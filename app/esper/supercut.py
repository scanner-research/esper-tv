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

# import query sets
from query.models import Video, Face, FaceIdentity, FaceGender
from django.db.models import F, Q

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
from pydub import AudioSegment
import pysrt
import re
import cv2
import shutil


# ============== Help functions ==============    
def second2time(second, sep=','):
    h, m, s, ms = int(second) // 3600, int(second % 3600) // 60, int(second) % 60, int((second - int(second)) * 1000)
    return '{:02d}:{:02d}:{:02d}{:s}{:03d}'.format(h, m, s, sep, ms)


def time2second(time):
        return time[0]*3600 + time[1]*60 + time[2] + time[3] / 1000.0

    
def count_intervals(intrvlcol):
    num_intrvl = 0
    for intrvllist in intrvlcol.get_allintervals().values():
        num_intrvl += intrvllist.size()
    return num_intrvl


def intrvlcol2list(intrvlcol, with_duration=True):
    interval_list = []
    for video_id, intrvllist in intrvlcol.get_allintervals().items():
        if with_duration:
            video = Video.objects.filter(id=video_id)[0]
        for i in intrvllist.get_intervals():
            if with_duration:
                interval_list.append((video_id, i.start, i.end, (i.end - i.start) / video.fps))
            else:
                interval_list.append((video_id, i.start, i.end))
    print("Get {} intervals from interval collection".format(len(interval_list)))
    return interval_list


def interval2result(intervals):
    materialized_result = [
        {'video': video_id,
#             'track': t.id,
         'min_frame': sfid,
         'max_frame': efid }
        for video_id, sfid, efid, duration in intervals ]
    count = len(intervals)
    groups = [{'type': 'flat', 'label': '', 'elements': [r]} for r in materialized_result]
    return {'result': groups, 'count': count, 'type': 'Video'}


def auto_select_candidates(intervals, num_sample=1, range=(0.5, 1.5), filter='random'):
    durations = [i[-1] for i in intervals]
    median = np.median(durations)
    intervals_regular = [i for i in intervals if i[-1] > range[0] * median and i[-1] < range[1] * median]
    if len(intervals_regular) == 0:
        intervals_regular = [i for i in intervals if i[-1] > 0.5 * median and i[-1] < 1.5 * median]
    # Todo: if regular intervals are not enough
    if filter == 'random':
        if num_sample == 1:
            return random.choice(intervals_regular)
        else:
            return random.sample(intervals_regular, num_sample)
    elif filter == 'longest':
        durations_regular = [i[-1] for i in intervals_regular]
        return intervals_regular[np.argmax(durations_regular)]

    
def stitch_video_temporal(intervals, out_path, out_duration=None, dilation=None, speed=None):
    intervals = intervals.copy()
    def download_video_clip(i):
        video_id, sfid, efid = intervals[i][:3]
        video = Video.objects.filter(id=video_id)[0]
        start, end = 1. * sfid / video.fps, 1. * efid / video.fps
        video_path = video.download(segment=(start, end))
        if i == len(intervals) - 1 and not dilation is None: 
            video_path = add_fade_out(video_path)
        return video_path
    
    in_duration = sum([i[-1] for i in intervals])
    if dilation < 0.1:
        dilation = None
    if not dilation is None:
        video_id, sfid, efid = intervals[-1][:3]
        video = Video.objects.filter(id=video_id)[0]
        intervals.append((video_id, efid, efid + int(dilation*video.fps), dilation))
    
    # make supercut video 
    clip_paths = par_for(download_video_clip, [i for i in range(len(intervals))])
    # concat phrase clips with speed change if need
    if len(intervals) > 2:
        tmp_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
        concat_videos(clip_paths[:-1], tmp_path)
    else:
        tmp_path = clip_paths[0]
    if not out_duration is None:    
        speed = in_duration / out_duration
        print(in_duration, out_duration, speed)
        speed = max(0.5, speed)
        speed = min(2.0, speed)
        tmp_path2 = tempfile.NamedTemporaryFile(suffix='.mp4').name
        cmd = 'ffmpeg -y -i {} -filter_complex "[0:v]setpts={}*PTS[v];[0:a]atempo={}[a]" -map "[v]" -map "[a]" {}' \
              .format(tmp_path, 1 / speed, speed, tmp_path2)
        os.system(cmd)
        tmp_path = tmp_path2
    
    if not dilation is None:
        concat_videos([tmp_path, clip_paths[-1]], out_path)
    else:
        shutil.move(tmp_path, out_path)

    
