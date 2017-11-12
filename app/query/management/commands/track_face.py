from django.core.management.base import BaseCommand
from query.base_models import ModelDelegator
import random
import json
import tensorflow as tf
import cv2
import os
import numpy as np
from django.core.exceptions import ValidationError

def dist(feat1, feat2):
    return np.sum(np.square(np.subtract(feat1, feat2)))

DATASET = os.environ.get('DATASET')
models = ModelDelegator(DATASET)
Video, Labeler, FaceFeatures, Face, FaceTrack = models.Video, models.Labeler, models.FaceFeatures, models.Face, models.FaceTrack

# TODO(matt): clean this up, seems like there's a lot of redundant/commented code
# The 5-tuple that's stored in "recent_features" should be a dict for human-readable keys

class Command(BaseCommand):
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str)
        parser.add_argument('bbox_labeler', nargs='?', default='tinyfaces')
        parser.add_argument('feature_labeler', nargs='?', default='facenet')
        parser.add_argument('-t', '--threshold', type=float, default=.65)
        parser.add_argument('-s', '--sequence_time', type=int, default=5)
        parser.add_argument('-m', '--min_feat_threshold', type=int, default=3)

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

        bbox_labeler = Labeler.objects.get(name=options['bbox_labeler'])
        feature_labeler = Labeler.objects.get(name=options['feature_labeler'])

        for path in paths:
            if path == '':
                return
            print path
            video = Video.objects.filter(path=path).get()
            face_features = FaceFeatures.objects.filter(
                face__frame__video=video,
                face__labeler=bbox_labeler,
                labeler=feature_labeler).order_by('face__frame__number').all()
            fps = video.fps

            # [first_frame, last_frame, all_features, avg_feature, sum_feature]
            recent_features = []
            faces_len = len(face_features)
            in_seq = 0
            short_seq = 0
            low_confidence = 0

            old_frame_id = 0
            #index in the face array NOT the face id
            for face_idx in range(faces_len):
                curr_face = face_features[face_idx]
                curr_feature = np.array(json.loads(str(curr_face.features)))
                curr_face_id = curr_face.face.id
                curr_frame_id = curr_face.face.frame.number
                confidence = curr_face.face.bbox_score
                #                if confidence < .98:
                #                    low_confidence += 1
                #                    continue

                if old_frame_id != curr_frame_id:
                    keep_set = []
                    complete_set = []
                    for feat in recent_features:
                        if float(curr_frame_id - feat[1]) / fps > sequence_time:
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
                                track = FaceTrack()
                                track.labeler = bbox_labeler
                                track.save()
                                last_frame = None
                                for seq_face_id in item[2]:
                                    seq_face = Face.objects.get(id=seq_face_id)
                                    if seq_face.frame.number == last_frame: continue
                                    seq_face.track = track
                                    in_seq += 1
                                    seq_face.save()
                                    last_frame = seq_face.frame.number

                    old_frame_id = curr_frame_id
                best_match = -1
                best_distance = 10000.0
                for i in range(len(recent_features)):
                    curr_dist = dist(curr_feature, recent_features[i][3])
                    if curr_dist < best_distance:
                        best_distance = curr_dist
                        best_match = i

                if best_match == -1 or best_distance > threshold:
                    recent_features.append(
                        [curr_frame_id, curr_frame_id, [curr_face_id], curr_feature, curr_feature])
                else:
                    recent_features[best_match][1] = curr_frame_id
                    recent_features[best_match][2].append(curr_face_id)
                    recent_features[best_match][4] = np.add(recent_features[best_match][4],
                                                            curr_feature)
                    recent_features[best_match][3] = np.divide(recent_features[best_match][4],
                                                               len(recent_features[best_match][2]))

            for item in recent_features:
                seq_len = len(item[2])
                if (seq_len < min_feat_threshold):
                    short_seq += len(item[2])
                    continue
                track = FaceTrack()
                track.labeler = bbox_labeler
                track.save()
                last_frame = None
                for seq_face_id in item[2]:
                    seq_face = Face.objects.get(id=seq_face_id)
                    if seq_face.frame.number == last_frame: continue
                    seq_face.track = track
                    in_seq += 1
                    seq_face.save()
                    last_frame = seq_face.frame.number
            print 'total faces: ', faces_len
            print 'in output seq: ', in_seq
            print 'dropped in short seq: ', short_seq
            print 'low confidence', low_confidence
            print 'accounted for: ', (low_confidence + short_seq + in_seq)
