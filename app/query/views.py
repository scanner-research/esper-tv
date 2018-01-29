from __future__ import print_function
from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from base_models import ModelDelegator
from timeit import default_timer as now
from scannerpy import Config, Database, Job, BulkJob, DeviceType
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
import importlib
import pysrt
import requests
from storehouse import StorageConfig, StorageBackend

import search
import query.datasets.queries as queries

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
    print(*args)
    sys.stdout.flush()


# Renders home page
def index(request):
    schemas = []
    queries_ = {}

    common_queries = queries.queries['datasets']

    def load_queries(name):
        mod = importlib.import_module('query.datasets.{}.queries'.format(name))
        return mod.queries[name]

    def get_fields(cls):
        fields = cls._meta.get_fields()
        return [f.name for f in fields if isinstance(f, models.Field)]

    for name, ds in ModelDelegator().datasets().iteritems():
        schema = []

        # Get queries for dataset
        if os.path.isfile('query/datasets/{}/queries.py'.format(name)):
            ds_queries = load_queries(name)
        else:
            ds_queries = []
        queries_[name] = common_queries + ds_queries

        # Get schema for dataset
        for cls in ds.all_models():
            schema.append([cls, get_fields(getattr(ds, cls))])
        schemas.append([name, schema])

    return render(
        request, 'index.html', {
            'globals':
            json.dumps({
                'bucket': BUCKET,
                'selected': os.environ.get('DATASET'),
                'schemas': schemas,
                'queries': queries_
            })
        })


# Write out requested thumbnails to disk
def extract(frames, dataset):
    with Database() as db:
        frame = db.ops.FrameInput()
        gathered = frame.sample()
        device = DeviceType.GPU if os.environ['DEVICE'] == 'gpu' else DeviceType.CPU
        resized = db.ops.Resize(frame=gathered, width=640, preserve_aspect=True, device=device)
        compressed = db.ops.ImageEncoder(frame=resized)
        output = db.ops.Output(columns=[compressed])
        job = Job(
            op_args={
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
                    temp_dir, BUCKET, DATA_PATH, dataset)))
            _print('Write: {:.3f}'.format(now() - start))

        elif ESPER_ENV == 'local':
            try:
                os.makedirs('assets/thumbnails/' + dataset)
            except OSError:
                pass

            def write_jpg((jpg, frame)):
                with open('assets/thumbnails/{}/frame_{}.jpg'.format(dataset, frame.id), 'w') as f:
                    f.write(jpg)

            start = now()
            with ThreadPoolExecutor(max_workers=64) as executor:
                list(executor.map(write_jpg, jpgs))
            _print('Write: {:.3f}'.format(now() - start))

        return jpg


# Run search routine
def search2(request):
    params = json.loads(request.body)
    return search.search(params)


# Get distinct values in schema
def schema(request):
    params = json.loads(request.body)
    m = ModelDelegator(params['dataset'])

    cls = getattr(m, params['cls_name'])
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

    entry_fmt = u'{position}\n{start} --> {end}\n{text}'

    def fmt_time(t):
        return u'{:02d}:{:02d}:{:02d}.{:03d}'.format(t.hours, t.minutes, t.seconds, t.milliseconds)

    entries = [
        entry_fmt.format(
            position=i, start=fmt_time(sub.start), end=fmt_time(sub.end), text=sub.text)
        for i, sub in enumerate(subs)
    ]

    return u'\n\n'.join([u'WEBVTT'] + entries)


# Get subtitles for video
def subtitles(request):
    m = ModelDelegator(request.GET.get('dataset'))
    m.import_all(locals())

    path = request.GET.get('video')
    base, _ = os.path.splitext(path)

    s = storage.read('{}.cc5.srt'.format(base)).decode('utf-8')
    vtt = srt_to_vtt(s)

    return HttpResponse(vtt, content_type="text/vtt")


# Register frames as labeled
def labeled(request):
    params = json.loads(request.body)
    m = ModelDelegator(params['dataset'])

    face_labeler, _ = m.Labeler.objects.get_or_create(name='handlabeled-face')
    gender_labeler, _ = m.Labeler.objects.get_or_create(name='handlabeled-gender')
    labeled_tag, _ = m.Tag.objects.get_or_create(name='handlabeled-face:labeled')

    all_tags = []
    all_people = []
    all_faces = []
    all_genders = []
    for (vid, frame_num, faces) in params['frames']:
        frame = m.Frame.objects.get(video_id=vid, number=frame_num)
        all_tags.append(
            m.Frame.tags.through(tvnews_frame_id=frame.id, tvnews_tag_id=labeled_tag.id))
        for face in faces:
            all_people.append(m.Person(frame=frame))

            face_params = {
                'bbox_score': 1.0,
                'labeler': face_labeler,
                'person_id': None,
                'shot_id': None,
            }
            for k in ['bbox_x1', 'bbox_x2', 'bbox_y1', 'bbox_y2']:
                face_params[k] = face[k]
            all_faces.append(m.Face(**face_params))

            all_genders.append(
                m.FaceGender(face_id=None, gender_id=face['gender_id'], labeler=gender_labeler))

    m.Frame.tags.through.objects.bulk_create(all_tags)

    m.Person.objects.bulk_create(all_people)

    for (p, f) in zip(all_people, all_faces):
        f.person_id = p.id
    m.Face.objects.bulk_create(all_faces)

    for (f, g) in zip(all_faces, all_genders):
        g.face_id = f.id
    m.FaceGender.objects.bulk_create(all_genders)

    return JsonResponse({'success': True})
