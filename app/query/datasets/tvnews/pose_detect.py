from query.datasets.prelude import *

LABELER, _ = Labeler.objects.get_or_create(name='openpose')
LABELED_TAG, _ = Tag.objects.get_or_create(name='openpose:labeled')
KP_SIZE = (Pose.POSE_KEYPOINTS + Pose.FACE_KEYPOINTS + 2 * Pose.HAND_KEYPOINTS) * 3


def pose_detect(videos, all_frames, force=False):

    existing_frames = Frame.objects.filter(
        video=videos[0], number__in=all_frames[0], tags=LABELED_TAG).count()
    needed_frames = len(all_frames[0])
    if force or existing_frames != needed_frames:
        log.debug('Poses not cached, missing {}/{} frames'.format(needed_frames - existing_frames,
                                                                  needed_frames))

        def output_name(video, frames):
            return video.path + '_poses_' + str(hash(tuple(frames)))

        log.debug('Connecting to scanner db')
        with make_scanner_db(kube=True) as db:
            log.debug('Connected!')

            # ingest_if_missing(db, videos)

            frame = db.ops.FrameInput()
            frame_sampled = frame.sample()
            try:
                pose = db.ops.OpenPose(
                    frame=frame_sampled,
                    model_directory="/app/deps/openpose-models/",
                    compute_hands=False,
                    compute_face=False,
                    pose_num_scales=2,
                    pose_scale_gap=0.5,
                    batch=50,
                    device=DeviceType.GPU)
                output = db.ops.Output(columns=[pose])
            except ScannerException:
                log.warning('No openpose op')
                output = db.ops.Output(columns=[frame])

            def remove_already_labeled(video, frames):
                # if (len(set(frames)) != len(frames)):
                #     raise Exception("Duplicate frames in {}: {}".format(video.path, frames))
                already_labeled = set([
                    f['number']
                    for f in Frame.objects.filter(video=video, tags=LABELED_TAG).values('number')
                ])
                l = sorted(list(set(frames) - already_labeled))
                assert (len(l) > 0)
                return l

            all_filtered_frames = [
                remove_already_labeled(video, vid_frames)
                for video, vid_frames in zip(videos, all_frames)
            ]

            jobs = [
                Job(
                    op_args={
                        frame: db.table(video.path).column('frame'),
                        frame_sampled: db.sampler.gather(vid_frames),
                        output: output_name(video, vid_frames)
                    }) for video, vid_frames in zip(videos, all_filtered_frames)
                if not db.has_table(output_name(video, vid_frames))
                or not db.table(output_name(video, vid_frames)).committed() or force
            ]

            if len(jobs) > 0:
                log.debug('Running {} Scanner pose jobs'.format(len(jobs)))
                outputs = db.run(output, jobs, force=True, io_packet_size=500, work_packet_size=100)
                log.debug('Done!')
            else:
                log.debug('No Scanner jobs to run')

            outputs = [
                db.table(output_name(video, vid_frames))
                for video, vid_frames in zip(videos, all_filtered_frames)
            ]

            def load_poses():
                log.debug('Loading poses')

                def loader(t):
                    return [[
                        Pose(keypoints=kp.tobytes(), labeler=LABELER)
                        for kp in np.split(
                            np.frombuffer(buf, dtype=np.float32),
                            len(buf) / (KP_SIZE * 4))
                    ] if len(buf) > 1 else [] for i, buf in t.column('pose').load()]

                return par_for(loader, outputs)

            all_pose_bufs = pcache.get('pose_bufs', load_poses, method='pickle', force=True)

            return [{
                frame: bufs
                for (frame, bufs) in zip(sorted(list(set(vid_frames))), pose_bufs)
            }
                    for (video, vid_frames,
                         pose_bufs) in tqdm(zip(videos, all_filtered_frames, all_pose_bufs))]

            log.debug('Saving poses')
            for (video, vid_frames, output) in zip(videos, all_filtered_frames, outputs):
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
                    for j in range(0, len(all_kp), KP_SIZE):
                        people.append(Person(frame=frame))
                Frame.tags.through.objects.bulk_create(tags)
                Person.objects.bulk_create(people)

                k = 0
                for i, buf in output.column('pose').load():
                    if len(buf) == 1: continue
                    all_kp = np.frombuffer(buf, dtype=np.float32)
                    for j in range(0, len(all_kp), KP_SIZE):
                        pose = Pose(
                            keypoints=all_kp[j:(j + KP_SIZE)].tobytes(),
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


def closest_pose(candidates, target):
    if len(candidates) == 0: return None
    noses = [pose.pose_keypoints()[Pose.Nose] for pose in candidates]
    filtered_noses = [(nose[:2], i) for i, nose in enumerate(noses) if nose[2] > 0]
    if len(filtered_noses) == 0: return None
    noses, indices = unzip(filtered_noses)
    target = target.pose_keypoints()[Pose.Nose][:2] if type(target) is not np.ndarray else target
    dists = np.linalg.norm(np.array(noses) - target, axis=1)
    closest = candidates[indices[np.argmin(dists)]]
    return closest


TARGET_FPS = 10


def bbox_midpoint2(f):
    return np.array([(f['bbox_x1'] + f['bbox_x2']) / 2, (f['bbox_y1'] + f['bbox_y2']) / 2])


def pose_track(videos, all_shots, all_shot_frames, all_shot_faces, all_dense_poses, force=False):
    labeler, _ = Labeler.objects.get_or_create(name='posetrack')
    if force or not PersonTrack.objects.filter(video=videos[0], labeler=labeler).exists():
        all_tracks = []
        for (video, vid_shots, vid_frames, vid_shot_faces, vid_dense_poses) in zip(
                videos, all_shots, all_shot_frames, all_shot_faces, all_dense_poses):

            # pose_map = defaultdict(list, {l[0].person.frame.number: l for l in vid_dense_poses})

            vid_tracks = []
            for shot, frame, known_face in zip(vid_shots, vid_frames, vid_shot_faces):
                shot_frames = list(
                    range(shot['min_frame'], shot['max_frame'], int(round(video.fps / TARGET_FPS))))
                closest_frame = shot_frames[np.argmin([abs(n - frame) for n in shot_frames])]
                known_pose = closest_pose(vid_dense_poses[closest_frame],
                                          bbox_midpoint2(known_face))

                initial_frame = closest_frame
                track = [known_pose]

                lower = [n for n in shot_frames if n < initial_frame]
                upper = [n for n in shot_frames if n > initial_frame]

                min_frame = None
                max_frame = None
                for frame in reversed(lower):
                    closest = closest_pose(vid_dense_poses[frame], track[0])
                    if closest is None:
                        break
                    min_frame = frame
                    track.insert(0, closest)

                for frame in upper:
                    closest = closest_pose(vid_dense_poses[frame], track[-1])
                    if closest is None:
                        break
                    max_frame = frame
                    track.append(closest)

                # person_track = PersonTrack(
                #     video=video,
                #     labeler=labeler,
                #     min_frame=track[0].person.frame.number,
                #     max_frame=track[-1].person.frame.number)
                person_track = {
                    'min_frame': min_frame,
                    'max_frame': max_frame,
                    'video_id': video.id,
                    'labeler_id': labeler.id
                }

                vid_tracks.append([track, person_track])

            all_tracks.append(track)

            # log.debug('Creating persontracks')
            # PersonTrack.objects.bulk_create([p for _, p in vid_tracks])

            # log.debug('Adding links to persontracks')
            # ThroughModel = Person.tracks.through
            # links = []
            # for track, person_track in vid_tracks:
            #     for pose in track:
            #         links.append(
            #             ThroughModel(
            #                 tvnews_person_id=pose.person.pk, tvnews_persontrack_id=person_track.pk))
            # ThroughModel.objects.bulk_create(links)
        return all_tracks

    return [list(PersonTrack.objects.filter(video=video, labeler=labeler)) for video in videos]
