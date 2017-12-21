from query.datasets.prelude import *
from scannerpy import ColumnType
from scannerpy.stdlib import writers

LABELER, _ = Labeler.objects.get_or_create(name='facenet')
cwd = os.path.dirname(os.path.abspath(__file__))


def face_embed(videos, all_faces, force=False):
    if not force and FaceFeatures.objects.filter(
            face__person__frame__video=videos[0], labeler=LABELER).exists():
        return [
            list(FaceFeatures.objects.filter(
                face__person__frame__video=video,
                labeler=LABELER) \
            .order_by('id') \
            .select_related('face', 'face__person', 'face__person__frame')) \
            for video in videos
        ]

    def output_name(video):
        return video.path + '_embeddings'

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
        for video, vid_faces in zip(videos, all_faces):
            frame_numbers = []
            rows = []
            cur_frame = None
            insts = []
            for f in vid_faces:
                if f.person.frame.id != cur_frame:
                    cur_frame = f.person.frame.id
                    rows.append([])
                    frame_numbers.append(f.person.frame.number)

                rows[-1].append(
                    db.protobufs.BoundingBox(
                        x1=f.bbox_x1, x2=f.bbox_x2, y1=f.bbox_y1, y2=f.bbox_y2))
                insts.append(f.id)
            face_insts.append(insts)

            if db.has_table(output_name(video)) and not force:
                continue

            bbox_table = db.new_table(
                video.path + '_bboxes', ['bboxes'], [[r] for r in rows],
                fn=writers.bboxes,
                force=True)

            jobs.append(
                Job(op_args={
                    frame: db.table(video.path).column('frame'),
                    frame_strided: db.sampler.gather(frame_numbers),
                    bboxes: bbox_table.column('bboxes'),
                    output: output_name(video)
                }))

        if len(jobs) > 0:
            log.debug('Running Scanner embed jobs')
            bulk_job = BulkJob(output=output, jobs=jobs)
            db.run(bulk_job, force=True, pipeline_instances_per_node=1)

        output_tables = [db.table(output_name(video)) for video in videos]

        all_features = []
        for t, insts in zip(output_tables, face_insts):
            vid_features = []
            inst_idx = 0
            embs = t.column('embeddings').load()
            for _, emb in embs:
                for i in range(0, len(emb), 512):
                    e = np.frombuffer(emb[i:i + 512], dtype=np.float32)
                    vid_features.append(
                        FaceFeatures(
                            features=json.dumps(e.tolist()),
                            face_id=insts[inst_idx],
                            labeler=LABELER))
                    inst_idx += 1

            for i in range(0, len(vid_features), 1000):
                FaceFeatures.objects.bulk_create(vid_features[i:min(i + 1000, len(vid_features))])

            all_features.append(vid_features)

        return all_features
