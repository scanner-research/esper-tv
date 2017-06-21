from django.core.management.base import BaseCommand
from query.models import Video, Face, Track
import random
import json
import tensorflow as tf
import cv2
import os
import numpy as np


def load_imgs(img_directory):
    imgs = []
    for root, subdirs, files in os.walk(img_directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in ('.jpg', '.jpeg'):
                path = os.path.join(root, file)
                imgs.append(path)

    return imgs

# FIXME: Exit gracefully if same images being sent to clustering algorithm a
# second time...

def dist(feat1, feat2):
    return np.sum(np.square(np.subtract(feat1, feat2)))

class Command(BaseCommand):
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('threshold')
        parser.add_argument('sequence_time')
        parser.add_argument('min_feat_threshold')

    def handle(self, *args, **options):
        """
        Takes embeddings for faces and merges them into 'tracks'
        based on the distance of the embeddings.
        It walks through each frame of the video and adds each new
        face into a set of recently seen faces. The embedding of each
        face in a track is averaged together ('avg_feature') and the first_frame
        and last_frame of a track is recorded. If a similar (within 'threshold' 
        distance of the 'avg_feature' of a track) has not been
        seen in 'sequence_time' seconds, the track is added to the database. Any 
        sequence without at least 'min_feat_threshold' embeddings is dropped.

        Args:
        path : newline seperated file of paths to track faces
        threshold : L2 distance threshold for determining if a face embedding belongs to a track
        sequence_time : threshold number of seconds without seeing a similar face to dump the track to the database
        min_feat_threshold : minimum number of features in a track before dumping to the database
        """

        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]
        threshold = float(options['threshold'])
        sequence_time = float(options['sequence_time'])
        min_feat_threshold = int(options['min_feat_threshold'])

        for path in paths:
            if path == '':
                return
            print path
            video = Video.objects.filter(path=path).get()
            labelset = video.detected_labelset()
            faces = Face.objects.filter(labelset=labelset).exclude(features='').order_by('frame').all()

            fps = video.fps

            # [first_frame, last_frame, all_features, avg_feature, sum_feature]
            recent_features = []
            faces_len = len(faces)
            in_seq = 0
            short_seq = 0
            low_confidence = 0

            old_frame_id = 0
            #index in the face array NOT the face id
            for face_idx in range(len(faces)):


                curr_face = faces[face_idx]
                curr_feature = np.array(json.loads(curr_face.features))
                curr_face_id = curr_face.id
                curr_frame_id = curr_face.frame
                confidence = curr_face.bbox.score;
                if confidence < .98:
                    low_confidence += 1
                    continue

                if old_frame_id != curr_frame_id:
                    keep_set = []
                    complete_set = []
                    for feat in recent_features:
                        if float(curr_frame_id - feat[1])/fps > sequence_time:
                            complete_set.append(feat)
                        else:
                            keep_set.append(feat)
                    if len(keep_set) != len(recent_features):
                        recent_features = keep_set
                        if len(complete_set) > 0:
                            for item in complete_set:
                                seq_len = len(item[2])
                                if (seq_len < min_feat_threshold):
                                    short_seq += len(item[2])
                                    continue
                                first_frame = Face.objects.filter(id=item[2][0]).get().frame
                                last_frame = Face.objects.filter(id=item[2][-1]).get().frame
                                track = Track.objects.create(labelset=labelset, first_frame=first_frame, last_frame=last_frame)
                                track.save()
                                for seq_face_id in item[2]:
                                    seq_face = Face.objects.filter(id=seq_face_id).get()
                                    seq_face.track = track;
                                    in_seq += 1
                                    seq_face.save()


                    old_frame_id = curr_frame_id
                best_match = -1
                best_distance = 10000.0
                for i in range(len(recent_features)):
                    curr_dist = dist(curr_feature, recent_features[i][3])
                    if curr_dist < best_distance:
                        best_distance = curr_dist
                        best_match = i
                #if best_match >= 0:
                #    print best_match, best_distance
                if best_match == -1 or best_distance > threshold:
                    recent_features.append([curr_frame_id, curr_frame_id, [curr_face_id], curr_feature, curr_feature])
                else:
                    recent_features[best_match][1] = curr_frame_id;
                    recent_features[best_match][2].append(curr_face_id)
                    recent_features[best_match][4] = np.add(recent_features[best_match][4], curr_feature)
                    recent_features[best_match][3] = np.divide(recent_features[best_match][4], len(recent_features[best_match][2]))

            for item in complete_set:
                seq_len = len(item[2])
                if (seq_len < min_feat_threshold):
                    short_seq += len(item[2])
                    continue
                track = Track.objects.create(labelset=labelset, first_frame=item[2][0].frame, last_frame=item[2][-1].frame)
                track.save()
                for seq_face_id in item[2]:
                    seq_face = Face.objects.filter(id=seq_face_id).get()
                    seq_face.track_id = track.id;
                    in_seq += 1
                    seq_face.save()
            print 'total faces: ', faces_len
            print 'in output seq: ', in_seq
            print 'dropped in short seq: ', short_seq
            print 'low confidence', low_confidence
            recent_features_sum = 0
            for feat in recent_features:
                recent_features_sum += len(feat[2])
            print 'left in recent_features', recent_features_sum
            print 'accounted for: ', (recent_features_sum + low_confidence + short_seq + in_seq)
