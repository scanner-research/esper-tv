from django.core.management.base import BaseCommand
from query.models import Video, Face, LabelSet
from scannerpy import Database, DeviceType, Job
from scannerpy.stdlib import parsers, pipelines
import os
import cv2
import math

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
                labelset = video.detected_labelset()
                if len(Face.objects.filter(labelset=labelset)) > 0: continue
                filtered.append(path)

            stride = 24

            # Run the detector via Scanner
            # Choose stride based on framerate (3 frames / second)
            c = db.new_collection('tmp', filtered, force=True)
            faces_c = pipelines.detect_faces(
                db, c, lambda t: t.strided(stride), 'tmp_faces')

            for path, video_faces_table in zip(filtered, faces_c.tables()):
                video = Video.objects.filter(path=path).get()
                labelset = LabelSet()
                labelset.name = "detected"
                labelset.video = video
                labelset.save()

                table = db.table(path)
                frames = table.load(['frame'], rows=range(0, table.num_rows(), stride))

                video_faces = video_faces_table.load(['bboxes'], parsers.bboxes)
                for (i, frame_faces), (_, frame) in zip(video_faces, frames):
                    for bbox in frame_faces:
                        f = Face()
                        f.labelset = labelset
                        f.frame = i * stride
                        f.bbox = bbox
                        f.save()
                        thumbnail_path = 'assets/thumbnails/{}_{}.jpg'.format(labelset.id, f.id)
                        thumbnail = frame[0][int(bbox.y1):int(bbox.y2),
                                             int(bbox.x1):int(bbox.x2)]

                        cv2.imwrite(thumbnail_path, cv2.cvtColor(thumbnail, cv2.COLOR_RGB2BGR))
