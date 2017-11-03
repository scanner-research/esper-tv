from __future__ import print_function
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.forms.models import model_to_dict
from django.db.models.query import QuerySet
import django.db.models as models
from base_models import ModelDelegator
from timeit import default_timer as now
import sys
from google.protobuf.json_format import MessageToJson
import json
from collections import defaultdict
from scannerpy import Config, Database, Job, BulkJob, DeviceType
from django.db import connection
import logging
import time
from django.db.models import Min, Max, Q, F, Count, OuterRef, Subquery
from django.db.models.functions import Cast
import os
from concurrent.futures import ThreadPoolExecutor
from django.views.decorators.csrf import csrf_exempt
import tempfile
import subprocess as sp
import shlex
import math
import itertools
import numpy as np
from operator import itemgetter
import traceback

ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATASET = os.environ.get('DATASET')  # TODO(wcrichto): move from config to runtime
DATA_PATH = os.environ.get('DATA_PATH')
FALLBACK_ENABLED = False
logger = logging.getLogger(__name__)

# TODO(wcrichto): find a better way to do this
Config()
from scanner.types_pb2 import BoundingBox

DIFF_BBOX_THRESHOLD = 0.35
# 24 frames/sec - so this requires more than a sec overlap
FRAME_OVERLAP_THRESHOLD = 25


def _print(*args):
    print(*args)
    sys.stdout.flush()


def index(request):
    schemas = []
    for name, ds in ModelDelegator().datasets().iteritems():
        schema = []

        def get_fields(cls):
            fields = cls._meta.get_fields()
            return [f.name for f in fields if isinstance(f, models.Field)]

        for cls in ['Video', 'Frame', 'Labeler'] + sum([[c, c + 'Track', c + 'Features']
                                                        for c in ds.concepts], []) + ds.other:
            schema.append([cls, get_fields(getattr(ds, cls))])
        schemas.append([name, schema])

    return render(request, 'index.html', {'schemas': json.dumps(schemas)})


def extract(frames):
    with Database() as db:
        frame = db.ops.FrameInput()
        gathered = frame.sample()
        resized = db.ops.Resize(frame=gathered, width=640, preserve_aspect=True, device=DeviceType.GPU)
        compressed = db.ops.ImageEncoder(frame=resized)
        output = db.ops.Output(columns=[compressed])
        job = Job(op_args={
            frame: db.table(frames[0].video.path).column('frame'),
            gathered: db.sampler.gather([frame.number for frame in frames]),
            output: '_ignore'
        })

        start = now()
        [output] = db.run(BulkJob(output=output, jobs=[job]), force=True)
        _print('Extract: {:.3f}'.format(now() - start))

        start = now()
        jpgs = [(jpg[0], frame) for (_, jpg), frame in zip(output.load(['img']), frames)]
        _print('Loaded: {:.3f}'.format(now() - start))

        if ESPER_ENV == 'google':
            temp_dir = tempfile.mkdtemp()

            def write_jpg((jpg, frame)):
                with open('{}/frame_{}.jpg'.format(temp_dir, frame.id), 'w') as f:
                    f.write(jpg)

            start = now()
            with ThreadPoolExecutor(max_workers=64) as executor:
                list(executor.map(write_jpg, jpgs))
            sp.check_call(
                shlex.split('gsutil -m mv "{}/*" gs://{}/{}/thumbnails/{}'.format(
                    temp_dir, BUCKET, DATA_PATH, DATASET)))
            _print('Write: {:.3f}'.format(now() - start))

        elif ESPER_ENV == 'local':

            try:
                os.makedirs('assets/thumbnails/' + DATASET)
            except OSError:
                pass

            def write_jpg((jpg, frame)):
                with open('assets/thumbnails/{}/frame_{}.jpg'.format(DATASET, frame.id), 'w') as f:
                    f.write(jpg)

            start = now()
            with ThreadPoolExecutor(max_workers=64) as executor:
                list(executor.map(write_jpg, jpgs))
            _print('Write: {:.3f}'.format(now() - start))
        return jpg


@csrf_exempt
def batch_fallback(request):
    m = ModelDelegator('tvnews')
    frames = [int(s) for s in request.POST.get('frames').split(',')]
    frames = m.Frame.objects.filter(id__in=frames)
    extract(frames)
    return JsonResponse({'success': True})


