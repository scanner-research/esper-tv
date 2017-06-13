from django.core.management.base import BaseCommand
from query.models import Video, Face, Identity
import random
import json
import tensorflow as tf
import facenet
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
            faces = Face.objects.filter(video=video).exclude(features='').order_by('frame').all()

            fps = video.fps

            # [first_frame, last_frame, all_features, avg_feature, sum_feature]
            recent_features = []
            
            old_frame_id = 0
            #index in the face array NOT the face id
            for face_idx in range(len(faces)):


                curr_face = faces[face_idx]
                curr_feature = np.array(json.loads(curr_face.features))
                curr_face_id = curr_face.id
                curr_frame_id = curr_face.frame
                confidence = curr_face.bbox.score;
                if confidence < .9:
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
                                    continue
                                identity = Identity.objects.create(cohesion=0.0)
                                identity.save()
                                for seq_face_id in item[2]:
                                    seq_face = Face.objects.filter(id=seq_face_id).get()
                                    seq_face.identity_id = identity.id;
                                    seq_face.save()


                    old_frame_id = curr_frame_id
                best_match = -1
                best_distance = 4.0
                for i in range(len(recent_features)):
                    curr_dist = dist(curr_feature, recent_features[i][3])
                    if curr_dist < best_distance:
                        best_distance = curr_dist
                        best_match = i
                if best_match == -1 or best_distance > threshold:
                    recent_features.append([curr_frame_id, curr_frame_id, [curr_face_id], curr_feature, curr_feature])
                else:
                    recent_features[best_match][1] = curr_face_id;
                    recent_features[best_match][2].append(curr_face_id)
                    recent_features[best_match][4] = np.add(recent_features[best_match][4], curr_feature)
                    recent_features[best_match][3] = np.divide(recent_features[best_match][4], len(recent_features[best_match][2]))
