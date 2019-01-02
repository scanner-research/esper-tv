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
from esper.prelude import *

import random
import os
import pickle
import tempfile
from tqdm import tqdm
import multiprocessing
from pydub import AudioSegment


# ============== Help functions ==============    
def second2time(second, sep=','):
    h, m, s, ms = int(second) // 3600, int(second % 3600) // 60, int(second) % 60, int((second - int(second)) * 1000)
    return '{:02d}:{:02d}:{:02d}{:s}{:03d}'.format(h, m, s, sep, ms)


def count_intervals(intrvlcol):
    num_intrvl = 0
    for intrvllist in intrvlcol.get_allintervals().values():
        num_intrvl += intrvllist.size()
    return num_intrvl


def intrvlcol2list(intrvlcol):
    interval_list = []
    for video_id, intrvllist in intrvlcol.intervals.items():
        for interval in intrvllist.get_intervals():
            interval_list.append((video_id, interval.get_start(), interval.get_end()))
    return interval_list


def stitch_video_temporal(intervals, out_path):
    def download_video_clip(i):
        video_id, sfid, efid = intervals[i]
        video = Video.objects.filter(id=video_id)[0]
        clip_path = video.download(segment=(1.*sfid/video.fps, 1.*efid/video.fps))
        return clip_path
    
    # make supercut video 
    clip_paths = par_for(download_video_clip, [i for i in range(len(intervals))])
    concat_videos(clip_paths, out_path)

    
def make_montage_t(args):
    (videos, frames, kwargs) = args
    return make_montage(videos, frames, **kwargs)    

def stitch_video_spatial(intervals, out_path, align=False, **kwargs):
    def gcd(a, b):
        return gcd(b, a % b) if b else a

    id2video = {video_id: Video.objects.filter(id=video_id)[0] for (video_id, sfid, efid) in intervals}
    videos = [id2video[video_id] for (video_id, sfid, efid) in intervals]
    fps = reduce(gcd, [int(math.ceil(v.fps)) for v in videos])
#     print('gcd fps', fps)

    nframes_list = []
    for (video_id, sfid, efid) in intervals:
        n = (efid - sfid) / math.ceil(id2video[video_id].fps) * fps
        nframes_list.append(int(n))
    if align:
        nframes = min(nframes_list)
    else:
        nframes = max(nframes_list)
    
    kwargs_list = []
    for i in range(nframes):
        frames = [int(math.ceil(id2video[video_id].fps) / fps) * i + sfid for (video_id, sfid, efid) in intervals]
#         print(frames)
        kwargs_list.append((videos, frames, kwargs))
    
    first = make_montage_t(kwargs_list[0])
    vid = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*'XVID'), fps,
                          (first.shape[1], first.shape[0]))
    frames = par_for(
        make_montage_t, kwargs_list,
        workers=16,
        process=True)
    for frame in tqdm(frames):
        vid.write(frame)

    vid.release()
    

def mix_audio(intervals, out_path, decrease_volume=3, align=False):
    def download_audio_clip(i):
        video_id, sfid, efid = intervals[i]
        video = Video.objects.filter(id=video_id)[0]
        video_path = video.download(segment=(1.*sfid/video.fps, 1.*efid/video.fps))
        return AudioSegment.from_file(video_path, format="mp4")
    
    durations = []
    for (video_id, sfid, efid) in intervals:
        video = Video.objects.filter(id=video_id)[0]
        d = (efid - sfid) / video.fps
        durations.append(d)
    max_duration, min_duration = max(durations), min(durations)
    print("Max duration %.3f s" % max_duration)
    
    audios = par_for(download_audio_clip, [i for i in range(len(intervals))])
    if not align: 
        audio_mix = AudioSegment.silent(duration=int(max_duration*1000))
    else:
        audio_mix = AudioSegment.silent(duration=int(min_duration*1000))
        audios = [audio.speedup(playback_speed=durations[i] / min_duration) for i, audio in enumerate(audios)]
        
    for audio in audios:
        audio_mix = audio_mix.overlay(audio)
    audio_mix = audio_mix - decrease_volume
    audio_mix.export(out_path, format="wav")
    
    
def merge_video_audio(video_path, audio_path, out_path):
    avi_path = '/app/result/montage/merge.avi'
    cmd_merge = 'ffmpeg -y -i {} -i {} -c:v copy -c:a aac -strict experimental {}' \
            .format(video_path, audio_path, avi_path)
    cmd_avi2mp4 = 'ffmpeg -y -i {} -c:a aac -b:a 128k -c:v libx264 -crf 23 {}'.format(avi_path, out_path)
    os.system(cmd_merge)
    os.system(cmd_avi2mp4)
    
    