def fallback(request):
    if not FALLBACK_ENABLED:
        return HttpResponse(status=501)

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
                bbox = _inst_to_bbox_dict('', face)
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
        faces = FaceTrack.objects.filter(frame__labelset=labelset).select_related('frame').all()
        for face in faces:
            bbox = _inst_to_bbox('', face)
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
        FaceTrack.objects.filter(frame__in=old_frames).delete()
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
            face_params['bbox_x1'] = face_params['bbox']['x1']
            face_params['bbox_y1'] = face_params['bbox']['y1']
            face_params['bbox_x2'] = face_params['bbox']['x2']
            face_params['bbox_y2'] = face_params['bbox']['y2']
            track_id = face_params['track']
            if track_id is not None:
                face_params['track'] = id_to_track[track_id]
            face = FaceTrack(**face_params)
            face.frame = frame
            new_faces.append(face)
        for label_id in params['frames'][str(frame.number)]['labels']:
            new_labels.append(labelsModel(frame=frame, framelabel_id=int(label_id)))

    FaceTrack.objects.bulk_create(new_faces)
    labelsModel.objects.bulk_create(new_labels)

    return JsonResponse({'success': True})


def _inst_to_bbox_dict(prefix, inst):
    if prefix != '':
        prefix = prefix + "__"
    return {
        'x1': inst[prefix + 'bbox_x1'],
        'x2': inst[prefix + 'bbox_x2'],
        'y1': inst[prefix + 'bbox_y1'],
        'y2': inst[prefix + 'bbox_y2'],
        'score': inst[prefix + 'bbox_score']
    }


def _get_bbox_vals(prefix):
    if prefix != '':
        prefix = prefix + "__"
    return [
        prefix + 'bbox_x1', prefix + 'bbox_x2', prefix + 'bbox_y1', prefix + 'bbox_y2',
        prefix + 'bbox_score'
    ]


def _overlap(a, b):
    '''
    @a, b: are ranges with start/end as a[0], a[1]
    '''
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _overlap(a, b):
    '''
    @a, b: are ranges with start/end as a[0], a[1]
    '''
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _bbox_dist(bbox1, bbox2):
    return math.sqrt((bbox2['x1'] - bbox1['x1'])**2 + (bbox2['x2'] - bbox1['x2'])**2 + (bbox2['y1'] - bbox1['y1'])**2 \
                     + (bbox2['y2'] - bbox1['y2'])**2)


def bboxes_to_json(l):
    r = []
    for b in l:
        obj = _inst_to_bbox_dict('', b)
        obj['labeler'] = b['labeler']
        obj['id'] = b['id']
        r.append(obj)
    return r

