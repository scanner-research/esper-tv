from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.forms.models import model_to_dict
from base_models import ModelDelegator
from timeit import default_timer as now
import sys
from google.protobuf.json_format import MessageToJson
import json
from collections import defaultdict
from scannerpy import Config, Database, Job, DeviceType
from django.db import connection
import logging
import time
from django.db.models import Min, Max
import os
from concurrent.futures import ThreadPoolExecutor
from django.views.decorators.csrf import csrf_exempt
import tempfile
import subprocess as sp
import shlex

BUCKET = 'scanner-data'
logger = logging.getLogger(__name__)

# TODO(wcrichto): find a better way to do this
Config()
from scanner.types_pb2 import BoundingBox

models = ModelDelegator('krishna')
Video, Frame, Face = models.Video, models.Frame, models.Face


def index(request):
    return render(request, 'index.html')


def extract(frames):
    with Database() as db:
        frame = db.table(frames[0].video.path).as_op().gather([frame.number for frame in frames], task_size=1000)
        resized = db.ops.Resize(frame=frame, width=640, preserve_aspect=True, device=DeviceType.GPU)
        compressed = db.ops.ImageEncoder(frame=resized)
        job = Job(columns=[compressed], name='_ignore')

        start = now()
        output = db.run(job, force=True)
        print 'Extract: {:.3f}'.format(now() - start)
        sys.stdout.flush()

        start = now()
        jpgs = [(jpg[0], frame) for (_, jpg), frame in zip(output.load(['img']), frames)]
        print 'Loaded: {:.3f}'.format(now() - start)
        sys.stdout.flush()

        temp_dir = tempfile.mkdtemp()

        def write_jpg((jpg, frame)):
            # db.config.storage.write('/assets/thumbnails/frame_{}'.format(frame.id), jpg)
            with open('{}/frame_{}.jpg'.format(temp_dir, frame.id), 'w') as f:
                f.write(jpg)

        start = now()
        with ThreadPoolExecutor(max_workers=64) as executor:
            list(executor.map(write_jpg, jpgs))
        sp.check_call(shlex.split('gsutil -m mv "{}/*" gs://{}/assets/thumbnails'.format(temp_dir, BUCKET)))
        print 'Write: {:.3f}'.format(now() - start)
        sys.stdout.flush()

        return jpg

@csrf_exempt
def batch_fallback(request):
    frames = [int(s) for s in request.POST.get('frames').split(',')]
    frames = Frame.objects.filter(id__in=frames)
    extract(frames)
    return JsonResponse({'success': True})


def fallback(request):
    request_path = request.get_full_path().split('/')[3:]
    filename, _ = os.path.splitext(request_path[-1])
    [ty, id] = filename.split('_')
    assert ty == 'frame'

    frame = Frame.objects.get(id=id)
    jpg = extract([frame])

    return HttpResponse(jpg, content_type="image/jpeg")


def videos(request):
    id = request.GET.get('id', None)
    if id is None:
        videos = Video.objects.all()
    else:
        videos = [Video.objects.filter(id=id).get()]
    return JsonResponse({
        'videos':
        [dict(model_to_dict(v).items() + {'stride': v.get_stride()}.items()) for v in videos]
    })


def frames(request):
    video_id = request.GET.get('video_id', None)
    handlabeled = request.GET.get('video_id', False)
    video = Video.objects.filter(id=video_id).get()
    labelset = video.handlabeled_labelset() if handlabeled else video.detected_labelset()
    resp = JsonResponse({
        'frames':[dict(model_to_dict(f, exclude='labels').items() + {'labels' : f.label_ids()}.items()) \
                for f in Frame.objects.filter(labelset=labelset).prefetch_related('labels').all()] ,
        'labels':[model_to_dict(s) for s in FrameLabel.objects.all()]
    })
    return resp


def frame_and_faces(request):
    video_id = request.GET.get('video_id', None)
    video = Video.objects.filter(id=video_id).prefetch_related('labelset_set').get()
    labelsets = video.labelset_set.all()
    frame_and_face_dict = {}
    ret_dict = {}
    for ls in labelsets:
        frames = Frame.objects.filter(labelset=ls).prefetch_related(
            'faces', 'labels').order_by('number').all()
        ls_dict = {}
        for frame in frames:
            frame_dict = {}
            frame_dict['labels'] = frame.label_ids()
            faces = frame.faces.all()
            face_list = []
            for face in faces:
                bbox = json.loads(MessageToJson(face.bbox))
                face_json = model_to_dict(face)
                del face_json['features']
                face_json['bbox'] = bbox
                face_list.append(face_json)
            frame_dict['faces'] = face_list
            ls_dict[frame.number] = frame_dict
        frame_and_face_dict[2 if ls.name == 'handlabeled' else 1] = ls_dict
    ret_dict['frames'] = frame_and_face_dict
    frame_labels = FrameLabel.objects.all()
    label_dict = {}
    for label in frame_labels:
        label_dict[label.id] = label.name
    ret_dict['labels'] = label_dict
    return JsonResponse(ret_dict)


