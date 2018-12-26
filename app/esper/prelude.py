from scannerpy import ProtobufGenerator, Config
from storehouse import StorageConfig, StorageBackend
from django.db.models import Min, Max, Count, F, Q, OuterRef, Subquery, Sum, Avg, Func, FloatField, ExpressionWrapper
from django.db.models.functions import Cast, Extract
from IPython.core.getipython import get_ipython
from timeit import default_timer as now
from functools import reduce
from typing import Dict
from pprint import pprint
import datetime
import _strptime  # https://stackoverflow.com/a/46401422/356915
import os
import subprocess as sp
import numpy as np
import pandas as pd
import sys
import logging
import json
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
import requests
import cv2
import itertools
import shutil
import tempfile
import random
import socket
import math
import csv
from pathlib import Path
from collections import defaultdict
from pickle_cache import PickleCache
from esper.widget import esper_widget

# Access to Scanner protobufs
cfg = Config()
proto = ProtobufGenerator(cfg)

# Logging config
log = logging.getLogger('esper')
log.setLevel(logging.DEBUG)
log.propagate = False  # https://stackoverflow.com/questions/11820338/replace-default-handler-of-python-logger
if not log.handlers:

    class CustomFormatter(logging.Formatter):
        def format(self, record):
            level = record.levelname[0]
            time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')[2:]
            if len(record.args) > 0:
                record.msg = '({})'.format(', '.join(
                    [str(x) for x in [record.msg] + list(record.args)]))
                record.args = ()
            return '{level} {time} {filename}:{lineno:03d}] {msg}'.format(
                level=level, time=time, **record.__dict__)

    handler = logging.StreamHandler()
    handler.setFormatter(CustomFormatter())
    log.addHandler(handler)

# Only run if we're in an IPython notebook
if get_ipython() is not None:
    # Matplotlib/seaborn config
    import matplotlib
    import matplotlib.pyplot as plt
    import seaborn as sns
    matplotlib.rcParams['figure.figsize'] = (18, 8)
    plt.rc("axes.spines", top=False, right=False)
    sns.set_style('white')

    from tqdm import tqdm_notebook as tqdm

else:
    from tqdm import tqdm

# Setup Storehouse
ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATA_PATH = os.environ.get('DATA_PATH')

if ESPER_ENV == 'google':
    storage_config = StorageConfig.make_gcs_config(BUCKET)
else:
    storage_config = StorageConfig.make_posix_config()
storage = StorageBackend.make_from_config(storage_config)


def unzip(l, default=([], [])):
    x = tuple(zip(*l))
    if x == ():
        return default
    else:
        return x


def par_for(f, l, process=False, workers=None, progress=True):
    Pool = ProcessPoolExecutor if process else ThreadPoolExecutor
    with Pool(max_workers=mp.cpu_count() if workers is None else workers) as executor:
        if progress:
            return list(tqdm(executor.map(f, l), total=len(l), smoothing=0.05))
        else:
            return list(executor.map(f, l))


def par_filter(f, l, **kwargs):
    return [x for x, b in zip(l, par_for(f, l, **kwargs)) if b]


class Timer:
    def __init__(self, s, run=True):
        self._s = s
        self._run = run
        if run:
            log.debug('-- START: {} --'.format(s))

    def __enter__(self):
        self.start = now()

    def __exit__(self, a, b, c):
        t = int(now() - self.start)
        if self._run:
            log.debug('-- END: {} -- {:02d}:{:02d}:{:02d}'.format(self._s, int(t / 3600),
                                                                  int((t / 60) % 60),
                                                                  int(t) % 60))


pcache = PickleCache(cache_dir='/app/.cache')


def crop(img, bbox):
    [h, w] = img.shape[:2]
    return img[int(bbox.bbox_y1 * h):int(bbox.bbox_y2 * h),
               int(bbox.bbox_x1 * w):int(bbox.bbox_x2 * w)]


def resize(img, w, h):
    th = int(img.shape[0] * (w / float(img.shape[1]))) if h is None else int(h)
    tw = int(img.shape[1] * (h / float(img.shape[0]))) if w is None else int(w)
    return cv2.resize(img, (tw, th))


