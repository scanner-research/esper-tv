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


def load_intervals(video_ids, person_name, host_list,
                    face_size=0.2, stride_face=False, probability=0.7):

    person_intrvlcol = get_person_intrvlcol(person_name, video_ids=video_ids, face_size=face_size, 
                                            stride_face=stride_face, probability=probability, 
                                            granularity='second', payload_type='height')
    
    video_ids = list(person_intrvlcol.get_allintervals().keys())
    host_intrvlcol = get_person_intrvlcol(host_list, video_ids=video_ids, face_size=face_size, \
                                          stride_face=stride_face, probability=probability, 
                                          granularity='second', payload_type='shot_id')
            
    commercial = get_commercial_intrvlcol(video_ids, granularity='second')
    
    return person_intrvlcol, host_intrvlcol, commercial

    
def interview_query(person_intrvlcol, host_intrvlcol, commercial):
      
    # Remove single frame intervals 
#     person_intrvlcol = person_intrvlcol.filter_length(min_length=1)
#     host_intrvlcol = host_intrvlcol.filter_length(min_length=1)
    
    # Remove isolated small intervals
    host_intrvlcol = remove_isolated_interval(host_intrvlcol)
    person_intrvlcol = remove_isolated_interval(person_intrvlcol)
    
    # Test on removing sparse intervals
#     a = IntervalList([(0,1,0), (3,4,0), (6,7,0), (9,10,0), (12,13,0)])
#     window_size = 6
#     b = a.join(a, 
#            predicate=or_pred(before(max_dist=window_size/2), after(max_dist=window_size/2), arity=2),
#            merge_op=lambda i1, i2: [(i1.start, i1.end, [i2])],
#            working_window=window_size) \
#         .coalesce(payload_plus)
    
    # Split long segments into connected pieces
    host_intrvlcol = split_intrvlcol(host_intrvlcol, seg_length=30)

    # This temporal predicate defines A overlaps with B, or A before by less than 10 frames,
    #   or A after B by less than 10 frames
    overlaps_before_or_after_pred = or_pred(
            or_pred(overlaps(), before(max_dist=60), arity=2),
            after(max_dist=60), arity=2)

#     print(host_intrvlcol.get_allintervals())
    
    interview_candidates = host_intrvlcol \
            .merge(person_intrvlcol, predicate=overlaps_before_or_after_pred) \
            .coalesce() 
    
#     print(interview_candidates.get_allintervals())
    
    # This code finds sequences of:
    #   guest with host overlaps/before/after host OR
    #   guest with host overlaps/before/after guest
#     interview_candidates = person_with_X \
#             .merge(host_intrvlcol, predicate=overlaps_before_or_after_pred) \
#             .set_union(person_with_X.merge(
#                 person_intrvlcol, predicate=overlaps_before_or_after_pred)) \
#             .coalesce()

    # Sequences may be interrupted by shots where the guest or host don't
    #   appear, so dilate and coalesce to merge neighboring segments
    interviews = interview_candidates \
            .dilate(120) \
            .coalesce() \
            .dilate(-1 * 120) \
            .filter_length(min_length=240) \
            .minus(commercial) \
            .filter_length(min_length=240)
    
    # remove interview segments which the total person time proportion is below threshold
    def filter_person_time(i):
        person_time = 0
        small_person_time = 0
        for height, duration in i.payload:
            person_time += duration
            small_person_time += duration if height < 0.3 else 0 
        seg_length = i.end - i.start
        return person_time / seg_length > 0.4 and small_person_time / person_time < 0.5
    
    interviews_person_time = interviews.join(person_intrvlcol,
                             predicate=overlaps(),
                             merge_op=lambda i1, i2: [(i1.start, i1.end, [(i2.payload, i2.end - i2.start)])]) \
                             .coalesce(payload_plus)
    interviews = interviews_person_time.filter(filter_person_time)
    
    # remove interview segments which the total host time proportion is below threshold
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
    
    # remove interview segments where many people showing a lot
    def filter_face_in_shot(i):
        shot_time = {}
        for shot_id, duration in i.payload:
            shot_time[shot_id] = duration
        face_cnt = count_face_in_shot(shot_time.keys())
        multi_person_duration = sum([shot_time[id] for id in shot_time if face_cnt[id] > 2])
        return multi_person_duration / (i.end - i.start) < 0.3
    
    interviews_host_time = interviews.join(host_intrvlcol,
                             predicate=overlaps(),
                             merge_op=lambda i1, i2: [(i1.start, i1.end, [(i2.payload, i2.end - i2.start)])]) \
                             .coalesce(payload_plus)
    interviews = interviews_host_time.filter(filter_face_in_shot)
    
    person_in_interviews = interviews.overlaps(person_intrvlcol)
    
    person_with_host = person_in_interviews.overlaps(host_intrvlcol)
    
    return interviews, person_in_interviews, person_with_host


def save_interview(person_name, interviews, person_in_interviews, person_with_host):
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview.pkl'.format(person_name)
    
    if os.path.exists(pkl_path):
        interview_dict = pickle.load(open(pkl_path, 'rb'))
    else:
        interview_dict = {}
    
    for video_id, intrvllist in interviews.get_allintervals().items():
        all_list = intrvllist2list(intrvllist)
        person_list = intrvllist2list(person_in_interviews.get_intervallist(video_id))
        if video_id in person_with_host.get_allintervals():
            person_with_host_list = intrvllist2list(person_with_host.get_intervallist(video_id))
        else:
            person_with_host_list = []
        interview_dict[video_id] = {'all': all_list, 'person': person_list, 'person_with_host': person_with_host_list}
    
    pickle.dump(interview_dict, open(pkl_path, 'wb'))
    
    
def load_interview(person_name):
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview-clean.pkl'.format(person_name)
    
    if not os.path.exists(pkl_path):
        print("Interview for {} not founded".format(person_name))
        return None, None, None
    else:
        interview_dict = pickle.load(open(pkl_path, 'rb'))
        interviews, person_in_interviews, person_with_host = {}, {}, {}
        for video_id, value in interview_dict.items():
            interviews[video_id] = IntervalList(value['all'])
            person_in_interviews[video_id] = IntervalList(value['person'])
            if 'person_with_host' in value:
                person_with_host[video_id] = IntervalList(value['person_with_host'])
            else:
                person_with_host[video_id] = IntervalList([])
        return VideoIntervalCollection(interviews), VideoIntervalCollection(person_in_interviews), VideoIntervalCollection(person_with_host)


def montage_interview(person_name, **kwargs):
    person_name = person_name.lower()
    pkl_path = '/app/result/interview/{}-interview.pkl'.format(person_name)
    
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
        
