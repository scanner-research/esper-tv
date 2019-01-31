# import basic rekall queries
from esper.rekall_query import *

# import query sets
from query.models import LabeledInterview, CanonicalShow, Commercial

# import esper utils and widgets for selection
from esper.prelude import *
from esper.widget import *

import numpy as np
import random
import os
import pickle
from tqdm import tqdm
import cv2


def ground_truth_interviews(name, original=True):
    interviews = LabeledInterview.objects \
        .annotate(fps=F('video__fps')) \
        .annotate(min_frame=F('fps') * F('start')) \
        .annotate(max_frame=F('fps') * F('end')) \
        .filter(guest1=name)
    if original:
        interviews = interviews.filter(original=original)
    return VideoIntervalCollection(qs_to_intrvllists(interviews))


def load_num_face():
    face_dict = pickle.load(open('/app/data/num_face_intrvlcol.pkl', 'rb'))
    num_face_intrvlcol = {}
    for video_id, intervals in face_dict.items():
        num_face_intrvlcol[video_id] = IntervalList(intervals)
    num_face_intrvlcol = VideoIntervalCollection(num_face_intrvlcol)
    return num_face_intrvlcol


def load_intervals(video_ids, person_name, host_list,
                    face_size=0.2, stride_face=False, probability=0.7):

    person_intrvlcol = get_person_intrvlcol(person_name, video_ids=video_ids, face_size=face_size, 
                                            stride_face=stride_face, probability=probability, 
                                            granularity='second', payload_type='face_size')
    
    video_ids = list(person_intrvlcol.get_allintervals().keys())
    host_intrvlcol = get_person_intrvlcol(host_list, video_ids=video_ids, face_size=face_size, \
                                          stride_face=stride_face, probability=probability, 
                                          granularity='second', payload_type='shot_id')
    
    commercial = get_commercial_intrvlcol(video_ids, granularity='second')
    
    return person_intrvlcol, host_intrvlcol, commercial

    
def interview_query(person_intrvlcol, host_intrvlcol, commercial, num_face_intrvlcol=None):
    """
    Give person X, and a list of hosts, find all the intervals which is a interview with person X
    
    @person_intrvlcol: VideoIntervalCollection of person X
    @host_intrvlcol: VideoIntervalCollection of all the hosts
    @commercial: VideoIntervalCollection of all commercial
    @num_face_intrvlcol: VideoIntervalCollection of all intervals storing the number of faces in payload
    (This is precomputed using rust)
    """
    # Only keep related host videos
    host_intrvlcol_related = {}
    for video_id in person_intrvlcol.get_allintervals():
        if video_id in host_intrvlcol.get_allintervals():
            host_intrvlcol_related[video_id] = host_intrvlcol.get_intervallist(video_id)
    host_intrvlcol = VideoIntervalCollection(host_intrvlcol_related)
        
    # Remove single frame intervals 
#     person_intrvlcol = person_intrvlcol.filter_length(min_length=1)
#     host_intrvlcol = host_intrvlcol.filter_length(min_length=1)
    
    # Remove isolated small intervals
#     host_intrvlcol = remove_isolated_interval(host_intrvlcol)
#     person_intrvlcol = remove_isolated_interval(person_intrvlcol)
    
    # Split long segments into connected pieces
    host_intrvlcol = split_intrvlcol(host_intrvlcol, seg_length=30)
