

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

class VideoEvalStats(object):
    @initializer
    def __init__(self, video_id = 0, num_frames=0, tp_frames=0, fp_frames=0, fn_frames=0, mismatched_tp_frames=0, num_detections=0, tp_detections=0, fp_detections=0, fn_detections=0, num_males=0, num_females=0, gender_matches=0, male_mismatches=0, female_mismatches=0):
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
        return (det_precision, det_recall)

    def compute_gender_acc_stats(self):
        if self.tp_detections != 0:
            gender_precision = self.gender_matches / (self.num_males + self.num_females)
        else:
            gender_precision = 1.0
        return gender_precision

    def __str__(self):
        frame_stats = "Video({})[FRAME SELECTION]: num_frames({}), tp({}), fp({}), fn({})".format(self.video_id, self.num_frames, self.tp_frames, self.fp_frames, self.fn_frames)
        frame_acc_stats = "Video({})[FRAME SELECTION]: Frame selection precision({}), Frame selection recall({})".format(self.video_id, *self.compute_frame_acc_stats())

        det_stats = "Video({})[DETECTION]: num_detections({}), tp({}), fp({}), fn({}), mismatched_frames({})".format(self.video_id, self.num_detections, self.tp_detections, self.fp_detections, self.fn_detections, self.mismatched_tp_frames)
        det_acc_stats = "Video({})[DETECTION]: Detection precision({}), Detection recall({})".format(self.video_id, *self.compute_det_acc_stats())

        gender_stats = "Video({})[GENDER]: males({}), females({}), gender_matches({}), male_mismatches({}), female_mismatches({})".format(self.video_id, self.num_males, self.num_females, self.gender_matches, self.male_mismatches, self.female_mismatches)
        gender_acc_stats = "Video({})[GENDER]: Gender precision({})".format(self.video_id, self.compute_gender_acc_stats())

        return frame_stats + "\n" + frame_acc_stats + "\n" + det_stats + "\n" + det_acc_stats + "\n" + gender_stats + "\n" + gender_acc_stats

    def __add__(self, other):
        num_frames = self.num_frames + other.num_frames

        # frame selection
        tp_frames = self.tp_frames + other.tp_frames
        fp_frames = self.fp_frames + other.fp_frames
        fn_frames = self.fn_frames + other.fn_frames
        # face detection
        num_detections = self.num_detections + other.num_detections
        mismatched_tp_frames = self.mismatched_tp_frames + other.mismatched_tp_frames
        tp_detections = self.tp_detections + other.tp_detections
        fp_detections = self.fp_detections + other.fp_detections
        fn_detections = self.fn_detections + other.fn_detections
        # gender detection
        num_males = self.num_males + other.num_males
        num_females = self.num_females + other.num_females
        gender_matches = self.gender_matches + other.gender_matches
        male_mismatches = self.male_mismatches + other.male_mismatches
        female_mismatches = self.female_mismatches + other.female_mismatches

        return VideoEvalStats(self.video_id, num_frames, tp_frames, fp_frames, fn_frames, mismatched_tp_frames, num_detections, tp_detections, fp_detections, fn_detections, num_males, num_females, gender_matches, male_mismatches, female_mismatches)


class VideoStats(object):
    @initializer
    def __init__(self, video_id = 0, num_frames=0, selected_frames=0, num_detections=0, num_males=0, num_females=0):
        pass

    def __str__(self):
        stats = "Video({}): num_frames({}), selected_frames({}), num_detections({}), num_males({}), num_females({})".format(self.video_id, self.num_frames, self.selected_frames, self.num_detections, self.num_males, self.num_females)
        return stats

    def __add__(self, other):
        num_frames = self.num_frames + other.num_frames
        selected_frames = self.selected_frames + other.selected_frames
        num_detections = self.num_detections + other.num_detections
        num_males = self.num_males + other.num_males
        num_females = self.num_females + other.num_females
        return VideoStats(self.video_id, num_frames, selected_frames, num_detections, num_males, num_females)

