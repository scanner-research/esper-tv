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
import multiprocessing as mp


# ============== Basic help functions ==============    

def par_for_process(function, param_list, num_workers=32):
    num_jobs = len(param_list)
    print("Total number of %d jobs" % num_jobs)
    if num_jobs == 0:
        return 
    if num_jobs <= num_workers:
        num_workers = num_jobs
        num_jobs_p = 1
    else:
        num_jobs_p = math.ceil(1. * num_jobs / num_workers)
    print("{} workers and {} jobs per worker".format(num_workers, num_jobs_p))
    
    process_list = []
    for i in range(num_workers):
        if i != num_workers - 1:
            param_list_p = param_list[i*num_jobs_p : (i+1)*num_jobs_p]
        else:
            param_list_p = param_list[i*num_jobs_p : ]
        p = mp.Process(target=function, args=(param_list_p,))
        process_list.append(p)

    for p in process_list:
        p.start()
#     for p in process_list:
#         p.join()

        
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


# ============== Video audio operations ==============    

def stitch_video_temporal(intervals, out_path, out_duration=None, dilation=None, speed=None):
    intervals = intervals.copy()
    def download_video_clip(i):
        video_id, sfid, efid = intervals[i][:3]
        video = Video.objects.filter(id=video_id)[0]
        start, end = 1. * sfid / video.fps, 1. * efid / video.fps
        video_path = video.download(segment=(start, end))
        if i == len(intervals) - 1 and not dilation is None: 
            video_path = mute_video(video_path)
        return video_path
    
    in_duration = sum([i[-1] for i in intervals])
    if dilation < 0.1:
        dilation = None
    if not dilation is None:
        video_id, sfid, efid = intervals[-1][:3]
        video = Video.objects.filter(id=video_id)[0]
        intervals.append((video_id, efid, efid + int(dilation*video.fps), dilation))
    
    # download clips for each phrase 
    clip_paths = par_for(download_video_clip, [i for i in range(len(intervals))])
    
    # concat phrase clips
    tmp_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
    if dilation is None and len(intervals) > 1:
        concat_videos(clip_paths, tmp_path)
    elif not dilation is None and len(intervals) > 2:
        concat_videos(clip_paths[:-1], tmp_path)
    else:
        tmp_path = clip_paths[0]
    # global change sentence speed 
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
    # concat the dilation clip
    if not dilation is None:
        concat_videos([tmp_path, clip_paths[-1]], out_path)
    else:
        shutil.move(tmp_path, out_path)

    
def make_montage_t(args):
    (videos, frames, kwargs) = args
    return make_montage(videos, frames, **kwargs)    

def stitch_video_spatial(intervals, out_path, align=False, **kwargs):
    '''
    Stitch video into live montage
    
    @intervals: list of (video_id, start_frame_id, end_frame_id)
    @out_path: output video path
    @align: if true, adjust the speed of each video clip, so that each clip's duration equals to the median of them
    @kwargs: params for calling make_montage() 
    '''
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
    
    
def mute_video(video_path):
    audio = AudioSegment.from_file(video_path, format='mp4')
    silence = AudioSegment.silent(duration=len(audio))
    silence_path = tempfile.NamedTemporaryFile(suffix='.wav').name
    silence.export(silence_path, format='wav')
    out_path = tempfile.NamedTemporaryFile(suffix='.mp4').name
    replace_audio(video_path, silence_path, out_path)
    return out_path


def create_silent_clip(person_intrvlcol, out_path, out_duration):
    intervals = []
    for video_id, intrvllist in intrvlcol.get_allintervals().items():
        video = Video.objects.filter(id=video_id)[0]
        for i in intrvllist.get_intervals():
            duration = (i.end - i.start) / video.fps
            if duration > out_duration:
                intervals.append((video, i.start / video.fps, i.end / video.fps))
            if len(intervals) > 10:
                break
    video, start, end = random.choice(intervals)        
    video_path = video.download(segment=(start, start + out_duration))
    video_path = mute_video(video_path)
    return video_path
    
        
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


def get_person_alone_phrase_intervals(person_intrvlcol, phrase, filter_still=True):
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
    if not filter_still:
        return intervals
    intervals_nostill = filter_still_image_parallel(intervals)
    intervals_final = intervals_nostill if len(intervals_nostill) > 0 else intervals
    
    # Todo: always give at least one output 
    print('Get {} person alone intervals for phrase \"{}\"'.format(len(intervals_final), phrase))
    return intervals_final
    
    
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
            text = re.sub('\[.*\]', ' ', sub.text)
            text = re.sub('\(.*\)', ' ', text)
            text = re.sub('[^\'0-9a-zA-Z]+', ' ', text)
            words = []
            for word in text.split(' '): 
                if word != '':
                    if not is_word_in_lexicon(word.upper()):
                        print('Word \"{}\" not exist in Lexcion!'.format(word))
                    else:
                        words.append(word.upper())