#     person_intrvlcol = split_intrvlcol(person_intrvlcol, seg_length=30)

    # This temporal predicate defines A overlaps with B, or A before by less than 60 seconds,
    #   or A after B by less than 60 seconds
    overlaps_before_or_after_pred = or_pred(
            or_pred(overlaps(), before(max_dist=60), arity=2),
            after(max_dist=60), arity=2)
    
    interview_candidates = host_intrvlcol \
                .merge(person_intrvlcol, predicate=overlaps_before_or_after_pred) \
                .coalesce() 
    
    # Sequences may be interrupted by shots where the guest or host don't
    # appear, so dilate and coalesce to merge neighboring segments
    interviews = interview_candidates \
            .dilate(120) \
            .coalesce() \
            .dilate(-1 * 120) \
            .filter_length(min_length=240) \
            .minus(commercial) \
            .filter_length(min_length=240)
    
    
    # remove interview segments which the total person time proportion is below threshold
    def filter_person_time(i):
        # Thresh for Trump 0.4, 0.4, 0.5 
        person_time = 0
        small_person_time, large_person_time = 0, 0
        for height, duration in i.payload:
            person_time += duration
            small_person_time += duration if height < 0.3 else 0
            large_person_time += duration if height > 0.3 else 0
        seg_length = i.end - i.start
        return person_time / seg_length > 0.35 and small_person_time / person_time < 0.7
    
    interviews_person_time = interviews.join(person_intrvlcol,
                             predicate=overlaps(),
                             merge_op=lambda i1, i2: [(i1.start, i1.end, [(i2.payload, i2.end - i2.start)])] ) \
                             .coalesce(payload_plus)
    interviews = interviews_person_time.filter(filter_person_time)
    
    # Remove interview if the person is alone for too long
#     def filter_person_alone(i):
#         for duration in i.payload:
#             if duration / (i.end - i.start) > 0.5:
#                 return False
#         return True

#     interviews_person_alone = interviews.join(interviews.minus(host_intrvlcol),
#                              predicate=overlaps(),
#                              merge_op=lambda i1, i2: [(i1.start, i1.end, [i2.end - i2.start])] ) \
#                              .coalesce(payload_plus)
#     interviews = interviews_person_alone.filter(filter_person_alone)
    
    # Remove interview segments which the total host time proportion is below threshold
    # and there is only one host showing a lot
#     def filter_host_time(i):
#         host_time = {}
#         for faceID_id, duration in i.payload:
#             if not faceID_id in host_time:
#                 host_time[faceID_id] = 0
#             host_time[faceID_id] += duration
#         host_time_sort = sorted(host_time.values())
#         sum_host_time = sum(host_time_sort)
#         if sum_host_time / (i.end - i.start) < 0.1:
#             return False
#         if len(host_time_sort) > 1 and host_time_sort[-2] > 0.2:
#             return False
#         return True

    # Remove interview segments where many people showing a lot
#     def filter_face_in_shot(i):
#         shot_time = {}
#         for shot_id, duration in i.payload:
#             shot_time[shot_id] = duration
#         face_cnt = count_face_in_shot(shot_time.keys())
#         multi_person_duration = sum([shot_time[id] for id in shot_time if face_cnt[id] > 2])
#         return multi_person_duration / (i.end - i.start) < 0.05
    
#     interviews_host_time = interviews.join(host_intrvlcol,
#                              predicate=overlaps(),
#                              merge_op=lambda i1, i2: [(i1.start, i1.end, [(i2.payload, i2.end - i2.start)])]) \
#                              .coalesce(payload_plus)
#     interviews = interviews_host_time.filter(filter_face_in_shot)
    
    # Remove interview segments where many people showing a lot
#     def filter_num_face(i):
#         multi_person_duration = sum([duration for nface, duration in i.payload if nface > 2])
#         return multi_person_duration / (i.end - i.start) < 0.05
    
#     interviews_num_face = interviews.join(num_face_intrvlcol,
#                              predicate=overlaps(),
#                              merge_op=lambda i1, i2: [(i1.start, i1.end, [(i2.payload, i2.end - i2.start)])]) \
#                              .coalesce(payload_plus)
#     interviews = interviews_num_face.filter(filter_num_face)

    
    person_all = interviews.overlaps(person_intrvlcol)

    person_with_host = person_all.overlaps(host_intrvlcol)
    
    person_only = person_all.minus(person_with_host)
    
    host_only = interviews.overlaps(host_intrvlcol).minus(person_with_host)
    
    return interviews, person_only, host_only, person_with_host


