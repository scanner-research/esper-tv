from query.datasets.prelude import *

LABELER, _ = Labeler.objects.get_or_create(name='openpose')


def pose_detect(videos, all_frames, force=False):
    if not force and Pose.objects.filter(person__frame__video=videos[0], labeler=LABELER).exists():
        return [
            list(
                Pose.objects.filter(person__frame__video=video, labeler=LABELER) \
                .order_by('person__frame__number', 'id') \
                .select_related('person', 'person__frame')
            ) for video in videos
        ]

    def output_name(video):
        return video.path + '_poses'

    with Database() as db:
        db.load_op('/opt/openpose-scanner/build/libopenpose_op.so',
                   '/opt/openpose-scanner/build/openpose_pb2.py')

        frame = db.ops.FrameInput()
        frame_sampled = frame.sample()
        pose = db.ops.OpenPose(
            frame=frame_sampled, hands=False, face=False, scales=2, batch=50, device=DeviceType.GPU)
        output = db.ops.Output(columns=[pose])

        jobs = [
            Job(op_args={
                frame: db.table(video.path).column('frame'),
                frame_sampled: db.sampler.gather(sorted(vid_frames)),
                output: output_name(video)
            }) for video, vid_frames in zip(videos, all_frames)
            if not db.has_table(output_name(video)) or force
        ]
        if len(jobs) > 0:
            log.debug('Running Scanner pose jobs')
            bulk_job = BulkJob(output=output, jobs=jobs)
            outputs = db.run(bulk_job, force=True)

        outputs = [db.table(output_name(video)) for video in videos]

        log.debug('Saving poses')
        kp_size = (Pose.POSE_KEYPOINTS + Pose.FACE_KEYPOINTS + 2 * Pose.HAND_KEYPOINTS) * 3
        all_poses = []
        for (video, vid_frames, output) in zip(videos, all_frames, outputs):
            log.debug(video.path)
            poses = []
            unsorted_indices = np.argsort(vid_frames)
            prefetched_frames = list(Frame.objects.filter(video=video).order_by('number'))

            people = []
            for i, buf in output.column('pose').load():
                if len(buf) == 1: continue
                frame = prefetched_frames[vid_frames[unsorted_indices[i]]]
                all_kp = np.frombuffer(buf, dtype=np.float32)
                for j in range(0, len(all_kp), kp_size):
                    people.append(Person(frame=frame))
            Person.objects.bulk_create(people)

            k = 0
            for i, buf in output.column('pose').load():
                if len(buf) == 1: continue
                all_kp = np.frombuffer(buf, dtype=np.float32)
                for j in range(0, len(all_kp), kp_size):
                    pose = Pose(
                        keypoints=all_kp[j:(j + kp_size)].tobytes(),
                        labeler=LABELER,
                        person=people[k])
                    k += 1

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
            all_poses.append(poses)

        return all_poses