def make_montage_t(args):
    (videos, frames, kwargs) = args
    return make_montage(videos, frames, **kwargs)    

def stitch_video_spatial(intervals, out_path, align=False, **kwargs):
    def gcd(a, b):
        return gcd(b, a % b) if b else a

    id2video = {i[0]: Video.objects.filter(id=i[0])[0] for i in intervals}
    videos = [id2video[i[0]] for i in intervals]
    fps = reduce(gcd, [int(math.ceil(v.fps)) for v in videos])
#     print('gcd fps', fps)

    nframes = []
    for i in intervals:
        video_id, sfid, efid = i[:3]
        n = (efid - sfid) / math.ceil(id2video[video_id].fps) * fps
        nframes.append(int(n))
    if align:
        nframe_mix = np.median(nframes).astype(int)
    else:
        nframe_mix = max(nframes)
    
    kwargs_list = []
    for i in range(nframe_mix):
        frames = []
        for idx, intrv in enumerate(intervals):
            video_id, sfid, efid = intrv[:3]
            fid_shift = int(math.ceil(id2video[video_id].fps) / fps) * i
            if align:
                fid_shift = int(round(1. * fid_shift / nframe_mix * nframes[idx])) 
            frames.append(fid_shift + sfid)
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
        video_id, sfid, efid = intervals[i][:3]
        video = Video.objects.filter(id=video_id)[0]
        video_path = video.download(segment=(1.*sfid/video.fps, 1.*efid/video.fps))
        
        if align:
            speed = durations[i] / duration_mix
            speed = max(0.5, speed)
            speed = min(2.0, speed)
#             print(speed)
            tmp_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
            cmd = 'ffmpeg -i {} -filter:a "atempo={}" -vn {}'.format(video_path, speed, tmp_path)
#             print(cmd)
            os.system(cmd)
            video_path = tmp_path
        return AudioSegment.from_file(video_path, format="mp4")
    
    durations = []
    for i in intervals:
        video_id, sfid, efid = i[:3]
        video = Video.objects.filter(id=video_id)[0]
        d = (efid - sfid) / video.fps
        durations.append(d)
    duration_mix = np.median(durations)
    print("Audio clip duration: min=%.3fs max=%.3fs" % (min(durations), max(durations)))
    
    audios = par_for(download_audio_clip, [i for i in range(len(intervals))])
    audio_mix = AudioSegment.silent(duration=int(duration_mix*1000))
    for audio in audios:
        audio_mix = audio_mix.overlay(audio)
    audio_mix = audio_mix - decrease_volume
    audio_mix.export(out_path, format="wav")
    
    
def concat_video_audio(video_path, audio_path, out_path):
    tmp_path = tempfile.NamedTemporaryFile(suffix='.avi').name
    cmd_merge = 'ffmpeg -y -i {} -i {} -c:v copy -c:a aac -strict experimental {}' \
            .format(video_path, audio_path, tmp_path)
    cmd_avi2mp4 = 'ffmpeg -y -i {} -c:a aac -b:a 128k -c:v libx264 -crf 23 {}'.format(tmp_path, out_path)
    os.system(cmd_merge)
    os.system(cmd_avi2mp4)

    