def save_interview(person_name, suffix, interviews, person_only, host_only, person_with_host):
    """
    Save computed interviews of person X using pickel
    """
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview-{}.pkl'.format(person_name, suffix)
    
    if os.path.exists(pkl_path):
        interview_dict = pickle.load(open(pkl_path, 'rb'))
    else:
        interview_dict = {}
    
    for video_id, intrvllist in interviews.get_allintervals().items():
        all_list = intrvllist2list(intrvllist)
        if video_id in person_only.get_allintervals():
            person_list = intrvllist2list(person_only.get_intervallist(video_id))
        else:
            person_list = []
        
        if video_id in host_only.get_allintervals():
            host_list = intrvllist2list(host_only.get_intervallist(video_id))
        else:
            host_list = []
        
        if video_id in person_with_host.get_allintervals():
            person_with_host_list = intrvllist2list(person_with_host.get_intervallist(video_id))
        else:
            person_with_host_list = []
            
        interview_dict[video_id] = {'all': all_list, 'person_only': person_list, \
                                    'host_only': host_list, 'person_with_host': person_with_host_list}
    
    pickle.dump(interview_dict, open(pkl_path, 'wb'))
    
    
def load_interview(person_name, suffix):
    """
    load computed interviews of person X using pickel
    """
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview-{}.pkl'.format(person_name, suffix)
    
    if not os.path.exists(pkl_path):
        print("Interview for {} not founded".format(person_name))
        return None, None, None
    else:
        interview_dict = pickle.load(open(pkl_path, 'rb'))
        interviews, person_only, host_only, person_with_host = {}, {}, {}, {}
        for video_id, value in interview_dict.items():
            interviews[video_id] = IntervalList(value['all'])
            person_only[video_id] = IntervalList(value['person_only'])
            host_only[video_id] = IntervalList(value['host_only'])
            person_with_host[video_id] = IntervalList(value['person_with_host'])
        return VideoIntervalCollection(interviews), VideoIntervalCollection(person_only), \
                VideoIntervalCollection(host_only), VideoIntervalCollection(person_with_host)


def montage_interview(person_name, suffix, **kwargs):
    """
    From computed interviews of person X, create a montage
    """
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview-{}.pkl'.format(person_name, suffix)
    
    if not os.path.exists(pkl_path):
        print("Interview for {} not founded".format(person_name))
        return None
    
    interview_dict = pickle.load(open(pkl_path, 'rb'))
    
    videos, frames = [], []
    for video_id, value in interview_dict.items():
        if 'person_with_host' in value and len(value['person_with_host']) > 0:
            interval = random.choice(value['person_with_host'])
            video = Video.objects.filter(id=video_id)[0]
            frame = (interval[0] + interval[1]) / 2 * video.fps
            videos.append(video)
            frames.append(int(frame))
    return make_montage(videos, frames, **kwargs)        
        

def shotcut_interview(person_name):
    """
    Save some sampled frames from computed interviews of person X
    """
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview-final.pkl'.format(person_name)
    
    if not os.path.exists(pkl_path):
        print("Interview for {} not founded".format(person_name))
        return None
    
    path = '/app/result/interview/{}'.format(person_name)
    if not os.path.exists(path):
        os.mkdir(path)
    
    interview_dict = pickle.load(open(pkl_path, 'rb'))
    
    img_id = 0
    for video_id, value in interview_dict.items():
        if 'person_with_host' in value and len(value['person_with_host']) > 0:
            interval = random.choice(value['person_with_host'])
            video = Video.objects.filter(id=video_id)[0]
            frame = (interval[0] + interval[1]) / 2 * video.fps
            img = load_frame(video, int(frame), [])
            cv2.imwrite('{}/{}.jpg'.format(path, img_id), img)
            img_id += 1
            