from django.core.management.base import BaseCommand
from query.base_models import ModelDelegator
from scannerpy import Database, Job, BulkJob, ColumnType, DeviceType
from scannerpy.stdlib import writers
import os
import numpy as np
import json
import struct

DATASET = os.environ.get('DATASET')
models = ModelDelegator(DATASET)
models.import_all(globals())

cwd = os.path.dirname(os.path.abspath(__file__))

class Command(BaseCommand):
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('labeler', nargs='?', default='tinyfaces')

    def handle(self, *args, **options):
        face_labeler = Labeler.objects.get(name=options['labeler'])
        gender_labeler, _ = Labeler.objects.get_or_create(name='rude-carnie')

        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            db.register_op('Gender', [('frame', ColumnType.Video), 'bboxes'], ['genders'])
            db.register_python_kernel('Gender', DeviceType.CPU, cwd + '/gender_kernel.py')

            frame = db.ops.FrameInput()
            frame_strided = frame.sample()
            bboxes = db.ops.Input()
            embeddings = db.ops.Gender(frame=frame_strided, bboxes=bboxes)
            output = db.ops.Output(columns=[embeddings])

            jobs = []
            face_insts = []
            for path in paths:
                video = Video.objects.get(path=path)

                faces = Face.objects.filter(person__frame__video=video, labeler=face_labeler) \
                                            .select_related('person__frame') \
                                            .order_by('person__frame__video__id', 'person__frame__number')
                faces = [f for f in faces if f.bbox_y2 - f.bbox_y1 >= .04]

                frame_numbers = []
                rows = []
                cur_frame = None
                for f in faces:
                    if f.person.frame.id != cur_frame:
                        cur_frame = f.person.frame.id
                        rows.append([])
                        frame_numbers.append(f.person.frame.number)

                    rows[-1].append(db.protobufs.BoundingBox(
                        x1=f.bbox_x1, x2=f.bbox_x2, y1=f.bbox_y1, y2=f.bbox_y2))
                face_insts.append(faces)

                bbox_table = db.new_table(
                    path+'_bboxes', ['bboxes'], [[r] for r in rows], fn=writers.bboxes, force=True)

                bbox_table = db.table(path+'_bboxes')

                jobs.append(Job(op_args={
                    frame: db.table(path).column('frame'),
                    frame_strided: db.sampler.gather(frame_numbers),
                    bboxes: bbox_table.column('bboxes'),
                    output: path+'_genders'
                }))

            bulk_job = BulkJob(output=output, jobs=jobs)
            output_tables = db.run(bulk_job, force=True, pipeline_instances_per_node=1)
            output_tables = [db.table(path+'_genders') for path in paths]

            features = []
            gender_models = []
            for t, path, insts in zip(output_tables, paths, face_insts):
                inst_idx = 0
                genders = t.column('genders').load()
                for _, g in genders:
                    for i in range(0, len(g), 5):
                        (label, score) = struct.unpack('=cf', g[i:(i+5)])
                        face = insts[inst_idx]
                        gender_models.append(FaceGender(gender=Gender.objects.get_or_create(name=label)[0], labeler=gender_labeler, face=face))
                        inst_idx += 1

            FaceGender.objects.bulk_create(gender_models)