# def concat_videos_simple(paths, out_path):
#     tmp_path = tempfile.NamedTemporaryFile(suffix='.txt').name
#     file = open(tmp_path, 'w')
#     for p in paths:
#         file.write('file ' + "\'" + p + "\'" + '\n')
#     file.close()
#     cmd = 'ffmpeg -y -safe 0 -f concat -i {} -c copy {}'.format(tmp_path, out_path)
#     os.system(cmd)
    
    
# def filter_still_images(intrvlcol, limit=25):
#     def fn(i):
#         fid = (i.start + i.end) // 2
#         frame_first = load_frame(video, fid, [])
#         frame_second = load_frame(video, fid + 1, [])
#         diff = 1. * np.sum(frame_first - frame_second) / frame_first.size
# #         print(video.id, fid, diff)
#         return diff > 15
    
#     intrvlcol_nostill = {}
#     for video_id, intrvllist in intrvlcol.get_allintervals().items():
#         video = Video.objects.filter(id=video_id)[0]
#         intrvllist_nostill = intrvllist.filter(fn) 
#         if intrvllist_nostill != []:
#             intrvlcol_nostill[video_id] = intrvllist_nostill
#         if len(intrvlcol_nostill) > limit:
#             break
#     return VideoIntervalCollection(intrvlcol_nostill)


def filter_still_image_t(interval):
    video_id, sfid, efid = interval[:3]
    video = Video.objects.filter(id=video_id)[0]
    fid = (sfid + efid) // 2
    frame_first = load_frame(video, fid, [])
    frame_second = load_frame(video, fid + 1, [])
    diff = 1. * np.sum(frame_first - frame_second) / frame_first.size
#     print(video.id, fid, diff)
    return diff > 15

def filter_still_image_parallel(intervals, limit=100):
    durations = [i[-1] for i in intervals]
    if limit < len(intervals):
#         intervals = random.sample(intervals, limit)
        intervals = [intervals[idx] for idx in np.argsort(durations)[-limit : ]]
    filter_res = par_for(filter_still_image_t, intervals)
    return [intrv for i, intrv in enumerate(intervals) if filter_res[i]]


def replace_audio(video_path, audio_path, out_path):
    cmd = 'ffmpeg -y -i {} -i {} -c:v copy -map 0:v:0 -map 1:a:0 {}' \
          .format(video_path, audio_path, out_path)
    os.system(cmd)
    

def add_bgm(video_path, bgm_path, out_path, bgm_decrease=2):
    audio_ori = AudioSegment.from_file(video_path, format='mp4')
    audio_bgm = AudioSegment.from_file(bgm_path, format=bgm_path[-3:])
    audio_mix = audio_ori.overlay(audio_bgm - bgm_decrease)
    tmp_path = tempfile.NamedTemporaryFile(suffix='.wav').name
    audio_mix.export(tmp_path, format='wav')
    replace_audio(video_path, tmp_path, out_path)
    
    
def add_fade_out(video_path):
    audio = AudioSegment.from_file(video_path, format='mp4')
    silence = AudioSegment.silent(duration=len(audio))
    silence_path = tempfile.NamedTemporaryFile(suffix='.wav').name
    silence.export(silence_path, format='wav')
    out_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
    replace_audio(video_path, silence_path, out_path)
    return out_path

        
# ============== Queries with rekall ==============    
def get_person_intrvlcol(person_name, **kwargs):
#     if video_ids is None:
#         videos = Video.objects.filter(threeyears_dataset=True)
#         video_ids = [video.id for video in videos]
    
#     faceIDs = FaceIdentity.objects \
#               .annotate(video_id=F("face__frame__video_id")) \
#               .annotate(shot_boundary=F("face__frame__shot_boundary"))
            
