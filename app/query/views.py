from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from timeit import default_timer as now
import django.db.models as models
from concurrent.futures import ThreadPoolExecutor
from django.views.decorators.csrf import csrf_exempt
import sys
import json
import os
import tempfile
import subprocess as sp
import shlex
import math
import pysrt
import requests
import enum
from storehouse import StorageConfig, StorageBackend
import traceback
from pprint import pprint
from esper.stdlib import *
from esper.prelude import *
import django.apps

ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATA_PATH = os.environ.get('DATA_PATH')

if ESPER_ENV == 'google':
    storage_config = StorageConfig.make_gcs_config(BUCKET)
else:
    storage_config = StorageConfig.make_posix_config()
storage = StorageBackend.make_from_config(storage_config)


# Prints and flushes (necessary for gunicorn logs)
def _print(*args):
    pprint((*args))
    sys.stdout.flush()


# Renders home page
def index(request):
    return render(request, 'index.html', {'globals': json.dumps(esper_js_globals())})


# Run search routine
def search(request):
    params = json.loads(request.body.decode('utf-8'))

    def make_error(err):
        return JsonResponse({'error': err})

    try:
        fprint('Executing')
        ############### vvv DANGER -- REMOTE CODE EXECUTION vvv ###############
        _globals = {}
        _locals = {}
        for k in globals():
            _globals[k] = globals()[k]
        for k in locals():
            _locals[k] = locals()[k]
        exec((params['code']), _globals, _locals)
        result = _locals['FN']()
        ############### ^^^ DANGER -- REMOTE CODE EXECUTION ^^^ ###############

        if not isinstance(result, dict):
            return make_error(
                'Result must be a dict {{result, count, type}}, received type {}'.format(
                    type(result)))

        if not isinstance(result['result'], list):
            return make_error('Result must be a frame list')

        return JsonResponse({'success': result_with_metadata(result)})

    except Exception:
        return make_error(traceback.format_exc())


# Get distinct values in schema
def schema(request):
    params = json.loads(request.body.decode('utf-8'))

    cls = next(m for m in django.apps.apps.get_models() if m.__name__ == params['cls_name'])
    result = [
        r[params['field']]
        for r in cls.objects.values(params['field']).distinct().order_by(params['field'])[:100]
    ]
    try:
        json.dumps(result)
    except TypeError as e:
        return JsonResponse({'error': str(e)})

    return JsonResponse({'result': result})


# Convert captions in SRT format to WebVTT (for displaying in web UI)
def srt_to_vtt(s):
    subs = pysrt.from_string(s)
    subs.shift(seconds=-5)  # Seems like TV news captions are delayed by a few seconds

    entry_fmt = '{position}\n{start} --> {end}\n{text}'

    def fmt_time(t):
        return '{:02d}:{:02d}:{:02d}.{:03d}'.format(t.hours, t.minutes, t.seconds, t.milliseconds)

    entries = [
        entry_fmt.format(
            position=i, start=fmt_time(sub.start), end=fmt_time(sub.end), text=sub.text)
        for i, sub in enumerate(subs)
    ]

    return '\n\n'.join(['WEBVTT'] + entries)


# Get subtitles for video
def subtitles(request):
    video_id = request.GET.get('video')
    video = Video.objects.get(id=video_id)

    srt = video.srt_extension
    sub_path = '/app/data/subs/orig/{}.{}.srt'.format(video.item_name(), srt)

    s = open(sub_path, 'rb').read().decode('utf-8')
    vtt = srt_to_vtt(s)

    return HttpResponse(vtt, content_type="text/vtt")


def save_frame_labels(groups):
    face_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-face')
    gender_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-gender')
    identity_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-identity')
    labeled_tag, _ = Tag.objects.get_or_create(name='handlabeled-face:labeled')
    verified_tag, _ = Tag.objects.get_or_create(name='tmp-verified')

    all_frames = [(elt['video'], elt['min_frame'], elt['objects']) for group in groups
                  for elt in group['elements']]

    frame_ids = [
        Frame.objects.get(video_id=vid, number=frame_num).id
        for (vid, frame_num, faces) in all_frames
    ]
    Frame.tags.through.objects.filter(frame__id__in=frame_ids, tag=labeled_tag).delete()
    Frame.tags.through.objects.filter(frame__id__in=frame_ids, tag=verified_tag).delete()
    Face.objects.filter(person__frame__id__in=frame_ids, labeler=face_labeler).delete()

    all_tags = []
    all_people = []
    all_faces = []
    all_genders = []
    all_identities = []
    for (vid, frame_num, faces) in all_frames:
        frame = Frame.objects.get(video_id=vid, number=frame_num)
        all_tags.append(Frame.tags.through(frame_id=frame.id, tag_id=labeled_tag.id))
        all_tags.append(Frame.tags.through(frame_id=frame.id, tag_id=verified_tag.id))
        for face in faces:
            all_people.append(Person(frame=frame))

            face_params = {
                # TODO: this became something else at some point. It interferes with saving labels.
                # 'bbox_score': 1.0,
                'labeler': face_labeler,
                'person_id': None,
                'shot_id': None,
                'background': face['background']
            }
            for k in ['bbox_x1', 'bbox_x2', 'bbox_y1', 'bbox_y2']:
                face_params[k] = face[k]
            all_faces.append(Face(**face_params))

            all_genders.append(
                FaceGender(face_id=None, gender_id=face['gender_id'], labeler=gender_labeler))

            if 'identity_id' in face:
                all_identities.append(
                    FaceIdentity(
                        face_id=None, identity_id=face['identity_id'], labeler=identity_labeler))
            else:
                all_identities.append(None)

    Frame.tags.through.objects.bulk_create(all_tags)

    Person.objects.bulk_create(all_people)

    for (p, f) in zip(all_people, all_faces):
        f.person_id = p.id
    Face.objects.bulk_create(all_faces)

    for (f, g, i) in zip(all_faces, all_genders, all_identities):
        g.face_id = f.id
        if i is not None:
            i.face_id = f.id
    FaceGender.objects.bulk_create(all_genders)
    FaceIdentity.objects.bulk_create([i for i in all_identities if i is not None])


