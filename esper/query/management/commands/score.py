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
from functools import wraps
import inspect

cfg = Config()
proto = ProtobufGenerator(cfg)

def initializer(func):
    """
    Automatically assigns the parameters.

    >>> class process:
    ...     @initializer
    ...     def __init__(self, cmd, reachable=False, user='root'):
    ...         pass
    >>> p = process('halt', True)
    >>> p.cmd, p.reachable, p.user
    ('halt', True, 'root')
    """
    names, varargs, keywords, defaults = inspect.getargspec(func)

    @wraps(func)
    def wrapper(self, *args, **kargs):
        for name, arg in list(zip(names[1:], args)) + list(kargs.items()):
            setattr(self, name, arg)

        for name, default in zip(reversed(names), reversed(defaults)):
            if not hasattr(self, name):
                setattr(self, name, default)

        func(self, *args, **kargs)

    return wrapper

class VideoStats(object):
    @initializer
    def __init__(self, video_id = 0, num_frames=0, tp_frames=0, fp_frames=0, fn_frames=0, mismatched_tp_frames=0, num_detections=0, tp_detections=0, fp_detections=0, fn_detections=0, gender_matches=0):
        pass


    def compute_precision_recall(self, tp, fp, fn):
        if (tp + fp) != 0:
            precision = tp / (tp + fp)
        else:
            precision = 0.0
        if (tp + fn) != 0:
            recall = tp / (tp + fn)
        else:
            recall = 0.0
        return (precision, recall)

    def compute_frame_acc_stats(self):
        return self.compute_precision_recall(self.tp_frames, self.fp_frames, self.fn_frames)

    def compute_det_acc_stats(self):
        (det_precision, det_recall) = self.compute_precision_recall(self.tp_detections, self.fp_detections, self.fn_detections)
        if self.tp_detections != 0:
            gender_precision = self.gender_matches / self.tp_detections
        else:
            gender_precision = 1.0
        return (det_precision, det_recall, gender_precision)

    def __str__(self):
        frame_stats = "Video({}): num_frames({}), tp({}), fp({}), fn({})".format(self.video_id, self.num_frames, self.tp_frames, self.fp_frames, self.fn_frames)
        frame_acc_stats = "Video({}): Frame selection precision({}), Frame selection recall({})".format(self.video_id, *self.compute_frame_acc_stats())

        det_stats = "Video({}): num_detections({}), tp({}), fp({}), fn({}), mismatched_frames({}), gender_matches({})".format(self.video_id, self.num_detections, self.tp_detections, self.fp_detections, self.fn_detections, self.mismatched_tp_frames, self.gender_matches)

        det_acc_stats = "Video({}): Detection precision({}), Detection recall({}), Gender precision({})".format(self.video_id, *self.compute_det_acc_stats())

        return frame_stats + "\n" + frame_acc_stats + "\n" + det_stats + "\n" + det_acc_stats

    def __add__(self, other):
        num_frames = self.num_frames + other.num_frames
        tp_frames = self.tp_frames + other.tp_frames
        fp_frames = self.fp_frames + other.fp_frames
        fn_frames = self.fn_frames + other.fn_frames
        mismatched_tp_frames = self.mismatched_tp_frames + other.mismatched_tp_frames
        num_detections = self.num_detections + other.num_detections
        tp_detections = self.tp_detections + other.tp_detections
        fp_detections = self.fp_detections + other.fp_detections
        fn_detections = self.fn_detections + other.fn_detections
        gender_matches = self.gender_matches + other.gender_matches
        return VideoStats(self.video_id, num_frames, tp_frames, fp_frames, fn_frames, mismatched_tp_frames, num_detections, tp_detections, fp_detections, fn_detections, gender_matches)

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


    def fetch_ground_truth(self, video, label):
        g_labelset = video.handlabeled_labelset() # ground truth
        #g_faces = Face.objects.filter(frame__labelset=g_labelset).prefetch_related('frame').all()

        g_faces = Face.objects.filter(frame__labelset=g_labelset, frame__labels__name="Talking Heads").prefetch_related('frame').all()

        ground_truth_frames = []
        g_faces_dict = defaultdict(list)

        for g_face in g_faces:
            g_faces_dict[g_face.frame.number].append(g_face)
            ground_truth_frames.append(g_face.frame.number)

        ground_truth_frames = self.remove_duplicates(ground_truth_frames)
        return (ground_truth_frames, g_faces_dict)


    def fetch_automatic_detections(self, video, label):
        d_labelset = video.detected_labelset() # prediction
        #d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()

        #d_faces = Face.objects.filter(frame__labelset=d_labelset, frame__number__in=ground_truth_frames).prefetch_related('frame').all()
        d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()

        detected_frames = []
        d_faces_dict = defaultdict(list)

        # metrics for automatic detection of frames with "talking heads"
        face_size_thres = 0.05
        det_score_thres = 0.95

        for d_face in d_faces:
            if d_face.bbox.score > 0.95 and self.bbox_area(d_face.bbox, video) > (face_size_thres * video.width * video.height):
                d_faces_dict[d_face.frame.number].append(d_face)
                detected_frames.append(d_face.frame.number)

        detected_frames = self.remove_duplicates(detected_frames)
        return (detected_frames, d_faces_dict)

    # fetch all faces in a video
    def fetch_faces(self, video, label = "Talking Heads"):
        (ground_truth_frames, g_faces_dict) = self.fetch_ground_truth(video, label)
        (detected_frames, d_faces_dict) = self.fetch_automatic_detections(video, label)

        return (ground_truth_frames, g_faces_dict, detected_frames, d_faces_dict)


    def eval_frame(self, video, frame_number, d_faces, g_faces):
        if len(d_faces) == 0 and len(g_faces) == 0:
            return (0, 0, 0, 0, 0)

        iou_threshold = 0.5
        tp_detections = 0
        fp_detections = 0
        fn_detections = 0
        gender_matches = 0
         
        d_dict = defaultdict(int)
        g_dict = defaultdict(int)

        for d_face in d_faces:
            for g_face in g_faces:
                iou = self.compute_iou(d_face.bbox, g_face.bbox, video)
                if iou > iou_threshold:
                    if g_dict[g_face] != 0:
                        fp_detections += 1
                    else:
                        tp_detections += 1
                        if d_face.gender == g_face.gender:
                            gender_matches += 1
                    g_dict[g_face] += 1
                    d_dict[d_face] += 1

        for d_face in d_faces:
            if d_dict[d_face] == 0:
                fp_detections += 1
        
        for g_face in g_faces:
            if g_dict[g_face] == 0:
                fn_detections += 1

        #print("Frame({}) : d({}), g({}), tp({}), fp({}), fn({})".format(frame_number, len(d_faces), len(g_faces), tp_detections, fp_detections, fn_detections))

        return (len(d_faces), tp_detections, fp_detections, fn_detections, gender_matches)

    def eval_frame_selection(self, g_frame_list, d_frame_list):
        tp_frames = [x for x in g_frame_list if x in d_frame_list]
        fp_frames = [x for x in d_frame_list if x not in tp_frames]
        fn_frames = [x for x in g_frame_list if x not in tp_frames]
        return (tp_frames, fp_frames, fn_frames)

    def eval_video(self, video):
        (ground_truth_frames, g_faces_dict, detected_frames, d_faces_dict) = self.fetch_faces(video)

        (tp_frames, fp_frames, fn_frames) = self.eval_frame_selection(ground_truth_frames, detected_frames)

        vstats = VideoStats(video_id=video.id, num_frames=int(video.num_frames/video.get_stride()),
                    tp_frames = len(tp_frames), fp_frames=len(fp_frames), fn_frames=len(fn_frames))

        for frame_number in tp_frames:
        #for frame_number in range(0, 1000, video.get_stride()):
            d_faces = d_faces_dict[frame_number]
            g_faces = g_faces_dict[frame_number]
            (num_detections, tp_detections, fp_detections, fn_detections, gender_matches) = self.eval_frame(video, frame_number, d_faces, g_faces)
            vstats.num_detections += num_detections
            vstats.tp_detections += tp_detections
            vstats.fp_detections += fp_detections
            vstats.fn_detections += fn_detections
            if fp_detections != 0 or fn_detections != 0:
                vstats.mismatched_tp_frames += 1
            vstats.gender_matches += gender_matches

        return vstats

    def handle(self, *args, **options):
        #with open(options['path']) as f:
        #    paths = [s.strip() for s in f.readlines()]

        start_video_id = 1
        end_video_id = 61

        vtotal_stats = VideoStats(video_id=0)

        for video_id in range(start_video_id, end_video_id):
            #video = Video.objects.filter(path=path).get()
            video = Video.objects.filter(id=video_id).get()
            #print("Video {}".format(path))
            vstats = self.eval_video(video)
            print(vstats)

            vtotal_stats = vtotal_stats + vstats

        print(vtotal_stats)
