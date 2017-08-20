from django.core.management.base import BaseCommand, CommandError
from query.models import *
from scannerpy import Database
from scannerpy.stdlib.montage import make_montage
import subprocess as sp
import cv2
from datetime import datetime
import shlex


def run(s, shell=False):
    if shell == True:
        return sp.check_output(s, shell=True)
    else:
        return sp.check_output(shlex.split(s))


def get_dimensions(path):
    cmd = 'ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 "{}"'
    s = run(cmd.format(path)).split("\n")
    if s[0].split("=")[1] == "N/A":
        width = int(s[2].split("=")[1])
        height = int(s[3].split("=")[1])
    else:
        width = int(s[0].split("=")[1])
        height = int(s[1].split("=")[1])
    return width, height


def get_fps(path):
    cmd = 'ffmpeg -i "{}" 2>&1 | sed -n "s/.*, \\(.*\\) fp.*/\\1/p"'
    return float(run(cmd.format(path), shell=True))


def get_num_frames(path):
    cmd = '''
    ffprobe -v error -count_frames -select_streams v:0 \
      -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
      "{}"'''
    return int(run(cmd.format(path)))


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


def extract_frames(video, frame_id_start):
    cmd = 'ffmpeg -y -i "{}" assets/thumbnails/{}_frame_%06d.jpg'.format(video.path, video.id)
    run(cmd)
    for i in range(video.num_frames):
        run('mv assets/thumbnails/{}_frame_{:06d}.jpg assets/thumbnails/frame_{}.jpg'.format(
            video.id, i + 1, frame_id_start + i))


class Command(BaseCommand):
    help = 'Ingest videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = set([s.strip() for s in f.readlines()])

        with Database() as db:
            # Ingest videos into Scanner
            _, failed = db.ingest_videos([(p, p) for p in paths], force=True)
            for path, _ in failed:
                paths.remove(path)

            # Save ingested videos into SQL database
            for path in paths:
                video = Video()
                video.path = path
                video.num_frames = get_num_frames(path)
                video.fps = get_fps(path)
                width, height = get_dimensions(path)
                video.width = width
                video.height = height
                video.save()

                frames = [Frame(number=i, video=video) for i in range(video.num_frames)]
                Frame.objects.bulk_create(frames)

                # Extract static file
                make_thumbnail(video, db)
                extract_audio(video)

                # Because bulk_create doesn't return the primary keys for the frames,
                # we assume that they're numbered in order starting frame 0.
                extract_frames(video, Frame.objects.get(video=video, number=0).id)