#     if not video_ids is None:
#         faceIDs = faceIDs.filter(video_id__in=video_ids, shot_boundary=True) \
    
    if kwargs['labeler'] == 'old': # old labeler model
        faceIDs = FaceIdentity.objects \
                  .exclude(face__shot__isnull=True) \
                  .filter(Q(labeler__name='face-identity-converted:'+person_name.lower()) | 
                          Q(labeler__name='face-identity:'+person_name.lower()) ) \
                  .filter(probability__gt=0.9) \
                  .annotate(height=F("face__bbox_y2") - F("face__bbox_y1"))   
        if 'large_face' in kwargs:
            faceIDs = faceIDs.filter(height__gte=0.3)
    
        person_intrvllists = qs_to_intrvllists(
            faceIDs.annotate(video_id=F("face__shot__video_id"))
                   .annotate(shot_id=F("face__shot_id"))
                   .annotate(min_frame=F("face__shot__min_frame"))
                   .annotate(max_frame=F("face__shot__max_frame")),\
            schema={
                'start': 'min_frame',
                'end': 'max_frame',
                'payload': 'shot_id'
            })
        person_intrvlcol = VideoIntervalCollection(person_intrvllists)
    else: # new labeler model
        faceIDs = FaceIdentity.objects \
                  .filter(face__frame__shot_boundary=False) \
                  .filter(Q(labeler__name='face-identity-converted:'+person_name.lower()) | 
                          Q(labeler__name='face-identity:'+person_name.lower()) ) \
                  .filter(probability__gt=0.9) \
                  .annotate(height=F("face__bbox_y2") - F("face__bbox_y1"))   
        if 'large_face' in kwargs:
            faceIDs = faceIDs.filter(height__gte=0.3)
    
        person_intrvllists_raw = qs_to_intrvllists(
            faceIDs.annotate(video_id=F("face__frame__video_id"))
                   .annotate(frame_id=F("face__frame__number"))
                   .annotate(min_frame=F("face__frame__number"))
                   .annotate(max_frame=F("face__frame__number") + 1),\
            schema={
                'start': 'min_frame',
                'end': 'max_frame',
                'payload': 'frame_id'
            })
        # dilate and coalesce
        person_intrvllists = {}
        for video_id, intrvllist in person_intrvllists_raw.items():
            video = Video.objects.filter(id=video_id)[0]
            person_intrvllists[video_id] = intrvllist.dilate(int(video.fps*1.6)).coalesce()
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

def get_person_alone_phrase_intervals(person_intrvlcol, phrase):
    phrase_intrvlcol = get_caption_intrvlcol(phrase, person_intrvlcol.get_allintervals().keys())
    person_phrase_intrvlcol_raw = person_intrvlcol.overlaps(phrase_intrvlcol)
    # only keep intervals which is the same before overlap
    person_phrase_intrvlcol = person_phrase_intrvlcol_raw.filter_against(
        phrase_intrvlcol,
        predicate = equal() )
    
    relevant_shots = get_relevant_shots(person_phrase_intrvlcol)
    oneface_intrvlcol = get_oneface_intrvlcol(relevant_shots)
    person_alone_phrase_intrvlcol = person_phrase_intrvlcol.overlaps(oneface_intrvlcol)
    
    # run optical flow to filter out still images
    intervals = intrvlcol2list(person_alone_phrase_intrvlcol)
    intervals_nostill = filter_still_image_parallel(intervals)
    intervals_final = intervals_nostill if len(intervals_nostill) > 0 else intervals
    
    # Todo: always give at least one output 
    print('Get {} person alone intervals for phrase \"{}\"'.format(len(intervals_final), phrase))
    return intervals_final
    
    
