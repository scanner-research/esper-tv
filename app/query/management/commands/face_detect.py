from django.core.management.base import BaseCommand
from query.base_models import ModelDelegator
from scannerpy import Database, DeviceType, Job
from scannerpy.stdlib import parsers, pipelines
import os
import cv2
import math
import random

DATASET = os.environ.get('DATASET')
models = ModelDelegator(DATASET)
models.import_all(globals())


class Command(BaseCommand):
    help = 'Detect faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('bbox_labeler', nargs='?', default='tinyfaces')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            filtered = paths
            labeler, _ = Labeler.objects.get_or_create(name=options['bbox_labeler'])

            filtered = []
            for path in paths:
                try:
                    video = Video.objects.get(path=path)
                except Video.DoesNotExist:
                    continue
                if len(Face.objects.filter(person__frame__video=video, labeler=labeler)) > 0:
                    continue
                filtered.append(path)

            stride = 24

            # Run the detector via Scanner
            faces_c = pipelines.detect_faces(db,
                                             [db.table(path).column('frame') for path in filtered],
                                             db.sampler.strided(stride), 'tmp_faces')

            for path, video_faces_table in zip(filtered, faces_c):
                video = Video.objects.filter(path=path).get()

                table = db.table(path)
                imgs = table.load(['frame'], rows=range(0, table.num_rows(), stride))
                video_faces = video_faces_table.load(
                    ['bboxes'], lambda lst, db: parsers.bboxes(lst[0], db.protobufs))

                for (i, frame_faces), (_, img) in zip(video_faces, imgs):
                    frame = Frame.objects.get(video=video, number=i * stride)
                    for bbox in frame_faces:
                        if labeler.name == 'dummy' and random.randint(0, 10) == 1:
                            # generate dummy labels, sometimes
                            # TODO: add boundary checks, shouldn't matter much thouhg.
                            bbox.x1 += 50
                            bbox.x2 += 50
                            bbox.y1 += 50
                            bbox.y2 += 50

                        p = Person(frame=frame)
                        p.save()
                        f = Face(person=p)
                        f.bbox_x1 = bbox.x1 / video.width
                        f.bbox_x2 = bbox.x2 / video.width
                        f.bbox_y1 = bbox.y1 / video.height
                        f.bbox_y2 = bbox.y2 / video.height
                        f.bbox_score = bbox.score
                        f.labeler = labeler
                        f.save()