# ============== Queries with rekall ==============    
def get_person_intrvlcol(person_name, video_ids=None):
    if video_ids is None:
        videos = Video.objects.filter(threeyears_dataset=True)
        video_ids = [video.id for video in videos]
    
    all_faces = FaceIdentity.objects.annotate(height=F("face__bbox_y2") - F("face__bbox_y1"))
    if not video_ids is None:
        all_faces = all_faces.filter(face__shot__video_id__in=video_ids)
        
    person_intrvllists = qs_to_intrvllists(
        all_faces
            .filter(identity__name=person_name.lower(), 
                    probability__gt=0.99,
                    height__gte=0.3)
            .annotate(video_id=F("face__shot__video_id"))
            .annotate(shot_id=F("face__shot_id"))
            .annotate(min_frame=F("face__shot__min_frame"))
            .annotate(max_frame=F("face__shot__max_frame")),
        schema={
            'start': 'min_frame',
            'end': 'max_frame',
            'payload': 'shot_id'
        })
    person_intrvlcol = VideoIntervalCollection(person_intrvllists)
    print("Get {} intervals for person {}".format(count_intervals(person_intrvlcol), person_name))
    return person_intrvlcol


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
    phrase_intrvlcol = VideoIntervalCollection(phrase_intrvllists)
    print('Get {} intervals for phrase \"{}\"'.format(count_intervals(phrase_intrvlcol), phrase))
    return phrase_intrvlcol


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
    print("Get %d relevant one face intervals" % num_intrvl)
    return oneface_intrvlcol

def get_person_alone_phrase_intrvlcol(person_intrvlcol, phrase):
    phrase_intrvlcol = get_caption_intrvlcol(phrase, person_intrvlcol.get_allintervals().keys())
    person_phrase_intrvlcol = person_intrvlcol.overlaps(phrase_intrvlcol)
    relevant_shots = get_relevant_shots(person_phrase_intrvlcol)
    oneface_intrvlcol = get_oneface_intrvlcol(relevant_shots)
    person_alone_phrase_intrvlcol = person_phrase_intrvlcol.overlaps(oneface_intrvlcol)
    
    print('Get {} person alone intervals for phrase \"{}\"'.format(count_intervals(person_alone_phrase_intrvlcol), phrase))
    return person_alone_phrase_intrvlcol
    
    
# ============== Applications ==============    
def same_person_one_sentence(person, sentence):
    if type(person) == str:
        person_intrvlcol = get_person_intrvlcol(person_name)
    else:
        person_intrvlcol = person
    words = [word.upper() for word in sentence.split(' ')]

    supercut_candidates = []
    segments = []
    phrase2interval = {}
    num_concat = 0
    for idx, word in tqdm(enumerate(words)):
        if num_concat > 0:
            num_concat -= 1
            continue
            
        phrase = word
        candidates = None
        while idx + num_concat < len(words):
            if num_concat > 0:
                phrase += ' ' + words[idx + num_concat]
            # skip short word for long phrase
            if len(phrase) < 4:
                num_concat += 1
                continue
            
            if phrase in phrase2interval:
                candidates = phrase2interval[phrase]
                segment = phrase
                num_concat += 1
            else:
                person_alone_phrase_intrvlcol = get_person_alone_phrase_intrvlcol(person_intrvlcol, phrase)
                num_intervals = count_intervals(person_alone_phrase_intrvlcol)
                if num_intervals > 3:
                    candidates = intrvlcol2list(person_alone_phrase_intrvlcol)
                    phrase2interval[phrase] = candidates
                    segment = phrase
                    num_concat += 1
                else:
                    num_concat = num_concat - 1 if num_concat != 0 else 0
                    break
        # make up for short word            
        if candidates is None and len(word) < 4:
            person_alone_phrase_intrvlcol = get_person_alone_phrase_intrvlcol(person_intrvlcol, word)
            num_intervals = count_intervals(person_alone_phrase_intrvlcol)
            if num_intervals > 0:
                candidates = intrvlcol2list(person_alone_phrase_intrvlcol)
                phrase2interval[word] = candidates
                segment = word
        if not candidates is None:
            supercut_candidates.append(candidates)
            segments.append(segment)
            
    print("Sentence segments: ", segments)
    return supercut_candidates


def multi_person_one_phrase(phrase, with_faces=False, limit=None):
    videos = Video.objects.filter(threeyears_dataset=True)
    video_ids = [video.id for video in videos]
    phrase_intrvlcol = get_caption_intrvlcol(phrase.upper(), video_ids)

    
    def fn(i):
        faces = Face.objects.filter(shot__video__id=video_id, shot__min_frame__lte=i.start, shot__max_frame__gte=i.end)
        return len(faces) > 0
            
    if with_faces:
        intrvlcol_withface = {}
        for video_id, intrvllist in phrase_intrvlcol.intervals.items():
            intrvllist_withface = intrvllist.filter(fn)
            if intrvllist_withface.size() > 0:
                intrvlcol_withface[video_id] = intrvllist_withface
            if not limit is None and len(intrvlcol_withface) == limit:
                phrase_intrvlcol = VideoIntervalCollection(intrvlcol_withface)
                break
    return intrvlcol2list(phrase_intrvlcol)
