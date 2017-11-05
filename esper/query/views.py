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
from pprint import pprint

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
        # TODO(wcrichto): use GPU for resize if exists
        resized = db.ops.Resize(frame=gathered, width=640, preserve_aspect=True, device=DeviceType.CPU)
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
            # tracks = list(result[:LIMIT*STRIDE:STRIDE])

            # TODO: move to django 1.11, enable subquery

            # face_ids = [f.id for f in faces]
            # sq = Face.objects.filter(face_id=OuterRef('pk')).annotate(min_frame=Min('frame__number'))
            # tracks = Face \
            #     .filter(id__in=face_ids) \
            #     .annotate(min_frame=Subquery(sq.values('min_frame'))) \
            #     .values()

            for t in result:
                bounds = Face.objects.filter(track=t).aggregate(min_frame=Min('frame__number'), max_frame=Max('frame__number'))
                assert(bounds['min_frame'] is not None)
                if bounds['min_frame'] == bounds['max_frame']: 
                    continue

                min_face = Face.objects.filter(frame__number=bounds['min_frame'], track=t)[0]
                video = min_face.frame.video.id
                materialized_result.append({
                    'video': video,
                    'track': t.id,
                    'start_frame': Frame.objects.get(video_id=video, number=bounds['min_frame']).id,
                    'end_frame': Frame.objects.get(video_id=video, number=bounds['max_frame']).id,
                    'bboxes': [bbox_to_dict(min_face)]
                })

                if len(materialized_result) == LIMIT:
                    break

            materialized_result.sort(key=itemgetter('video', 'start_frame'))

        if group:
            grouped_result = defaultdict(list)
            for r in materialized_result:
                grouped_result[(r['video'], r['start_frame'])].extend(r['bboxes'])

            flat_result = [{'video': t1, 'start_frame': t2, 'bboxes': r}
                                   for (t1, t2), r in grouped_result.iteritems()]
            materialized_result = sorted(flat_result, key=itemgetter('video', 'start_frame'))

        if segment:
            tracks = [r['track'] for r in materialized_result]
            intervals = [(r['video'], r['start_frame'], r['end_frame']) for r in materialized_result]
            points = []
            for (video, start, end) in intervals:
                points.extend([(video, Frame.objects.get(id=start).number, start, False),
                               (video, Frame.objects.get(id=end).number, end, True)])
            points.sort(key=itemgetter(0, 1)) 

            pprint(points)
            sys.stdout.flush()

            intervals_active = 0
            boundaries = []
            i = 0
            while i < len(points):
                num_intervals = 1
                (_, _, frame, is_end) = points[i]
                while i + 1 < len(points):
                    if points[i+1][2] == frame:
                        num_intervals += 1
                        i += 1
                    else:
                        break

                pprint((points[i], num_intervals))
                sys.stdout.flush()

                if not is_end:
                    intervals_active += num_intervals
                    boundaries.append((frame, points[i+1][2]))
                else:
                    intervals_active -= num_intervals
                    if intervals_active > 0:
                        boundaries.append((frame, points[i+1][2]))

                i += 1

            # pprint(boundaries)
            # sys.stdout.flush()

            materialized_result = []
            for (start, end) in boundaries:
                f = Frame.objects.filter(id=start).select_related('video').get()
                materialized_result.append({
                    'video': f.video.id,
                    'start_frame': start,
                    'end_frame': end,
                    #'bboxes': [bbox_to_dict(face) for face in Face.objects.filter(frame=f)]
                    'bboxes': [bbox_to_dict(face) for face in Face.objects.filter(frame=f, track__in=tracks)]
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