def save_speaker_labels(groups):
    audio_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-audio')
    segment_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-audio:labeled')
    speakers = []
    segments = []
    for group in groups:
        elements = group['elements']
        frame_nums = []
        for e in elements:
            speakers.append(
                Speaker(
                    labeler=audio_labeler,
                    video_id=e['video'],
                    min_frame=e['min_frame'],
                    max_frame=e['max_frame'],
                    gender_id=e['gender_id']))
            frame_nums.append(e['min_frame'])
            frame_nums.append(e['max_frame'])

        frame_nums.sort()
        segments.append(
            Segment(
                labeler=segment_labeler,
                video_id=elements[0]['video'],
                min_frame=frame_nums[0],
                max_frame=frame_nums[-1]))

    Speaker.objects.bulk_create(speakers)
    Segment.objects.bulk_create(segments)


def save_single_identity_labels(groups):
    identity_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-identity')

    last_obj = groups[-1]['elements'][0]['objects'][0]
    if not 'identity_id' in last_obj:
        raise Exception("Missing identity on last object")

    identity = Thing.objects.get(id=last_obj['identity_id'])

    face_ids = [o['id'] for g in groups for e in g['elements'] for o in e['objects']]
    identities = [
        FaceIdentity(face_id=face_id, identity=identity, labeler=identity_labeler)
        for face_id in face_ids if face_id != -1
    ]

    FaceIdentity.objects.filter(face_id__in=face_ids, labeler=identity_labeler).delete()
    FaceIdentity.objects.bulk_create(identities)


def save_topic_segments(groups):
    segment_labeler, _ = Labeler.objects.get_or_create(name='handlabeled-topic')
    segments = []
    topics = []
    videos = set()
    for group in groups:
        for e in group['elements']:
            segments.append(
                Segment(
                    labeler=segment_labeler,
                    video_id=e['video'],
                    min_frame=e['min_frame'],
                    max_frame=e['max_frame']))
            topics.append(e['things'])
            videos.add(e['video'])

    Segment.objects.bulk_create(segments)

    topic_links = []
    for (seg, ts) in zip(segments, topics):
        for t in ts:
            topic_links.append(Segment.things.through(segment_id=seg.id, thing_id=t))

    Segment.things.through.objects.bulk_create(topic_links)

    tag, _ = Tag.objects.get_or_create(name='handlabeled-topic:labeled')
    VideoTag.objects.bulk_create([VideoTag(tag=tag, video_id=v) for v in videos])


class LabelMode(enum.IntEnum):
    DEFAULT = 0
    SINGLE_IDENTITY = 1
    TOPIC_SEGMENTS = 2


# Register frames as labeled
def labeled(request):
    try:
        params = json.loads(request.body.decode('utf-8'))

        label_mode = int(params['label_mode'])
        groups = params['groups']
        ty = groups[0]['type']
        if label_mode == LabelMode.DEFAULT:
            if ty == 'flat':
                save_frame_labels(groups)
            else:
                save_speaker_labels(groups)

        elif label_mode == LabelMode.SINGLE_IDENTITY:
            save_single_identity_labels(groups)

        elif label_mode == LabelMode.TOPIC_SEGMENTS:
            save_topic_segments(groups)

        else:
            raise Exception('Invalid label mode: {}'.format(label_mode))

        return JsonResponse({'success': True})
    except Exception:
        return JsonResponse({'success': False, 'error': traceback.format_exc()})


# Add new "Thing" objects on-demand from the frontend
def newthings(request):
    try:
        params = json.loads(request.body.decode('utf-8'))
        thing_types = {t.name: t for t in ThingType.objects.all()}
        things = []
        for t in params['things']:
            parts = t.split(' : ')
            if len(parts) < 2:
                raise Exception('Missing type annotation on label `{}`'.format(t))
            if parts[-1].strip() not in thing_types:
                raise Exception('Invalid type annotation on label `{}`'.format(t))
            things.append(Thing(name=' : '.join(parts[:-1]).strip(), type=thing_types[parts[-1].strip()]))
        Thing.objects.bulk_create(things)
        return JsonResponse({'success': True, 'newthings': [{
            'id': t.id,
            'name': t.name,
            'type': t.type.name
        } for t in things]})
    except Exception:
        return JsonResponse({'success': False, 'error': traceback.format_exc()})