LIMIT = 100
STRIDE = 1
def search2(request):
    params = json.loads(request.body)

    m = ModelDelegator(params['dataset'])
    Video, Frame, FaceTrack, Face, FaceFeatures, Labeler = m.Video, m.Frame, m.FaceTrack, m.Face, m.FaceFeatures, m.Labeler

    def make_error(err):
        return JsonResponse({'error': err})

    #### UTILITIES ####
    # TODO(wcrichto): move this into a separate, user-modifiable file

    def at_fps(qs, n=1):
        return qs.annotate(_tmp=F('number') % (Cast('video__fps', models.IntegerField()) / n)).filter(_tmp=0)

    def bbox_to_dict(f):
        return {
            'id': f.id,
            'bbox_x1': f.bbox_x1,
            'bbox_x2': f.bbox_x2,
            'bbox_y1': f.bbox_y1,
            'bbox_y2': f.bbox_y2,
            'bbox_score': f.bbox_score,
            'labeler': f.labeler.id
        }

    def bbox_area(f):
        return (f.bbox_x2 - f.bbox_x1) * (f.bbox_y2 - f.bbox_y1)

    def bbox_midpoint(f):
        return np.array([(f.bbox_x1 + f.bbox_x2) / 2, (f.bbox_y1 + f.bbox_y2) / 2])

    def bbox_dist(f1, f2):
        return np.linalg.norm(bbox_midpoint(f1) - bbox_midpoint(f2))

    def qs_to_result(result, group=False, segment=False):
        try:
            sample = result[0]
        except IndexError:
            return []

        materialized_result = []
        cls_name = '_'.join(sample.__class__.__name__.split('_')[1:])
        if cls_name == 'Frame':
            for frame in result[:LIMIT*STRIDE:STRIDE]:
                materialized_result.append({
                    'video': frame.video.id,
                    'start_frame': frame.id,
                    'bboxes': []
                })

        elif cls_name == 'Face':
            for inst in result[:LIMIT*STRIDE:STRIDE]:
                materialized_result.append({
                    'video': inst.frame.video.id,
                    'start_frame': inst.frame.id,
                    'bboxes': [bbox_to_dict(inst)]
                })

        elif cls_name == 'FaceTrack':
            tracks = list(result[:LIMIT*STRIDE:STRIDE])

            # TODO: move to django 1.11, enable subquery

            # face_ids = [f.id for f in faces]
            # sq = Face.objects.filter(face_id=OuterRef('pk')).annotate(min_frame=Min('frame__number'))
            # tracks = Face \
            #     .filter(id__in=face_ids) \
            #     .annotate(min_frame=Subquery(sq.values('min_frame'))) \
            #     .values()

            for t in tracks:
                bounds = Face.objects.filter(track=t).aggregate(min_frame=Min('frame__number'), max_frame=Max('frame__number'))
                min_face = Face.objects.filter(frame__number=bounds['min_frame'], track=t)[0]
                video = min_face.frame.video.id
                materialized_result.append({
                    'video': video,
                    'start_frame': Frame.objects.get(video_id=video, number=bounds['min_frame']).id,
                    'end_frame': Frame.objects.get(video_id=video, number=bounds['max_frame']).id,
                    'bboxes': [bbox_to_dict(min_face)]
                })

        if group:
            grouped_result = defaultdict(list)
            for r in materialized_result:
                grouped_result[(r['video'], r['start_frame'])].extend(r['bboxes'])

            flat_result = [{'video': t1, 'start_frame': t2, 'bboxes': r}
                                   for (t1, t2), r in grouped_result.iteritems()]
            materialized_result = sorted(flat_result, key=itemgetter('video', 'start_frame'))

        if segment:
            intervals = [(r['start_frame'], r['end_frame']) for r in materialized_result]
            points = []
            for (start, end) in intervals:
                points.extend([(start, False), (end, True)])
            points.sort(key=itemgetter(0))

            intervals_active = 0
            boundaries = []
            for i, (frame, is_end) in enumerate(points):
                if not is_end:
                    intervals_active += 1
                    boundaries.append((frame, points[i+1][0]))
                else:
                    if intervals_active > 1:
                        boundaries.append((frame, points[i+1][0]))
                    intervals_active -= 1

            materialized_result = []
            for (start, end) in boundaries:
                f = Frame.objects.filter(id=start).select_related('video').get()
                materialized_result.append({
                    'video': f.video.id,
                    'start_frame': start,
                    'end_frame': end,
                    'bboxes': [bbox_to_dict(face) for face in Face.objects.filter(frame=f)]
                })

        return materialized_result

    ############### WARNING: DANGER -- REMOTE CODE EXECUTION ###############
    try:
        exec(params['code']) in globals(), locals()
    except Exception as e:
        return make_error(traceback.format_exc())
    ############### WARNING: DANGER -- REMOTE CODE EXECUTION ###############

    try:
        result
    except NameError:
        return make_error('Variable "result" must be set')

    if not isinstance(result, list):
        return make_error('Result must be a frame list')

    video_ids = set()
    frame_ids = set()
    labeler_ids = set()
    for obj in result:
        video_ids.add(obj['video'])
        frame_ids.add(obj['start_frame'])
        if 'end_frame' in obj:
            frame_ids.add(obj['end_frame'])

        for bbox in obj['bboxes']:
            labeler_ids.add(bbox['labeler'])

        obj['bboxes'] = bboxes_to_json(obj['bboxes'])

    def to_dict(qs):
        return {t.id: model_to_dict(t) for t in qs}

    videos = to_dict(Video.objects.filter(id__in=video_ids))
    frames = to_dict(Frame.objects.filter(id__in=frame_ids))
    labelers = to_dict(Labeler.objects.filter(id__in=labeler_ids))

    for r in result:
        path = Video.objects.get(id=r['video']).path
        frame = r['start_frame']
        number = Frame.objects.get(id=frame).number


    return JsonResponse({'success': {
        'result': result,
        'videos': videos,
        'frames': frames,
        'labelers': labelers,
    }})


def schema(request):
    params = json.loads(request.body)
    m = ModelDelegator(params['dataset'])

    cls = getattr(m, params['cls_name'])
    result = [r[params['field']] for r in cls.objects.values(params['field']).distinct().order_by(params['field'])[:LIMIT]]
    try:
        json.dumps(result)
    except TypeError as e:
        return JsonResponse({'error': str(e)})

    return JsonResponse({'result': result})


def build_index(request):
    id = request.GET.get('id', 4457280)
    m = ModelDelegator('tvnews')
    m.FaceFeatures.dropTempFeatureModel()
    m.FaceFeatures.getTempFeatureModel([id])
    return JsonResponse({})