# ============== Applications ============== 
class SinglePersonSing:
    def __init__(self, person_name, lyric_path, person_intrvlcol=None):
        if person_intrvlcol is None:
            person_intrvlcol = get_person_intrvlcol(person_name, large_face=True, labeler='old')
        self.person_name = person_name.replace(' ', '_')
        self.person_intrvlcol = person_intrvlcol

        # load lyrics
        self.song_name = os.path.basename(lyric_path).replace('.srt', '')
        lyrics = []
        subs = pysrt.open(lyric_path)
        for sub in subs:
            lyrics.append((sub.text, time2second(tuple(sub.start)[:4]), time2second(tuple(sub.end)[:4])))
        self.lyrics = lyrics

        # load cache
        cache_path = '/app/result/supercut/cache/{}.pkl'.format(self.person_name)
        cache = pickle.load(open(cache_path, 'rb')) if os.path.exists(cache_path) else {'candidates':{}, 'selection':{}}
        self.phrase2candidates, self.phrase2selection = cache['candidates'], cache['selection']
        self.cache_path = cache_path
    
    def search_candidates(self):
        segments_list = []
        candidates_list = []
        for idx, (sentence, start, end) in enumerate(self.lyrics):
            segments, candidates = single_person_one_sentence(self.person_intrvlcol, sentence, self.phrase2candidates)
            segments_list.append(segments)
            candidates_list.append(candidates)
            self.dump_cache()
        self.segments_list = segments_list
        self.candidates_list = candidates_list
    
    def select_candidates(self, human_selection=False, duplicate_selection=True, redo_selection=False):
        self.selections_list = []
        if not human_selection:
            for idx, (segments, candidates) in enumerate(zip(self.segments_list, self.candidates_list)):
                selections = [auto_select_candidates(c, range=(0.99, 1.5), filter='random') for c in candidates]
                self.selections_list.append(selections)
        else:
            self.human_select_candidates(duplicate_selection, redo_selection)
    
    def make_supercuts(self, out_path):
        cutting_paths = []
        for idx, (sentence, start, end) in enumerate(self.lyrics):
            selections = self.selections_list[idx]
            tmp_path = '/app/result/supercut/tmp/{}-{}-{}.mp4'.format(self.person_name, self.song_name, idx)
            dilation = self.lyrics[idx+1][1] - end if idx != len(self.lyrics) - 1 else 1
            stitch_video_temporal(selections, tmp_path, out_duration=None, dilation=dilation)
            cutting_paths.append(tmp_path)
            print('Concat videos for sentence \"{}\"'.format(sentence))
            
    #         if idx == 1:
    #             break
        concat_videos(cutting_paths, out_path)
        
    def dump_cache(self):
        pickle.dump({'candidates':self.phrase2candidates, 'selection':self.phrase2selection}, open(self.cache_path, 'wb'))
        
    def human_select_candidates(self, duplicate_selection, redo_selection):
        if redo_selection:
            for segments in self.segments_list:
                for phrase in segments:
                    if phrase in self.phrase2selection:
                        del self.phrase2selection[phrase]
        
        def launch_widget(idx_sentence, idx_phrase):
            if idx_phrase >= len(self.segments_list[idx_sentence]):
                idx_phrase = 0
                idx_sentence += 1
                self.selections_list.append([])
            if idx_sentence >= len(self.segments_list):
                clear_output()
                print("Finished all selections")
                return
            phrase, candidates = self.segments_list[idx_sentence][idx_phrase], self.candidates_list[idx_sentence][idx_phrase]
            
            if phrase in self.phrase2selection and duplicate_selection:
                self.selections_list[idx_sentence].append(self.phrase2selection[phrase])
                launch_widget(idx_sentence, idx_phrase + 1)
                return 
            else:
                durations = [i[-1] for i in candidates]
                candidates_sort = [candidates[idx] for idx in np.argsort(durations)[::-1]]
                result = interval2result(candidates_sort) 
            
            print('Select phrase \"{}\" for sentence \"{}\"'.format(phrase, ' '.join(self.segments_list[idx_sentence])))
            selection_widget = esper_widget(
                result, 
                disable_playback=False, jupyter_keybindings=True,
                crop_bboxes=True)

            submit_button = widgets.Button(
                layout=widgets.Layout(width='auto'),
                description='Save to database',
                disabled=False,
                button_style='danger'
            )
            def on_submit(b):
                selection = candidates_sort[selection_widget.selected[0]]
#                 print(selection_widget.selected, selection)
                self.selections_list[idx_sentence].append(selection)
                if not phrase in self.phrase2selection:
                    self.phrase2selection[phrase] = selection
                self.dump_cache()
                clear_output()
                launch_widget(idx_sentence, idx_phrase + 1)
            submit_button.on_click(on_submit)

            display(widgets.HBox([submit_button]))
            display(selection_widget)

        idx_sentence, idx_phrase = 0, 0
        self.selections_list.append([])
        launch_widget(idx_sentence, idx_phrase)
    

