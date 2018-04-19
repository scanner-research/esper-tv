from django.core.management.base import BaseCommand
from query.datasets.prelude import *
import math

class Command(BaseCommand):
    help = 'Detect poses in video'

    def add_arguments(self, parser):
        parser.add_argument('path')

    def handle(self, *args, **options):
        with open(options['path']) as f:
            paths = [s.strip() for s in f.readlines()]

        videos = [Video.objects.get(path=path) for path in paths]

        pose_labeler, _ = Labeler.objects.get_or_create(name='openpose')
        with Database() as db:
            db.load_op('/opt/openpose-scanner/build/libopenpose_op.so')

            frame = db.ops.FrameInput()
            frame_sampled = frame.sample()
            pose = db.ops.OpenPose(frame = frame_sampled, device=DeviceType.GPU)
            output = db.ops.Output(columns=[pose])

            jobs = [
                Job(op_args={
                    frame: db.table(video.path).column('frame'),
                    frame_sampled: db.sampler.strided(int(math.ceil(video.fps)/2)),
                    output: video.path + '_poses'
                })
                for video in videos
            ]
            bulk_job = BulkJob(output=output, jobs=jobs)
            outputs = db.run(bulk_job, force=True)
            outputs = [db.table(video.path + '_poses') for video in videos]
            print('Scanner computation finished.')

            kp_size = (Pose.POSE_KEYPOINTS + Pose.FACE_KEYPOINTS + 2 * Pose.HAND_KEYPOINTS) * 3

            for (video, output) in zip(videos, outputs):
                poses = []
                print((video.path))
                frames = list(Frame.objects.filter(video=video).order_by('number'))
                for i, buf in output.column('pose').load():
                    if len(buf) == 1: continue
                    # if video.fps > 30:
                    #     if i % 2 == 1: continue
                    #     frame = frames[(i/2)*video.get_stride()]
                    # else:
                    #     frame = frames[i*video.get_stride()]
                    frame = frames[i*(int(math.ceil(video.fps)/2))]
                    all_kp = np.frombuffer(buf, dtype=np.float32)
                    for j in range(0, len(all_kp), kp_size):
                        person = Person(frame=frame)
                        person.save()

                        pose = Pose(keypoints=all_kp[j:(j+kp_size)].tobytes(), labeler=pose_labeler, person=person)

                        p = pose.pose_keypoints()
                        l = p[16, :2]
                        r = p[17, :2]
                        o = p[0, :2]
                        up = o + [r[1] - l[1], l[0] - r[0]]
                        down = o + [l[1] - r[1], r[0] - l[0]]
                        face = np.array([l, r, up, down])

                        xmin = face[:, 0].min()
                        xmax = face[:, 0].max()
                        ymin = face[:, 1].min()
                        ymax = face[:, 1].max()

                        pose.bbox_x1 = xmin
                        pose.bbox_x2 = xmax
                        pose.bbox_y1 = ymin
                        pose.bbox_y2 = ymax
                        pose.bbox_score = min(p[16, 2], p[17, 2], p[0, 2])
                        poses.append(pose)
                Pose.objects.bulk_create(poses)
