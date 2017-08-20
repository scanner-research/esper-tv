from django.core.management.base import BaseCommand
from query.models import *
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
            filtered = paths
            labeler, _ = Labeler.objects.get_or_create(name="tinyfaces")

            filtered = []
            for path in paths:
                try:
                    video = Video.objects.get(path=path)
                except Video.DoesNotExist:
                    continue
                if len(FaceInstance.objects.filter(frame__video=video, labeler=labeler)) > 0:
                    continue
                filtered.append(path)

            stride = 24

            # Run the detector via Scanner
            # Choose stride based on framerate (3 frames / second)
            c = db.new_collection('tmp', filtered, force=True)
            faces_c = pipelines.detect_faces(
                db, c, lambda t: t.strided(stride), 'tmp_faces')
            for path, video_faces_table in zip(filtered, faces_c.tables()):
                video = Video.objects.filter(path=path).get()

                table = db.table(path)
                imgs = table.load(['frame'], rows=range(0, table.num_rows(), stride))

                video_faces = video_faces_table.load(['bboxes'], parsers.bboxes)
                for (i, frame_faces), (_, img) in zip(video_faces, imgs):
                    frame = Frame.objects.get(video=video, number=i*stride)
                    for bbox in frame_faces:
                        f = FaceInstance()
                        f.frame = frame
                        normalized_bbox = db.protobufs.BoundingBox()
                        normalized_bbox.CopyFrom(bbox)
                        normalized_bbox.x1 /= video.width
                        normalized_bbox.x2 /= video.width
                        normalized_bbox.y1 /= video.height
                        normalized_bbox.y2 /= video.height
                        f.bbox = normalized_bbox
                        f.labeler = labeler
                        f.save()

                        thumbnail_path = 'assets/thumbnails/face_{}.jpg'.format(f.id)
                        thumbnail = img[0][int(bbox.y1):int(bbox.y2),
                                           int(bbox.x1):int(bbox.x2)]

                        cv2.imwrite(thumbnail_path, cv2.cvtColor(thumbnail, cv2.COLOR_RGB2BGR))
