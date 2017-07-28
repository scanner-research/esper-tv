from django.core.management.base import BaseCommand, CommandError
from query.models import *
import subprocess
import cv2
import os


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
    subprocess.check_call(['mkdir', '-p', 'assets/thumbnails'])
    subprocess.check_call(['cp '+'assets/thumbnails/{}_frame_000001.png '.format(video.id)+'assets/thumbnails/{}.png'.format(video.id)], shell=True)

def extract_audio(video):
    subprocess.check_call(['mkdir', '-p', 'assets/audio'])
    cmd = 'ffmpeg -y -i "{}" -c:a copy "assets/audio/{}.aac"'.format(video.path, video.id)
    subprocess.check_call(cmd, shell=True)


def extract_frames(video):
    subprocess.check_call(['mkdir', '-p', 'assets/thumbnails'])
    print video.path
    cmd = 'ffmpeg -y -i "{}" assets/thumbnails/{}_frame_%06d.png' \
          .format(video.path, video.id)
    subprocess.check_call(cmd, shell=True)

def delete_between_frames(video):
    stride = video.get_stride()
    for frame_num in range(video.num_frames):
        if (frame_num % stride == 0):
            continue
        filename = ("assets/thumbnails/{}_frame_{:>06}.png".format(video.id, frame_num+1))
        if os.path.isfile(filename):
            os.remove(filename)


class Command(BaseCommand):
    help = 'Ingest videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = set([s.strip() for s in f.readlines()])

        # Save ingested videos into SQL database
        for path in paths:
            print path
            videos = Video.objects.filter(path=path)
            video = None
            if len(videos) == 0:
                video = Video()
                video.path = path
                video.fps = get_fps(path)
                video.num_frames = get_num_frames(path)
                width, height = get_dimensions(path)
                video.width = width
                video.height = height
                video.save()
            else:
                video = videos.get()

            # Create corresponding label sets
            def make_labelset(name):
                if len(LabelSet.objects.filter(video=video, name=name))>0:
                    return
                labelset = LabelSet()
                labelset.name = name
                labelset.video = video
                labelset.save()
            make_labelset("detected")
            make_labelset("handlabeled")

            # Extract static file
            extract_audio(video)
            extract_frames(video)
            delete_between_frames(video)
            make_thumbnail(video)
