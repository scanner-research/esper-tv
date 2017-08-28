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

GOOGLE = os.environ['ESPER_ENV'] == 'google'
BUCKET = 'scanner-data'
models = ModelDelegator('krishna')
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


# def extract_frames(video):
#     print 'Writing out thumbnails'
#     base_path = 'assets/thumbnails'
#     tmpdir = tempfile.mkdtemp()
#     cmd = 'ffmpeg -y -loglevel error -nostats -i "{}" -vf select="not(mod(n\,24))" -vf scale=640:-1 -vsync vfr {}/{}_frame_%06d.jpg'.format(video.path, tmpdir, video.id)
#     run(cmd)
#     video.num_frames = len(glob.glob('{}/{}_frame_*.jpg'.format(base_path, video.id))) * 24
#     video.save()

#     print 'Making frames'
#     frames = [Frame(number=i, video=video) for i in range(video.num_frames)]
#     Frame.objects.bulk_create(frames)
#     ids = Frame.objects.filter(video=video).order_by('number').values('id')

#     def move(i):
#         run('mv {}/{}_frame_{:06d}.jpg {}/frame_{}.jpg'.format(
#             tmpdir, video.id, i / 24 + 1, tmpdir, ids[i]['id']))

#     print 'Renaming frames'
#     with ThreadPoolExecutor(max_workers=64) as executor:
#         list(executor.map(move, range(0, video.num_frames, 24)))

#     print 'Copying to cloud'
#     run('gsutil -m mv "{}/*" gs://scanner-data/assets/'.format(tmpdir))

def ingest(path, num_frames):
    print path
    if GOOGLE:
        _, filename = os.path.split(path)
        local_path = '/tmp/{}'.format(filename)
        run('gsutil cp gs://{}/{} {}'.format(BUCKET, path, local_path))
    else:
        local_path = path

    video = Video()
    video.path = path
    video.num_frames = num_frames
    video.fps = get_fps(local_path)
    width, height = get_dimensions(local_path)
    video.width = width
    video.height = height
    video.save()

    frames = [Frame(number=i, video=video) for i in range(video.num_frames)]
    Frame.objects.bulk_create(frames)

    if GOOGLE:
        run('rm {}'.format(local_path))

    # # Because bulk_create doesn't return the primary keys for the frames,
    # # we assume that they're numbered in order starting frame 0.
    # print 'Extracting frames...'
    # extract_frames(video)
    # print 'Extracted!'

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
            paths = set([s.strip() for s in f.readlines()])

        with Database() as db:
            print 'Ingesting videos into Scanner...'
            tables, failed = db.ingest_videos([(p, p) for p in paths], force=True)
            for path, _ in failed:
                paths.remove(path)
            all_num_frames = [table.num_rows() for table in tables]

        print 'Creating entries in DB...'
        for path, num_frames in zip(paths, all_num_frames):
            ingest(path, num_frames)