def single_person_one_sentence(person_intrvlcol, sentence, phrase2interval=None, concat_word=4):
    words = [word.upper() for word in sentence.replace(',', '').replace('.', '').replace('!', '').split(' ')]
    
    # Magic numbers
    SHORT_WORD = 4
    LEAST_HIT = 3
    CONCAT_WORD = concat_word
    
    supercut_candidates = []
    if phrase2interval is None:
        phrase2interval = {}
    segments = []
    num_concat = 0
    for idx, word in tqdm(enumerate(words)):
        if num_concat > 0:
            num_concat -= 1
            continue
            
        phrase = word
        candidates = None
        while idx + num_concat < len(words):
            if num_concat == CONCAT_WORD:
                num_concat -= 1
                break
            if num_concat > 0:
                phrase += ' ' + words[idx + num_concat]
            # skip short word for long phrase
            if len(phrase) < SHORT_WORD:
                num_concat += 1
                continue
            
            if candidates is None:
                LEAST_HIT = 0
            else:
                LEAST_HIT = 3
                
            if phrase in phrase2interval:
#             if phrase in phrase2interval and not phrase2interval[phrase] is None:
                if phrase2interval[phrase] is None:
                    num_concat = num_concat - 1 if num_concat != 0 else 0
                    break
                candidates = phrase2interval[phrase]
                segment = phrase
                num_concat += 1
            else:
                person_alone_phrase_intervals = get_person_alone_phrase_intervals(person_intrvlcol, phrase)
                num_intervals = len(person_alone_phrase_intervals)
                if num_intervals > LEAST_HIT:
                    candidates = person_alone_phrase_intervals
                    phrase2interval[phrase] = candidates
                    segment = phrase
                    num_concat += 1
                else:
                    phrase2interval[phrase] = None
                    num_concat = num_concat - 1 if num_concat != 0 else 0
                    break
        
        # make up for short word            
        if candidates is None and len(word) < SHORT_WORD:
            if word in phrase2interval:
                candidates = phrase2interval[word]
                segment = word
            else:
                person_alone_phrase_intervals = get_person_alone_phrase_intervals(person_intrvlcol, phrase)
                num_intervals = len(person_alone_phrase_intervals)
                if num_intervals > 0:
                    candidates = person_alone_phrase_intervals
                    phrase2interval[word] = candidates
                    segment = word
        if not candidates is None:
            supercut_candidates.append(candidates)
            segments.append(segment)
            
    print("Sentence segments: ", segments)
    return segments, supercut_candidates


def multi_person_one_phrase(phrase, filters={}):
    videos = Video.objects.filter(threeyears_dataset=True)
    video_ids = [video.id for video in videos]
    phrase_intrvlcol = get_caption_intrvlcol(phrase.upper(), video_ids)

    def fn(i):
        faces = Face.objects.filter(shot__video__id=video_id, shot__min_frame__lte=i.start, shot__max_frame__gte=i.end)
#         faces = Face.objects.filter(frame__number__gte=i.start, frame__number__lte=i.end) 
        if len(faces) != 1:
            return False
        if 'gender' in filters:
            faceGender = FaceGender.objects.filter(face__id=faces[0].id)[0]
            if faceGender.gender.name != filters['gender']:
                return False
        return True
    
    if 'with_face' in filters:
        print('Filtering with face...')
        intrvlcol_withface = {}
        for video_id, intrvllist in phrase_intrvlcol.intervals.items():
            intrvllist_withface = intrvllist.filter(fn)
            if intrvllist_withface.size() > 0:
                intrvlcol_withface[video_id] = intrvllist_withface
            if 'limit' in filters and len(intrvlcol_withface) == filters['limit']:
                break
        phrase_intrvlcol = VideoIntervalCollection(intrvlcol_withface)
#         print(len(phrase_intrvlcol))
    return intrvlcol2list(phrase_intrvlcol)
