from esper.rekall_query import *

# import query sets
from query.models import LabeledInterview, CanonicalShow

# import esper utils and widgets for selection
from esper.prelude import *
from esper.widget import *
from IPython.display import display, clear_output
import ipywidgets as widgets

import numpy as np
import random
import os
import pickle
import tempfile
from tqdm import tqdm
import multiprocessing
import pysrt
import re
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
                                            stride_face=stride_face, probability=probability, granularity='second')
    
    video_ids = list(person_intrvlcol.get_allintervals().keys())
    host_intrvlcol = get_person_intrvlcol(host_list, video_ids=video_ids, face_size=face_size, \
                                          stride_face=stride_face, probability=probability, granularity='second')
            
    commercial = get_commercial_intrvlcol(video_ids, granularity='second')
    
    return person_intrvlcol, host_intrvlcol, commercial

    
def interview_query(person_intrvlcol, host_intrvlcol, commercial):
    
    # Get all shots where the guest and a host are on screen together
#     person_with_X = person_intrvlcol.overlaps(host_intrvlcol)
    
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

    
    interview_candidates = host_intrvlcol \
            .merge(person_intrvlcol, predicate=overlaps_before_or_after_pred) \
            .coalesce() 
    
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
            .minus(commercial)
    
    person_in_interviews = interviews.overlaps(person_intrvlcol)
    
    # remove interview segments which the total person time proportion is below threshold
    min_proportion = 0.4
    def filter_person_time(i):
        return i.payload / (i.end - i.start) > min_proportion
    
    interviews_persontime = interviews.join(person_in_interviews,
                             predicate=overlaps(),
                             merge_op=lambda i1, i2: [(i1.start, i1.end, i2.end - i2.start)]) \
                             .coalesce(payload_plus)
    interviews = interviews_persontime.filter(filter_person_time)
    person_in_interviews = interviews.overlaps(person_intrvlcol)
    
    return interviews, person_in_interviews


def save_interview(person_name, interviews, person_in_interviews):
    pkl_path = '/app/result/interview/{}-interview.pkl'.format(person_name)
    
    if os.path.exists(pkl_path):
        interview_dict = pickle.load(open(pkl_path, 'rb'))
    else:
        interview_dict = {}
    
    for video_id, intrvllist in interviews.get_allintervals().items():
        all_list = intrvllist2list(intrvllist)
        person_list = intrvllist2list(person_in_interviews.get_allintervals()[video_id])
        interview_dict[video_id] = {'all': all_list, 'person': person_list}
    
    pickle.dump(interview_dict, open(pkl_path, 'wb'))
    