def load_frame(video, frame, bboxes):
    while True:
        try:
            r = requests.get(
                'http://frameserver:7500/fetch', params={
                    'path': video.path,
                    'frame': frame,
                })
            break
        except requests.ConnectionError:
            pass
    img = cv2.imdecode(np.fromstring(r.content, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise Exception("Bad frame {} for {}".format(frame, video.path))
    for bbox in bboxes:
        img = cv2.rectangle(
            img, (int(bbox['bbox_x1'] * img.shape[1]), int(bbox['bbox_y1'] * img.shape[0])),
            (int(bbox['bbox_x2'] * img.shape[1]), int(bbox['bbox_y2'] * img.shape[0])), (0, 0, 255),
            8)

    return img


def make_montage(video,
                 frames,
                 output_path=None,
                 bboxes=None,
                 width=1600,
                 num_cols=8,
                 workers=16,
                 target_height=None,
                 progress=False):
    target_width = int(width / num_cols)

    bboxes = bboxes or [[] for _ in range(len(frames))]
    videos = video if isinstance(video, list) else [video for _ in range(len(frames))]
    imgs = par_for(
        lambda t: resize(load_frame(*t), target_width, target_height),
        list(zip(videos, frames, bboxes)),
        progress=progress,
        workers=workers)
    target_height = int(imgs[0].shape[0])
    num_rows = int(math.ceil(float(len(imgs)) / num_cols))

    montage = np.zeros((num_rows * target_height, width, 3), dtype=np.uint8)
    for row in range(num_rows):
        for col in range(num_cols):
            i = row * num_cols + col
            if i >= len(imgs):
                break
            img = imgs[i]
            montage[row * target_height:(row + 1) * target_height, col * target_width:(
                col + 1) * target_width, :] = img
        else:
            continue
        break

    if output_path is not None:
        cv2.imwrite(output_path, montage)
    else:
        return montage


def shot_montage(video, **kwargs):
    from query.models import Frame
    return make_montage(video, [
        f['number'] for f in Frame.objects.filter(video=video, shot_boundary=True).order_by(
            'number').values('number')
    ], **kwargs)


def _get_frame(args):
    (videos, fps, start, i, kwargs) = args
    return make_montage(videos, [int(math.ceil(v.fps)) / fps * i + start for v in videos], **kwargs)


def make_montage_video(videos, start, end, output_path, **kwargs):
    def gcd(a, b):
        return gcd(b, a % b) if b else a

    fps = reduce(gcd, [int(math.ceil(v.fps)) for v in videos])

    first = _get_frame((videos, fps, start, 0, kwargs))
    vid = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'XVID'), fps,
                          (first.shape[1], first.shape[0]))

    frames = par_for(
        _get_frame, [(videos, fps, start, i, kwargs) for i in range(end - start)],
        workers=8,
        process=True)
    for frame in tqdm(frames):
        vid.write(frame)

    vid.release()


# https://mathieularose.com/how-not-to-flatten-a-list-of-lists-in-python/
def flatten(l):
    return list(itertools.chain.from_iterable(l))


def collect(l, kfn):
    d = defaultdict(list)
    for x in l:
        d[kfn(x)].append(x)
    return dict(d)


def concat_videos(paths, output_path=None):
    if output_path is None:
        output_path = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name

    transform = ';'.join(['[{i}:v]scale=640:480:force_original_aspect_ratio=decrease,pad=640:480:(ow-iw)/2:(oh-ih)/2[v{i}]'.format(i=i) for i in range(len(paths))])
    filter = ''.join(['[v{i}][{i}:a:0]'.format(i=i) for i in range(len(paths))])
    inputs = ' '.join(['-i {}'.format(p) for p in paths])

    cmd = '''
    ffmpeg -y {inputs} \
    -filter_complex "{transform}; {filter}concat=n={n}:v=1:a=1[outv][outa]" \
    -map "[outv]" -map "[outa]" {output}
    '''.format(transform=transform, inputs=inputs, filter=filter, n=len(paths), output=output_path)
    print(cmd)
    sp.check_call(cmd, shell=True)

    return output_path


# For breaking out of nested loops
class Break(Exception):
    pass


def ring():
    print('\a')


def batch(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]


class Notifier:
    def __init__(self):
        import redis
        self._r = redis.Redis(host='redis', port=6379)
        self._p = self._r.pubsub()

    def notify(self, message, action=None):
        self._r.publish('main', json.dumps({'message': message, 'action': action}))
