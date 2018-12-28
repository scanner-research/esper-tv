from django.db.models import F
# import rekall
from esper.rekall import *
from rekall.video_interval_collection import VideoIntervalCollection
from rekall.interval_list import Interval, IntervalList
from rekall.temporal_predicates import *
from rekall.spatial_predicates import *
from rekall.parsers import in_array, bbox_payload_parser
from rekall.merge_ops import payload_plus
from rekall.payload_predicates import payload_satisfies
from rekall.list_predicates import length_exactly
# import caption search
from esper.captions import *

# import face identities for person search
from query.models import Video, Face, FaceIdentity

# import esper widget for debugging
from esper.prelude import esper_widget, concat_videos

import random
import os
import pickle
import tempfile
from tqdm import tqdm
import multiprocessing

def second2time(second, sep=','):
    h, m, s, ms = int(second) // 3600, int(second % 3600) // 60, int(second) % 60, int((second - int(second)) * 1000)
    return '{:02d}:{:02d}:{:02d}{:s}{:03d}'.format(h, m, s, sep, ms)


def count_intervals(intrvlcol):
    num_intrvl = 0
    for intrvllist in intrvlcol.get_allintervals().values():
        num_intrvl += intrvllist.size()
    return num_intrvl


def get_person_intrvlcol(person_name, video_ids=None):
    all_faces = FaceIdentity.objects
    if not video_ids is None:
        all_faces = all_faces.filter(face__shot__video_id__in=video_ids)
        
    person_intrvllists = qs_to_intrvllists(
        all_faces
            .filter(identity__name=person_name.lower())
            .filter(probability__gt=0.99)
            .annotate(video_id=F("face__shot__video_id"))
            .annotate(shot_id=F("face__shot_id"))
            .annotate(min_frame=F("face__shot__min_frame"))
            .annotate(max_frame=F("face__shot__max_frame")),
        schema={
            'start': 'min_frame',
            'end': 'max_frame',
            'payload': 'shot_id'
        })
    num_intrvl = 0
    for _, intrvllist in person_intrvllists.items():
        num_intrvl += intrvllist.size()
    print("Get %d intervals" % num_intrvl)
    return VideoIntervalCollection(person_intrvllists)


def get_caption_intrvlcol(phrase, video_ids=None):
    results = phrase_search(phrase, video_ids)
    
    if video_ids == None:
        videos = {v.id: v for v in Video.objects.all()}
    else:
        videos = {v.id: v for v in Video.objects.filter(id__in=video_ids).all()}
    def convert_time(k, t):
        return int(t * videos[k].fps)
    
    flattened = [
        (doc.id, convert_time(doc.id, p.start), convert_time(doc.id, p.end)) 
        for doc in results
        for p in doc.postings
    ]
    phrase_intrvllists = {}
    for video_id, t1, t2 in flattened:
        if video_id in phrase_intrvllists:
            phrase_intrvllists[video_id].append((t1, t2, 0))
        else:
            phrase_intrvllists[video_id] = [(t1, t2, 0)]
    
    for video_id, intrvllist in phrase_intrvllists.items():
        phrase_intrvllists[video_id] = IntervalList(intrvllist)
        
    num_intrvl = 0
    for _, intrvllist in phrase_intrvllists.items():
        num_intrvl += intrvllist.size()
    print("Get %d intervals" % num_intrvl)
    return VideoIntervalCollection(phrase_intrvllists)


def get_relevant_shots(intrvlcol):
    relevant_shots = set()
    for intrvllist in list(intrvlcol.get_allintervals().values()):
        for interval in intrvllist.get_intervals():
            relevant_shots.add(interval.get_payload())
    print("Get %d relevant shots" % len(relevant_shots))
    return relevant_shots


def get_oneface_intrvlcol(relevant_shots):
    faces = Face.objects.filter(shot__in=list(relevant_shots)) \
            .annotate(video_id=F('shot__video_id')) \
            .annotate(min_frame=F('shot__min_frame')) \
            .annotate(max_frame=F('shot__max_frame'))

    # Materialize all the faces and load them into rekall with bounding box payloads
    # Then coalesce them so that all faces in the same frame are in the same interval
    # NOTE that this is slow right now since we're loading all faces!
    oneface_intrvlcol = VideoIntervalCollection.from_django_qs(
        faces,
        with_payload=in_array(
            bbox_payload_parser(VideoIntervalCollection.django_accessor))
        ).coalesce(payload_merge_op=payload_plus).filter(payload_satisfies(length_exactly(1)))
    
    num_intrvl = 0
    for _, intrvllist in oneface_intrvlcol.get_allintervals().items():
        num_intrvl += intrvllist.size()
    print("Get %d intervals" % num_intrvl)
    return oneface_intrvlcol


def make_supercut(supercut_intervals, out_path = '/app/result/supercut/supercut.mp4'):
    def download_video_clip(i):
        video_id, sfid, efid = supercut_intervals[i]
        video = Video.objects.filter(id=video_id)[0]
        clip_path = video.download(segment=(1.*sfid/video.fps, 1.*efid/video.fps))
        return clip_path
    
    # make supercut video 
    clip_paths = par_for(download_video_clip, [i for i in range(len(supercut_intervals))])
    concat_videos(clip_paths, out_path)
    
    
def same_person_one_sentence(person_name, sentence):
    videos = Video.objects.filter(threeyears_dataset=True)
    video_ids = [video.id for video in videos]
    
    person_intrvlcol = get_person_intrvlcol(person_name, video_ids)
    words = [word.upper() for word in sentence.split(' ')] 
    supercut_intervals_all = []
    for word in tqdm(words):
        phrase_intrvlcol = get_caption_intrvlcol(word, person_intrvlcol.get_allintervals().keys())
        person_with_phrase_intrvlcol = person_intrvlcol.overlaps(phrase_intrvlcol)
        relevant_shots = get_relevant_shots(person_with_phrase_intrvlcol)
        oneface_intrvlcol = get_oneface_intrvlcol(relevant_shots)
        person_alone_intrvlcol = person_with_phrase_intrvlcol.overlaps(oneface_intrvlcol)

        print("Get {} intervals for word {}".format(count_intervals(person_alone_intrvlcol), word))

        supercut_intervals = []
        for video_id, intrvllist in person_alone_intrvlcol.intervals.items():
            for interval in intrvllist.get_intervals():
                supercut_intervals.append((video_id, interval.get_start(), interval.get_end()))
        supercut_intervals_all.append(supercut_intervals)
    return supercut_intervals_all


def multi_person_one_phrase(phrase):
    videos = Video.objects.filter(threeyears_dataset=True)
    video_ids = [video.id for video in videos]
    
    phrase_intrvlcol = get_caption_intrvlcol(phrase.upper(), video_ids)
    supercut_intervals = []
    for video, intrvllist in phrase_intrvlcol.intervals.items():
        for interval in intrvllist.get_intervals():
            supercut_intervals.append((video, interval.get_start(), interval.get_end()))
    return supercut_intervals