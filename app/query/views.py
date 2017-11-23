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

import search
import query.datasets.queries as queries

ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATA_PATH = os.environ.get('DATA_PATH')
FALLBACK_ENABLED = False


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

    return render(request, 'index.html', {
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


# Write many frames to disk
@csrf_exempt
def batch_fallback(request):
    dataset = request.POST.get('dataset')
    m = ModelDelegator(dataset)
    frames = [int(s) for s in request.POST.get('frames').split(',')]
    frames = m.Frame.objects.filter(id__in=frames)
    extract(frames, dataset)
    return JsonResponse({'success': True})


# Write one frame to disk
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
