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
    def __init__(self, video_id = 0, num_frames=0, selected_frames=0, mismatched_frames=0, num_detections=0, true_positives=0, false_positives=0, false_negatives=0, gender_matches=0):
        pass

    def compute_acc_stats(self):
        if (self.true_positives + self.false_positives) != 0:
            det_precision = self.true_positives / (self.true_positives + self.false_positives)
        else:
            det_precision = 0.0
        if (self.true_positives + self.false_negatives) != 0:
            det_recall = self.true_positives / (self.true_positives + self.false_negatives)
        else:
            det_recall = 0.0
        if self.true_positives != 0:
            gender_precision = self.gender_matches / self.true_positives
        else:
            gender_precision = 1.0
        return (det_precision, det_recall, gender_precision)


    def __str__(self):
        frame_stats = "Video({}): num_frames({}), selected_frames({}), mismatched_frames({})".format(self.video_id, self.num_frames, self.selected_frames, self.mismatched_frames)

        det_stats = "Video({}): num_detections({}), tp({}), fp({}), fn({}), gender_matches({})".format(self.video_id, self.num_detections, self.true_positives, self.false_positives, self.false_negatives, self.gender_matches)

        acc_stats = "Video({}): Detection precision({}), Detection recall({}), Gender precision({})".format(self.video_id, *self.compute_acc_stats())

        return frame_stats + "\n" + det_stats + "\n" + acc_stats

    def __add__(self, other):
        num_frames = self.num_frames + other.num_frames
        selected_frames = self.selected_frames + other.selected_frames
        mismatched_frames = self.mismatched_frames + other.mismatched_frames
        num_detections = self.num_detections + other.num_detections
        true_positives = self.true_positives + other.true_positives
        false_positives = self.false_positives + other.false_positives
        false_negatives = self.false_negatives + other.false_negatives
        gender_matches = self.gender_matches + other.gender_matches
        return VideoStats(self.video_id, num_frames, selected_frames, mismatched_frames, num_detections, true_positives, false_positives, false_negatives, gender_matches)

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
        face_size_thres = 0.05 # threshold for filtering frames

        d_labelset = video.detected_labelset() # prediction
        g_labelset = video.handlabeled_labelset() # ground truth

        #d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()
        #g_faces = Face.objects.filter(frame__labelset=g_labelset).prefetch_related('frame').all()

        g_faces = Face.objects.filter(frame__labelset=g_labelset, frame__labels__name="Talking Heads").prefetch_related('frame').all()

        selected_frames = []
        g_faces_dict = defaultdict(list)

        for g_face in g_faces:
            if self.bbox_area(g_face.bbox, video) > (face_size_thres * video.width * video.height):
                g_faces_dict[g_face.frame.number].append(g_face)
                selected_frames.append(g_face.frame.number)

        selected_frames = self.remove_duplicates(selected_frames)


        d_faces = Face.objects.filter(frame__labelset=d_labelset, frame__number__in=selected_frames).prefetch_related('frame').all()
        d_faces_dict = defaultdict(list)
        for d_face in d_faces:
            if self.bbox_area(d_face.bbox, video) > (face_size_thres * video.width * video.height):
                d_faces_dict[d_face.frame.number].append(d_face)

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
        (selected_frames, d_faces_dict, g_faces_dict) = self.fetch_faces(video)

        vstats = VideoStats(video_id=video.id, num_frames=int(video.num_frames/video.get_stride()),
                                                            selected_frames = len(selected_frames))

        for frame_number in selected_frames:
        #for frame_number in range(0, 1000, video.get_stride()):
            d_faces = d_faces_dict[frame_number]
            g_faces = g_faces_dict[frame_number]
            (det, tp, fp, fn, gen) = self.eval_frame(video, frame_number, d_faces, g_faces)
            vstats.num_detections += det
            vstats.true_positives += tp
            vstats.false_positives += fp
            vstats.false_negatives += fn
            if fp != 0 or fn != 0:
                vstats.mismatched_frames += 1
            vstats.gender_matches += gen

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
