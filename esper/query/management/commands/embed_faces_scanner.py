from django.core.management.base import BaseCommand
from query.base_models import ModelDelegator
from scannerpy import Database, Job, BulkJob, ColumnType, DeviceType
from scannerpy.stdlib import writers
import os
import numpy as np
import json

DATASET = os.environ.get('DATASET')
models = ModelDelegator(DATASET)
Video, Labeler, FaceInstance, Frame, FaceFeatures = models.Video, models.Labeler, models.FaceInstance, models.Frame, models.FaceFeatures

cwd = os.path.dirname(os.path.abspath(__file__))

class Command(BaseCommand):
    help = 'Cluster faces in videos'

    def add_arguments(self, parser):
        parser.add_argument('path')
        parser.add_argument('labeler', nargs='?', default='mtcnn')

    def handle(self, *args, **options):
        face_labeler = Labeler.objects.get(name=options['labeler'])
        feature_labeler, _ = Labeler.objects.get_or_create(name='facenet')

        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        with Database() as db:
            db.register_op('EmbedFaces', [('frame', ColumnType.Video), 'bboxes'], ['embeddings'])
            db.register_python_kernel('EmbedFaces', DeviceType.CPU, cwd + '/embed_kernel.py')

            frame = db.ops.FrameInput()
            frame_strided = frame.sample()
            bboxes = db.ops.Input()
            embeddings = db.ops.EmbedFaces(frame=frame_strided, bboxes=bboxes)
            output = db.ops.Output(columns=[embeddings])

            jobs = []
            face_insts = []
            for path in paths:
                video = Video.objects.get(path=path)

                faces = FaceInstance.objects.filter(frame__video=video, labeler=face_labeler) \
                                            .select_related('frame') \
                                            .order_by('frame__video__id', 'frame__number')
                faces = [f for f in faces if f.bbox_x2 - f.bbox_x1 >= .04]

                frame_numbers = []
                rows = []
                cur_frame = None
                insts = []
                for f in faces:
                    if f.frame.id != cur_frame:
                        cur_frame = f.frame.id
                        rows.append([])
                        frame_numbers.append(f.frame.number)

                    rows[-1].append(db.protobufs.BoundingBox(
                        x1=f.bbox_x1, x2=f.bbox_x2, y1=f.bbox_y1, y2=f.bbox_y2))
                    insts.append(f.id)
                face_insts.append(insts)

                bbox_table = db.new_table(
                    path+'_bboxes', ['bboxes'], [[r] for r in rows], fn=writers.bboxes, force=True)

                bbox_table = db.table(path+'_bboxes')

                jobs.append(Job(op_args={
                    frame: db.table(path).column('frame'),
                    frame_strided: db.sampler.gather(frame_numbers),
                    bboxes: bbox_table.column('bboxes'),
                    output: path+'_embeddings'
                }))

            bulk_job = BulkJob(output=output, jobs=jobs)
            output_tables = db.run(bulk_job, force=True, pipeline_instances_per_node=1)
            output_tables = [db.table(path+'_embeddings') for path in paths]

            features = []
            for t, path, insts in zip(output_tables, paths, face_insts):
                inst_idx = 0
                embs = t.column('embeddings').load()
                for _, emb in embs:
                    for i in range(0, len(emb), 512):
                        e = np.frombuffer(emb[i:i+512], dtype=np.float32)
                        features.append(FaceFeatures(
                            features=json.dumps(e.tolist()),
                            faceinstance_id=insts[inst_idx],
                            labeler=feature_labeler))
                        inst_idx += 1
            FaceFeatures.objects.bulk_create(features)