#             print("Extracted words from lyrics", words)
            
            lyrics.append((words, time2second(tuple(sub.start)[:4]), time2second(tuple(sub.end)[:4])))
        self.lyrics = lyrics

        # load cache
        cache_path = '/app/result/supercut/cache/{}.pkl'.format(self.person_name)
        cache = pickle.load(open(cache_path, 'rb')) if os.path.exists(cache_path) else {'candidates':{}, 'selection':{}}
        self.phrase2candidates, self.phrase2selection = cache['candidates'], cache['selection']
        self.cache_path = cache_path
    
    def search_phrases(self, phrase_list):
        for phrase in phrase_list:
            print("searching for \"{}\" ...".format(phrase))
            self.phrase2candidates_tmp[phrase] = get_person_alone_phrase_intervals(self.person_intrvlcol, 
                                                                                   phrase, filter_still=False)
    
#     def search_candidates_parallel(self, workers=16):
#         # collect all words
#         words_all = set()
#         for idx, (sentence, start, end) in enumerate(self.lyrics):
#             words = [word.upper() for word in sentence.replace(',', '').replace('.', '').replace('!', '').split(' ')]
#             for w in words:
#                 # todo: add more phrase
#                 words_all.add(w)
#         words_all = sorted(words_all)
#         print(words_all)
        
#         # search all word intervals
#         self.phrase2intrvlcol = {}
#         for word in words_all:
#             self.phrase2intrvlcol[word] = get_caption_intrvlcol(word, self.person_intrvlcol.get_allintervals().keys())
        
#         self.phrase2candidates_tmp = {}
#         par_for_process(self.search_phrases, words_all, num_workers=16)
        
#         # filter still images
#         for word, intervals in enumerate(zip(words_all, pre_candidates)):
#             intervals_nostill = filter_still_image_parallel(intervals)
#             intervals_final = intervals_nostill if len(intervals_nostill) > 0 else intervals
#             print('Get {} person alone intervals for phrase \"{}\"'.format(len(intervals_final), word))
#             self.phrase2candidates[word] = intervals_final
        
    def search_candidates(self):
        segments_list = []
        candidates_list = []
        for idx, (words, start, end) in enumerate(self.lyrics):
            segments, candidates = single_person_one_sentence(self.person_intrvlcol, words, self.phrase2candidates)
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
        for idx, (words, start, end) in enumerate(self.lyrics):
            selections = self.selections_list[idx]
            tmp_path = '/app/result/supercut/tmp/{}-{}-{}.mp4'.format(self.person_name, self.song_name, idx)
            dilation = self.lyrics[idx+1][1] - end if idx != len(self.lyrics) - 1 else 1
            if len(words) > 0:
                stitch_video_temporal(selections, tmp_path, out_duration=None, dilation=dilation)
            else:
                create_silent_clip(tmp_path, out_duration=end - start + dilation)
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
    

def single_person_one_sentence(person_intrvlcol, words, phrase2interval=None, concat_word=4):
    
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
                
            print('{} Searching for phrase \"{}\" {}'.format('=' * 10, phrase, '=' * 10))    
                
            if phrase in phrase2interval:
                print("Found in cache")
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
            print('{} Searching for phrase \"{}\" {}'.format('=' * 10, phrase, '=' * 10))    
            if word in phrase2interval:
                print("Found in cache")
                candidates = phrase2interval[word]
                segment = word
            else:
                person_alone_phrase_intervals = get_person_alone_phrase_intervals(person_intrvlcol, word)
                num_intervals = len(person_alone_phrase_intervals)
                if num_intervals > 0:
                    candidates = person_alone_phrase_intervals
                    phrase2interval[word] = candidates
                    segment = word
        # if really cannot find the word, use clips from other person instead
        if candidates is None:
            phrase_intrvlcol = get_caption_intrvlcol(word)
            candidates = intrvlcol2list(phrase_intrvlcol)
            segment = word
        if not candidates is None:
            supercut_candidates.append(candidates)
            segments.append(segment)
            
    print("-------- Searched words: ", words)        
    print("-------- Final segments: ", segments)
    return segments, supercut_candidates


def multi_person_one_phrase(phrase, filters={}):
    '''
    Get all intervals which the phrase is being said
    
    @phrase: input phrase to be searched
    @filters: 
        'with_face': must contain exactly one face
        'gender': filter by gender
        'limit': number of output intervals
    '''
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

if __name__ == "__main__":
    
    # Supercut of "Make Amercia Great Again"
    phrase = "make america great again"
    filters={ 
        'with_face': True,
        'gender': 'M'
    }
    supercut_intervals_all = multi_person_one_phrase(phrase, filters)
    
    supercut_intervals = auto_select_candidates(supercut_intervals_all, num_sample=64, filter='random')
    
    # App1: temporal supercut 
    stitch_video_temporal(supercut_intervals, out_path='/app/result/supercut/make_america_great_again.mp4')
    
    # App2: spatial supercut
    video_path = '/app/result/montage/test_video.avi'
    audio_path = '/app/result/montage/test_audio.wav'

    stitch_video_spatial(supercut_intervals, out_path=video_path, align=False, 
                     width=1080, num_cols=8, target_height = 1080 // 8 * 9 // 16)

    mix_audio(supercut_intervals, out_path=audio_path, decrease_volume=5, align=False)
    
    merge_video_audio(video_path, audio_path, '/app/result/montage/make_america_great_again.mp4')