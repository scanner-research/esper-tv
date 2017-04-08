from django.core.management.base import BaseCommand, CommandError
from query.models import Video
from scannerpy import Database
from scannerpy.stdlib.montage import make_montage
import subprocess
import cv2


def get_dimensions(path):
    cmd = 'ffprobe -v error -show_entries stream=width,height -of default=noprint_wrappers=1 "{}"'
    s = subprocess.check_output(cmd.format(path), shell=True).split("\n")
    if s[0].split("=")[1] == "N/A":
        width = int(s[2].split("=")[1])
        height = int(s[3].split("=")[1])
    else:
        width = int(s[0].split("=")[1])
        height = int(s[1].split("=")[1])
    return width, height


def get_fps(path):
    cmd = 'ffmpeg -i "{}" 2>&1 | sed -n "s/.*, \\(.*\\) fp.*/\\1/p"'
    return float(subprocess.check_output(cmd.format(path), shell=True))


def get_num_frames(path):
    cmd = '''
    ffprobe -v error -count_frames -select_streams v:0 \
      -show_entries stream=nb_read_frames -of default=nokey=1:noprint_wrappers=1 \
      "{}"'''
    return int(subprocess.check_output(cmd.format(path), shell=True))


def make_thumbnail(video):
    indices = [int(n * video.num_frames) for n in [0.1, 0.35, 0.60, 0.85]]
    vid = cv2.VideoCapture(video.path)
    frames = []
    for i in range(indices[-1]+1):
        _, frame = vid.read()
        if i in indices:
            frames.append(frame)
    img = make_montage(
        len(frames), iter(frames),
        frame_width=150,
        frames_per_row=2)
    subprocess.check_call(['mkdir', '-p', 'assets/thumbnails'])
    cv2.imwrite('assets/thumbnails/{}.jpg'.format(video.id), img)

class Command(BaseCommand):
    help = 'Ingest videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        # with Database() as db:
        #     db.ingest_videos([(p, p) for p in paths], force=True)

        for path in paths:
            video = Video()
            video.path = path
            video.num_frames = get_num_frames(path)
            video.fps = get_fps(path)
            width, height = get_dimensions(path)
            video.width = width
            video.height = height
            video.save()
            make_thumbnail(video)
