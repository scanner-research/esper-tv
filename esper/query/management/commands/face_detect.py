from django.core.management.base import BaseCommand, CommandError
from query.models import Video, Face
from scannerpy import Database, DeviceType, Job
from scannerpy.stdlib import parsers, pipelines
import os

class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            filtered = []
            for path in paths:
                video = Video.objects.filter(path=path)
                if len(video) == 0: continue
                video = video[0]
                if len(Face.objects.filter(video=video)) > 0: continue
                filtered.append(path)

            c = db.new_collection('tmp', filtered, force=True)
            faces_c = pipelines.detect_faces(
                db, c, lambda t: t.range(0, 100), 'tmp_faces', max_width = 960)

            for path, video_faces in zip(filtered, faces_c.tables()):
                video = Video.objects.filter(path=path).get()
                for i, frame_faces in video_faces.load(['bboxes'], parsers.bboxes):
                    for bbox in frame_faces:
                        f = Face()
                        f.video = video
                        f.frame = i
                        f.bbox = bbox
                        f.save()
