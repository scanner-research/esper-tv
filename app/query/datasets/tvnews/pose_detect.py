from query.datasets.prelude import *

LABELER, _ = Labeler.objects.get_or_create(name='openpose')
LABELED_TAG, _ = Tag.objects.get_or_create(name='openpose:labeled')


def pose_detect(videos, all_frames, force=False):
    existing_frames = Frame.objects.filter(
        video=videos[0], number__in=all_frames[0], tags=LABELED_TAG).count()
    needed_frames = len(all_frames[0])
    if force or existing_frames != needed_frames:
        log.debug('Poses not cached, missing {}/{} frames'.format(needed_frames - existing_frames,
                                                                  needed_frames))

        def output_name(video, frames):
            return video.path + '_poses_' + str(hash(tuple(frames)))

        with Database() as db:
            ingest_if_missing(db, videos)

            frame = db.ops.FrameInput()
            frame_sampled = frame.sample()
            pose = db.ops.OpenPose(
                frame=frame_sampled,
                model_directory="/app/deps/openpose-models/",
                hands=False,
                face=False,
                pose_num_scales=2,
                pose_scale_gap=0.5,
                batch=50,
                device=DeviceType.GPU)
            output = db.ops.Output(columns=[pose])

            def remove_already_labeled(video, frames):
                already_labeled = set([
                    f['number']
                    for f in Frame.objects.filter(video=video, tags=LABELED_TAG).values('number')
                ])
                return sorted(list(set(frames) - already_labeled))

            all_frames = [
                remove_already_labeled(video, vid_frames)
                for video, vid_frames in zip(videos, all_frames)
            ]

            jobs = [
                Job(op_args={
                    frame: db.table(video.path).column('frame'),
                    frame_sampled: db.sampler.gather(vid_frames),
                    output: output_name(video, vid_frames)
                }) for video, vid_frames in zip(videos, all_frames)
                if not db.has_table(output_name(video, vid_frames))
                or not db.table(output_name(video, vid_frames)).committed() or force
            ]
            if len(jobs) > 0:
                log.debug('Running Scanner pose jobs on {} frames'.format(
                    sum([len(f) for f in all_frames])))
                bulk_job = BulkJob(output=output, jobs=jobs)
                outputs = db.run(bulk_job, force=True)

            outputs = [
                db.table(output_name(video, vid_frames))
                for video, vid_frames in zip(videos, all_frames)
            ]

            log.debug('Saving poses')
            kp_size = (Pose.POSE_KEYPOINTS + Pose.FACE_KEYPOINTS + 2 * Pose.HAND_KEYPOINTS) * 3
            for (video, vid_frames, output) in zip(videos, all_frames, outputs):
                log.debug(video.path)
                poses = []
                unsorted_indices = np.argsort(vid_frames)
                prefetched_frames = list(Frame.objects.filter(video=video).order_by('number'))

                people = []
                tags = []
                for i, buf in output.column('pose').load():
                    frame = prefetched_frames[vid_frames[unsorted_indices[i]]]
                    tags.append(
                        Frame.tags.through(tvnews_frame_id=frame.pk, tvnews_tag_id=LABELED_TAG.pk))
                    if len(buf) == 1: continue
                    all_kp = np.frombuffer(buf, dtype=np.float32)
                    for j in range(0, len(all_kp), kp_size):
                        people.append(Person(frame=frame))
                Frame.tags.through.objects.bulk_create(tags)
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

    return [
        group_by_frame(
            list(
                Pose.objects.filter(
                    person__frame__video=video, labeler=LABELER, person__frame__number__in=frames)
                .order_by('person__frame__number', 'id').select_related('person', 'person__frame')),
            lambda p: p.person.frame.number,
            lambda p: p.id,
            include_frame=False) for video, frames in zip(videos, all_frames)
    ]
