from query.datasets.prelude import *
from scannerpy import ColumnType
from scannerpy.stdlib import writers

LABELER, _ = Labeler.objects.get_or_create(name='facenet')
cwd = os.path.dirname(os.path.abspath(__file__))


def face_embed(videos, all_faces, force=False):
    if force or \
       not FaceFeatures.objects.filter(face__person__frame__video=videos[0], labeler=LABELER).exists():

        def output_name(video, frames):
            return video.path + '_embeddings_' + str(hash(tuple(frames)))

        with Database() as db:
            db.register_op('EmbedFaces', [('frame', ColumnType.Video), 'bboxes'], ['embeddings'])
            db.register_python_kernel('EmbedFaces', DeviceType.CPU, cwd + '/embed_kernel.py')

            frame = db.ops.FrameInput()
            frame_strided = frame.sample()
            bboxes = db.ops.Input()
            embeddings = db.ops.EmbedFaces(frame=frame_strided, bboxes=bboxes)
            output = db.ops.Output(columns=[embeddings])

            jobs = []
            all_frame_numbers = []
            for video, vid_faces in zip(videos, all_faces):
                frame_numbers = [frame_faces[0].person.frame.number for frame_faces in vid_faces]
                all_frame_numbers.append(frame_numbers)

                unsorted_indices = np.argsort(frame_numbers)

                rows = [[
                    db.protobufs.BoundingBox(
                        x1=f.bbox_x1, x2=f.bbox_x2, y1=f.bbox_y1, y2=f.bbox_y2) for f in frame_faces
                ] for frame_faces in vid_faces]
                rows = [rows[i] for i in unsorted_indices]

                if not force and db.has_table(output_name(video, frame_numbers)):
                    continue

                bbox_table = db.new_table(
                    video.path + '_bboxes', ['bboxes'], [[r] for r in rows],
                    fn=writers.bboxes,
                    force=True)

                assert (len(frame_numbers) == len(set(frame_numbers)))

                jobs.append(
                    Job(op_args={
                        frame: db.table(video.path).column('frame'),
                        frame_strided: db.sampler.gather(sorted(frame_numbers)),
                        bboxes: bbox_table.column('bboxes'),
                        output: output_name(video, frame_numbers)
                }))

            if len(jobs) > 0:
                log.debug('Running Scanner embed jobs')
                bulk_job = BulkJob(output=output, jobs=jobs)

                # TODO(wcrichto): multi-gpu face embed
                db.run(bulk_job, force=True, pipeline_instances_per_node=1)

            output_tables = [
                db.table(output_name(video, nums))
                for video, nums in zip(videos, all_frame_numbers)
            ]

            for table, vid_faces, frame_numbers in zip(output_tables, all_faces, all_frame_numbers):
                face_map = {f[0].person.frame.number: f for f in vid_faces}
                unsorted_indices = np.argsort(frame_numbers)
                vid_features = []
                embs = table.column('embeddings').load()
                for idx, (_, emb) in zip(unsorted_indices, embs):
                    for j, face in zip(
                            range(0, len(emb), 512), face_map[frame_numbers[idx]]):
                        e = np.frombuffer(emb[j:(j + 512)], dtype=np.float32)
                        vid_features.append(
                            FaceFeatures(
                                features=json.dumps(e.tolist()), face=face, labeler=LABELER))

                FaceFeatures.objects.batch_create(vid_features)

    return [
        group_by_frame(
            list(
                FaceFeatures.objects.filter(face__person__frame__video=video, labeler=LABELER)
                .select_related('face', 'face__person', 'face__person__frame')),
            lambda f: f.face.person.frame.number,
            lambda f: f.face.id,
            include_frame=False) for video in videos
    ]
