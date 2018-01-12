from query.datasets.prelude import *
import struct

LABELER, _ = Labeler.objects.get_or_create(name='rude-carnie')
cwd = os.path.dirname(os.path.abspath(__file__))


def gender_detect(videos, all_frames, all_faces):
    def output_name(video, frames):
        return video.path + '_genders_' + str(hash(tuple(frames)))

    def loader():
        log.debug('Loading genders')
        with make_scanner_db() as db:

            def load(t):
                return [[struct.unpack('=cf', buf[i:(i + 5)]) for i in range(0, len(buf), 5)]
                        if buf is not None else [] for _, buf in t.column('genders').load()]

            log.debug('Fetching tables')
            tables = [
                db.table(output_name(video, frames))
                for video, frames in tqdm(zip(videos, all_frames))
                if db.has_table(output_name(video, frames))
                and db.table(output_name(video, frames)).committed()
            ]
            return par_for(load, tables)

    return pcache.get('all_genders', loader, method='marshal')

    log.debug('Connecting to scanner db')
    with make_scanner_db(kube=True) as db:
        log.debug('Connected!')

        log.debug('Registering Python op')
        try:
            db.register_op('Gender', [('frame', ColumnType.Video), 'bboxes'], ['genders'])
            db.register_python_kernel('Gender', DeviceType.CPU, cwd + '/gender_kernel.py')
        except ScannerException:
            traceback.print_exc()
            pass

        frame = db.ops.FrameInput()
        frame_sampled = frame.sample()
        bboxes = db.ops.Input()
        genders = db.ops.Gender(frame=frame_sampled, bboxes=bboxes)
        output = db.ops.Output(columns=[genders])

        jobs = [
            Job(
                op_args={
                    frame: db.table(video.path).column('frame'),
                    frame_sampled: db.sampler.gather(vid_frames),
                    bboxes: db.table(vid_faces).column('bboxes'),
                    output: output_name(video, vid_frames)
                }) for video, vid_frames, vid_faces in tqdm(zip(videos, all_frames, all_faces))
        ]
        assert (len(jobs) > 0)

        log.debug('Running gender on {} jobs'.format(len(jobs)))
        db.run(
            BulkJob(output=output, jobs=jobs),
            force=True,
            io_packet_size=50000,
            work_packet_size=500,
            pipeline_instances_per_node=1)

        log.debug('Done!')
        exit()
