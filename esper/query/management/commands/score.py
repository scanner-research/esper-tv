from __future__ import print_function
from __future__ import division
from django.core.management.base import BaseCommand
from query.models import Video, Face, LabelSet, Frame
from scannerpy import ProtobufGenerator, Config
import os
import cv2
import math
import numpy as np
import tensorflow as tf
import align.detect_face
from collections import defaultdict

cfg = Config()
proto = ProtobufGenerator(cfg)

class VideoStats(object):
    def __init__(self, num_detections, mismatches, tp, fp, fn):
        self.frame_nodet = frame_nodet
        self.frame_mismatches = frame_mismatch
        self.true_positives = tp
        self.false_positives = fp
        self.false_negatives = fn

class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def bbox_area(self, bbox, video):
        return ((bbox.x2 - bbox.x1)*video.width) * \
                            ((bbox.y2 - bbox.y1)*video.height)
         
    def compute_iou(self, bbox1, bbox2, video):
        int_x1=max(bbox1.x1, bbox2.x1)
        int_y1=max(bbox1.y1, bbox2.y1)
        int_x2=min(bbox1.x2, bbox2.x2)
        int_y2=min(bbox1.y2, bbox2.y2)
        
        int_area = 0.0
        if(int_x2 > int_x1 and int_y2 > int_y1):
            int_area = ((int_x2 - int_x1)*video.width) * \
                            ((int_y2 - int_y1)*video.height)

        iou = int_area/(self.bbox_area(bbox1, video)+self.bbox_area(bbox2, video)-int_area)
        return iou

    # fetch all faces in a video
    def fetch_faces(self, video):
        d_labelset = video.detected_labelset() # prediction
        g_labelset = video.handlabeled_labelset() # ground truth

        d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()
        g_faces = Face.objects.filter(frame__labelset=g_labelset).prefetch_related('frame').all()

        d_faces_dict = defaultdict(list)
        g_faces_dict = defaultdict(list)

        for d_face in d_faces:
            d_faces_dict[d_face.frame.number].append(d_face)

        for g_face in g_faces:
            g_faces_dict[g_face.frame.number].append(g_face)

        return (d_faces_dict, g_faces_dict)


    def eval_detector(self, video, frame_number, d_faces, g_faces):
        if len(d_faces) == 0 and len(g_faces) == 0:
            return (0, 0, 0, 0, 0)

        iou_threshold = 0.6
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        gender_mismatches = 0
         
        d_dict = defaultdict(int)
        g_dict = defaultdict(int)

        for d_face in d_faces:
            for g_face in g_faces:
                iou = self.compute_iou(d_face.bbox, g_face.bbox, video)
                if iou > iou_threshold:
                    if g_dict[g_face] != 0:
                        false_positives += 1
                    else:
                        true_positives += 1
                    if d_face.gender != g_face.gender:
                        gender_mismatches += 1
                    g_dict[g_face] += 1
                    d_dict[d_face] += 1

        for d_face in d_faces:
            if d_dict[d_face] == 0:
                false_positives += 1
        
        for g_face in g_faces:
            if g_dict[g_face] == 0:
                false_negatives += 1

        print("Frame({}) : d({}), g({}), tp({}), fp({}), fn({})".format(frame_number, len(d_faces), len(g_faces), true_positives, false_positives, false_negatives))

        return (len(d_faces), true_positives, false_positives, false_negatives, gender_mismatches)


    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        for path in paths:
            #video = Video.objects.filter(path=path).get()
            video = Video.objects.filter(id=1).get()
            print("Video {}".format(path))

            num_frames = 0
            frame_mismatches = 0

            num_detections = 0
            true_positives = 0
            false_positives = 0
            false_negatives = 0
            gender_mismatches = 0 #gender mismatch is on true positive detections

            (d_faces_dict, g_faces_dict) = self.fetch_faces(video)

            for frame_number in range(0, video.num_frames, video.get_stride()):
            #for frame_number in range(0, 1000, video.get_stride()):
                num_frames += 1
                d_faces = d_faces_dict[frame_number]
                g_faces = g_faces_dict[frame_number]
                (det, tp, fp, fn, gen) = self.eval_detector(video, frame_number, d_faces, g_faces)
                num_detections += det
                true_positives += tp
                false_positives += fp
                false_negatives += fn
                if fp != 0 or fn != 0:
                    frame_mismatches += 1
                gender_mismatches += gen

            print("Video({}) : num_frames({}), frame_mismatches({}), det({}), tp({}), fp({}), fn({}), gender_mismatches({})".format(video.id, num_frames, frame_mismatches, num_detections, true_positives, false_positives, false_negatives, gender_mismatches))
            precision = true_positives / (true_positives + false_positives)
            recall = true_positives / (true_positives + false_negatives)
            print("Video({}) : Precision({}), Recall({})".format(video.id, precision, recall))