def faces(request):
    video_id = request.GET.get('video_id', None)
    if video_id is None:
        return JsonResponse({})  # TODO
    video = Video.objects.filter(id=video_id).get()
    labelsets = LabelSet.objects.filter(video=video)
    all_bboxes = {}
    for labelset in labelsets:
        bboxes = defaultdict(list)
        faces = Face.objects.filter(frame__labelset=labelset).select_related('frame').all()
        for face in faces:
            bbox = json.loads(MessageToJson(face.bbox))
            face_json = model_to_dict(face)
            del face_json['features']
            face_json['bbox'] = bbox
            bboxes[face.frame.number].append(face_json)
        # 1 is Autolabeled 2 is handlabled ugly but works until
        # we use something more than a string in the model
        set_id = 1 if labelset.name == 'detected' else 2
        all_bboxes[set_id] = bboxes
    return JsonResponse({'faces': all_bboxes})


def identities(request):
    # FIXME: Should we be sending faces for each identity too?
    # FIXME: How do I see output of this when calling from js?
    identities = Identity.objects.all()
    return JsonResponse({'ids': [model_to_dict(id) for id in identities]})


def handlabeled(request):
    params = json.loads(request.body)
    video = Video.objects.filter(id=params['video']).get()
    labelset = video.handlabeled_labelset()
    frame_nums = map(int, params['frames'].keys())

    min_frame = min(frame_nums)
    max_frame = max(frame_nums)
    #old frames, create new_frames
    old_frames = Frame.objects.filter(
        labelset=labelset, number__lte=max_frame, number__gte=min_frame).all()
    labelsModel = Frame.labels.through
    if len(old_frames) > 0:
        Face.objects.filter(frame__in=old_frames).delete()
        labelsModel.objects.filter(frame__in=old_frames).delete()

    old_frame_nums = [old_frame.number for old_frame in old_frames]
    missing_frame_nums = [num for num in frame_nums if num not in old_frame_nums]
    new_frames = [Frame(labelset=labelset, number=num) for num in missing_frame_nums]
    Frame.objects.bulk_create(new_frames)
    tracks = defaultdict(list)
    for frame_num, frames in params['frames'].iteritems():
        for face_params in frames['faces']:
            track_id = face_params['track']
            if track_id is not None:
                tracks[track_id].append(frame_num)

    id_to_track = {}
    all_frames = Frame.objects.filter(
        labelset=labelset, number__lte=max_frame, number__gte=min_frame).all()
    curr_video_tracks = Track.objects.filter(video=video).all()
    for track in curr_video_tracks:
        id_to_track[track.id] = track
    for track_id, frames in tracks.iteritems():
        if track_id < 0:
            track = Track(video=video)
            track.save()
            id_to_track[track_id] = track

    new_faces = []
    new_labels = []
    for frame in all_frames:
        for face_params in params['frames'][str(frame.number)]['faces']:
            bbox = BoundingBox()
            bbox.x1 = face_params['bbox']['x1']
            bbox.y1 = face_params['bbox']['y1']
            bbox.x2 = face_params['bbox']['x2']
            bbox.y2 = face_params['bbox']['y2']
            face_params['bbox'] = bbox
            track_id = face_params['track']
            if track_id is not None:
                face_params['track'] = id_to_track[track_id]
            face = Face(**face_params)
            face.frame = frame
            new_faces.append(face)
        for label_id in params['frames'][str(frame.number)]['labels']:
            new_labels.append(labelsModel(frame=frame, framelabel_id=int(label_id)))

    Face.objects.bulk_create(new_faces)
    labelsModel.objects.bulk_create(new_labels)

    return JsonResponse({'success': True})


def search(request):
    concept = request.GET.get('concept')
    # TODO(wcrichto): Unify video and face cases?
    # TODO(wcrichto): figure out stupid fucking groupwise aggregation issue. Right now we're
    # an individual query for every concept, which is a Bad Idea.
    if concept == 'video':
        min_frame_numbers = list(Video.objects.values('id').annotate(
            min_frame=Min('frame__number'), max_frame=Max('frame__number')).order_by('id')[:10])
        qs = [
            Video.objects.filter(id=f['id'], frame__number=f['min_frame']).distinct().values(
                'id', 'frame__id').get() for f in min_frame_numbers
        ]
        sys.stdout.flush()
        clips = defaultdict(list)
        for result, f in zip(qs, min_frame_numbers):
            clips[result['id']].append({
                'frame': result['frame__id'],
                'bboxes': [],
                'start': f['min_frame'],
                'end': f['max_frame']
            })
        clips = dict(clips)

    elif concept == 'face':
        min_frame_numbers = Face.objects.values('id').annotate(
            min_frame=Min('faceinstance__frame__number'),
            max_frame=Max('faceinstance__frame__number'))[:100]
        qs = [
            Face.objects.filter(id=f['id'], faceinstance__frame__number=f['min_frame']).values(
                'id', 'faceinstance__frame__id', 'faceinstance__frame__video__id',
                'faceinstance__bbox').get() for f in min_frame_numbers if f['min_frame'] is not None
        ]
        print qs
        sys.stdout.flush()
        clips = defaultdict(list)
        for result, f in zip(qs, min_frame_numbers):
            clips[result['faceinstance__frame__video__id']].append({
                'concept':
                result['id'],
                'frame':
                result['faceinstance__frame__id'],
                'start':
                f['min_frame'],
                'end':
                f['max_frame'],
                'bboxes': [json.loads(MessageToJson(result['faceinstance__bbox']))]
            })
        clips = dict(clips)

    videos = {v.id: model_to_dict(v) for v in Video.objects.filter(pk__in=clips.keys())}
    return JsonResponse({'clips': clips, 'videos': videos})