class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('command')

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


    def fetch_ground_truth(self, video, label = "Talking Heads"):
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


    def fetch_automatic_detections(self, video, label = "Talking Heads"):
        d_labelset = video.detected_labelset() # prediction
        #d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()

        #d_faces = Face.objects.filter(frame__labelset=d_labelset, frame__number__in=ground_truth_frames).prefetch_related('frame').all()
        d_faces = Face.objects.filter(frame__labelset=d_labelset).prefetch_related('frame').all()

        detected_frames = []
        d_faces_dict = defaultdict(list)

        # metrics for automatic detection of frames with "talking heads"
        face_size_thres = 0.03
        det_score_thres = 0.95

        for d_face in d_faces:
            if d_face.bbox.score > det_score_thres and self.bbox_area(d_face.bbox, video) > (face_size_thres * video.width * video.height):
                d_faces_dict[d_face.frame.number].append(d_face)
                detected_frames.append(d_face.frame.number)

        detected_frames = self.remove_duplicates(detected_frames)
        return (detected_frames, d_faces_dict)

    def eval_detection(self, video, frame_number, d_faces, g_faces, vstats):
        if len(d_faces) == 0 and len(g_faces) == 0:
            return (0, 0, 0, 0, 0)

        iou_threshold = 0.5
        tp_detections = 0
        fp_detections = 0
        fn_detections = 0
        gender_matches = 0
         
        d_dict = defaultdict(int)
        g_dict = defaultdict(int)

        gender_eval_list = []

        for d_face in d_faces:
            for g_face in g_faces:
                iou = self.compute_iou(d_face.bbox, g_face.bbox, video)
                if iou > iou_threshold:
                    if g_dict[g_face] != 0:
                        fp_detections += 1
                    else:
                        tp_detections += 1
                        #if d_face.gender == g_face.gender:
                        #    gender_matches += 1
                        gender_eval_list.append((d_face.gender, g_face.gender))
                    g_dict[g_face] += 1
                    d_dict[d_face] += 1

        for d_face in d_faces:
            if d_dict[d_face] == 0:
                fp_detections += 1
        
        for g_face in g_faces:
            if g_dict[g_face] == 0:
                fn_detections += 1

        # update detection stats
        vstats.num_detections += len(d_faces)
        vstats.tp_detections += tp_detections
        vstats.fp_detections += fp_detections
        vstats.fn_detections += fn_detections
        if fp_detections != 0 or fn_detections != 0:
            vstats.mismatched_tp_frames += 1

        return (vstats, gender_eval_list)

    def eval_frame_selection(self, g_frame_list, d_frame_list):
        tp_frames = [x for x in g_frame_list if x in d_frame_list]
        fp_frames = [x for x in d_frame_list if x not in tp_frames]
        fn_frames = [x for x in g_frame_list if x not in tp_frames]
        return (tp_frames, fp_frames, fn_frames)

    def eval_gender(self, gender_eval_list, vstats):
        num_males = 0
        num_females = 0
        gender_matches = 0
        male_mismatches = 0
        female_mismatches = 0
        for (d, g) in gender_eval_list:
            if d == 'M':
                num_males += 1
                if g != d:
                    male_mismatches += 1
                else:
                    gender_matches += 1
            else:
                num_females += 1
                if g != d:
                    female_mismatches += 1
                else:
                    gender_matches += 1

        #update gender stats
        vstats.num_males += num_males
        vstats.num_females += num_females
        vstats.gender_matches += gender_matches
        vstats.male_mismatches += male_mismatches
        vstats.female_mismatches += female_mismatches

        return vstats


    def eval_video(self, video):
        (ground_truth_frames, g_faces_dict) = self.fetch_ground_truth(video)
        (detected_frames, d_faces_dict) = self.fetch_automatic_detections(video)

        (tp_frames, fp_frames, fn_frames) = self.eval_frame_selection(ground_truth_frames, detected_frames)

        vstats = VideoEvalStats(video_id=video.id, num_frames=int(video.num_frames/video.get_stride()), tp_frames = len(tp_frames), fp_frames=len(fp_frames), fn_frames=len(fn_frames))

        #for frame_number in range(0, 1000, video.get_stride()):
        for frame_number in tp_frames:
            # evaluate detection
            d_faces = d_faces_dict[frame_number]
            g_faces = g_faces_dict[frame_number]
            (vstats, gender_eval_list) = self.eval_detection(video, frame_number, d_faces, g_faces, vstats)

            # evaluate gender
            vstats = self.eval_gender(gender_eval_list, vstats)

        return vstats

    def eval_videos(self, start_video_id, end_video_id):
        vtotal_stats = VideoEvalStats(video_id=0)

        for video_id in range(start_video_id, end_video_id):
            video = Video.objects.filter(id=video_id).get()
            vstats = self.eval_video(video)
            print(vstats)

            vtotal_stats = vtotal_stats + vstats

        print(vtotal_stats)

    def infer_videos(self, start_video_id, end_video_id):
        vtotal_stats = VideoStats(video_id=0)

        for video_id in range(start_video_id, end_video_id):
            video = Video.objects.filter(id=video_id).get()
            (detected_frames, d_faces_dict) = self.fetch_automatic_detections(video)

            vstats = VideoStats(video_id=video.id, num_frames=int(video.num_frames/video.get_stride()), selected_frames=len(detected_frames))

            #for frame_number in range(0, 1000, video.get_stride()):
            for frame_number in detected_frames:
                # evaluate detection
                d_faces = d_faces_dict[frame_number]
                for d_face in d_faces:
                    vstats.num_detections += 1
                    if d_face.gender == 'M':
                        vstats.num_males += 1
                    else:
                        vstats.num_females += 1

            print(vstats)

            vtotal_stats = vtotal_stats + vstats
        print(vtotal_stats)

    def handle(self, *args, **options):
        start_video_id = 1
        end_video_id = 61

        #with open(options['path']) as f:
        #    paths = [s.strip() for s in f.readlines()]
        command = options['command']
        if command == "eval":
            self.eval_videos(start_video_id, end_video_id) # compare with labeled data
        elif command == "infer":
            self.infer_videos(start_video_id, end_video_id) # no labeled data (just infer)
        else:
            print("Error: eval or run")

