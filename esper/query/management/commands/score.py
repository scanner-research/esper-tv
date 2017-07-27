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
from array import *

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

    #def add_arguments(self, parser):
        #parser.add_argument('path')

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

    def remove_duplicates(self, l):
        s = set()
        return [x for x in l
                if x not in s and not s.add(x)]

    # fetch all faces in a video
    def fetch_faces(self, video):
        d_labelset = video.detected_labelset() # prediction
        g_labelset = video.handlabeled_labelset() # ground truth

        d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()
        g_faces = Face.objects.filter(frame__labelset=g_labelset).prefetch_related('frame').all()

        d_faces_dict = defaultdict(list)
        g_faces_dict = defaultdict(list)

        selected_frames = []

        face_size_thres = 0.05
        for d_face in d_faces:
            if self.bbox_area(d_face.bbox, video) > (face_size_thres * video.width * video.height):
                d_faces_dict[d_face.frame.number].append(d_face)
                selected_frames.append(d_face.frame.number)

        for g_face in g_faces:
            if self.bbox_area(g_face.bbox, video) > (face_size_thres * video.width * video.height):
                g_faces_dict[g_face.frame.number].append(g_face)
                selected_frames.append(d_face.frame.number)

        selected_frames = self.remove_duplicates(selected_frames)

        return (selected_frames, d_faces_dict, g_faces_dict)


    def eval_frame(self, video, frame_number, d_faces, g_faces):
        if len(d_faces) == 0 and len(g_faces) == 0:
            return (0, 0, 0, 0, 0)

        iou_threshold = 0.5
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        gender_matches = 0
         
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
                        if d_face.gender == g_face.gender:
                            gender_matches += 1
                    g_dict[g_face] += 1
                    d_dict[d_face] += 1

        for d_face in d_faces:
            if d_dict[d_face] == 0:
                false_positives += 1
        
        for g_face in g_faces:
            if g_dict[g_face] == 0:
                false_negatives += 1

        #print("Frame({}) : d({}), g({}), tp({}), fp({}), fn({})".format(frame_number, len(d_faces), len(g_faces), true_positives, false_positives, false_negatives))

        return (len(d_faces), true_positives, false_positives, false_negatives, gender_matches)

    def eval_video(self, video):
        frame_mismatches = 0

        num_detections = 0
        true_positives = 0
        false_positives = 0
        false_negatives = 0
        gender_matches = 0 #gender match is on true positive detections

        (selected_frames, d_faces_dict, g_faces_dict) = self.fetch_faces(video)


        for frame_number in selected_frames:
        #for frame_number in range(0, 1000, video.get_stride()):
            d_faces = d_faces_dict[frame_number]
            g_faces = g_faces_dict[frame_number]
            (det, tp, fp, fn, gen) = self.eval_frame(video, frame_number, d_faces, g_faces)
            num_detections += det
            true_positives += tp
            false_positives += fp
            false_negatives += fn
            if fp != 0 or fn != 0:
                frame_mismatches += 1
            gender_matches += gen

        print("Video({}) : num_frames({}), selected_frames({}), frame_mismatches({})".format(video.id, int(video.num_frames/video.get_stride()), len(selected_frames), frame_mismatches))

        print("Video({}) : num_detections({}), tp({}), fp({}), fn({}), gender_matches({})".format(video.id, num_detections, true_positives, false_positives, false_negatives, gender_matches))

        if (true_positives + false_positives) != 0:
            det_precision = true_positives / (true_positives + false_positives)
        else:
            det_precision = 0.0
        if (true_positives + false_negatives) != 0:
            det_recall = true_positives / (true_positives + false_negatives)
        else:
            det_recall = 0.0
        if true_positives != 0:
            gender_precision = gender_matches / true_positives
        else:
            gender_precision = 1.0

        return (det_precision, det_recall, gender_precision)

    def handle(self, *args, **options):
        #with open(options['path']) as f:
        #    paths = [s.strip() for s in f.readlines()]

        start_video_id = 1
        end_video_id = 20

        avg_det_precision = 0.0
        avg_det_recall = 0.0
        avg_gender_precision = 0.0

        for video_id in range(start_video_id, end_video_id):
            #video = Video.objects.filter(path=path).get()
            video = Video.objects.filter(id=video_id).get()
            #print("Video {}".format(path))
            (det_precision, det_recall, gender_precision) = self.eval_video(video)
            print("Video({}) : Detection precision({}), Detection recall({}), Gender precision({})".format(video.id, det_precision, det_recall, gender_precision))

            avg_det_precision += det_precision
            avg_det_recall += det_recall
            avg_gender_precision += gender_precision

        avg_det_precision /= (end_video_id - start_video_id)
        avg_det_recall /= (end_video_id - start_video_id)
        avg_gender_precision /= (end_video_id - start_video_id)
        print("Average: Detection precision({}), Detection recall({}), Gender precision({})".format(avg_det_precision, avg_det_recall, avg_gender_precision))

