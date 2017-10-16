from django.core.management.base import BaseCommand, CommandError
from query.base_models import ModelDelegator
from scannerpy import Database
from scannerpy.stdlib.montage import make_montage
import subprocess as sp
import cv2
from datetime import datetime
import shlex
import tempfile
import glob
from concurrent.futures import ThreadPoolExecutor
import multiprocessing as mp
from timeit import default_timer as now
import os
import requests
from datetime import datetime
import math

ESPER_ENV = os.environ.get('ESPER_ENV')
BUCKET = os.environ.get('BUCKET')
DATASET = os.environ.get('DATASET')
models = ModelDelegator(DATASET)
Video, Frame = models.Video, models.Frame


def run(s, shell=False, output=False):
    if shell == True:
        return sp.check_output(s, shell=True)
    elif output == True:
        return sp.check_output(shlex.split(s))
    else:
        return sp.check_call(shlex.split(s))


def get_dimensions(path):
    cmd = 'ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 "{}"'
    s = run(cmd.format(path), output=True).split("\n")
    if s[0].split("=")[1] == "N/A":
        width = int(s[2].split("=")[1])
        height = int(s[3].split("=")[1])
    else:
        width = int(s[0].split("=")[1])
        height = int(s[1].split("=")[1])
    return width, height


def get_fps(path):
    cmd = 'ffmpeg -i "{}" 2>&1 | sed -n "s/.*, \\(.*\\) fp.*/\\1/p"'
    return float(run(cmd.format(path), shell=True, output=True))


def get_num_frames(path):
    cmd = '''
    ffprobe -v error -count_frames -select_streams v:0 \
      -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
      "{}"'''
    return int(run(cmd.format(path), output=True))


def make_thumbnail(video, db):
    indices = [int(n * video.num_frames) for n in [0.1, 0.35, 0.60, 0.85]]
    table = db.table(video.path)
    frames = [f[0] for _, f in table.load([1], rows=indices)]
    img = make_montage(len(frames), iter(frames), frame_width=150, frames_per_row=2)
    run('mkdir -p assets/thumbnails')
    cv2.imwrite('assets/thumbnails/{}.jpg'.format(video.id), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))


def extract_audio(video):
    sp.check_call(['mkdir', '-p', 'assets/audio'])
    cmd = 'ffmpeg -y -i "{}" -c:a copy "assets/audio/{}.aac"'.format(video.path, video.id)
    run(cmd)


def save_frames(video):
    stride = int(math.ceil(video.fps)/2)
    ids = [
        str(f['id'])
        for f in Frame.objects.filter(video=video, number__in=range(0, video.num_frames, stride))
        .order_by('number').values('id')
    ]
    requests.post('http://localhost:8000/batch_fallback', data={'frames': ','.join(ids)})


def ingest(path, num_frames):
    try:
        if ESPER_ENV == 'google':
            _, filename = os.path.split(path)
            local_path = '/tmp/{}'.format(filename)
            run('gsutil cp gs://{}/{} {}'.format(BUCKET, path, local_path))
        else:
            local_path = path

        parts = os.path.splitext(os.path.split(path)[1])[0].split('_')
        [channel, date, time] = parts[:3]
        dt = datetime.strptime('{} {}'.format(date, time), '%Y%m%d %H%M%S')
        if channel[-1] == 'W':
            channel = channel[:-1]
        show = ' '.join(parts[3:-1])  # -1 for "_segment"

        video = Video()
        video.path = path
        video.num_frames = num_frames
        video.fps = get_fps(local_path)
        width, height = get_dimensions(local_path)
        video.width = width
        video.height = height
        video.time = dt
        video.channel = channel
        video.show = show
        video.save()

        frames = [Frame(number=i, video=video) for i in range(video.num_frames)]
        Frame.objects.bulk_create(frames)

        save_frames(video)

        if ESPER_ENV == 'google':
            run('rm {}'.format(local_path))
    except:
        Video.objects.filter(path=path).delete()
        raise

    # Extract static file
    if False:
        make_thumbnail(video, db)
        extract_audio(video)


class Command(BaseCommand):
    help = 'Ingest videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            print 'Ingesting videos into Scanner...'
            tables, failed = db.ingest_videos([(p, p) for p in paths], force=True)
            for path, _ in failed:
                paths.remove(path)
            all_num_frames = [table.num_rows() for table in tables]

            # all_num_frames = [db.table(p).num_rows() for p in paths]

        print 'Creating entries in DB...'
        for i, (path, num_frames) in enumerate(zip(paths, all_num_frames)):
            print '{}/{}: {}'.format(i, len(paths), path)
            ingest(path, num_frames)
