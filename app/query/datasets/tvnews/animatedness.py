from query.datasets.prelude import *
from query.datasets.tvnews.shot_detect import shot_detect, shot_stitch
from query.datasets.tvnews.face_detect import face_detect
from query.datasets.tvnews.face_embed import face_embed
from query.datasets.tvnews.pose_detect import pose_detect
from query.datasets.tvnews.identity_detect import identity_detect

POSE_STRIDE = 3


def shot_frame_to_detect(shot):
    return (shot.min_frame + shot.max_frame) / 2


# Remove faces with negative coords and small height
def filter_invalid_faces(all_faces):
    def inrange(v):
        return 0 <= v and v <= 1

    def valid_bbox(f):
        return f.bbox_y2 - f.bbox_y1 >= .1 and inrange(f.bbox_x1) and inrange(f.bbox_x2) \
            and inrange(f.bbox_y1) and inrange(f.bbox_y2)

    filtered_faces = [[[f for f in frame if valid_bbox(f)] for frame in vid_faces]
                      for vid_faces in all_faces]

    return [[f for f in vid_faces if len(f) > 0] for vid_faces in filtered_faces]


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


def match_poses_to_faces(all_poses, all_faces):
    return [[
        closest_pose(poses, bbox_midpoint(face)) for (poses, face) in zip(vid_poses, vid_faces)
    ] for (vid_poses, vid_faces) in zip(all_poses, all_faces)]


# Remove poses that don't have hands showing
def filter_invalid_poses(all_poses):
    def valid_pose(p):
        kp = p.pose_keypoints()
        return kp[Pose.LWrist][2] > 0 and kp[Pose.RWrist][2] > 0

    poses, indices = unzip([
        unzip([(p, i) for i, p in enumerate(vid_poses) if valid_pose(p)]) for vid_poses in all_poses
    ])
    log.debug('filtering invalid poses: {} --> {}'.format(len(all_poses[0]), len(poses[0])))
    return poses, indices


    # Get shots corresponding to matched faces
def features_to_shots(matching_features, all_shots, frame_per_shot):
    all_shot_maps = [{frame: shot
                      for shot, frame in zip(vid_shots, vid_frames)}
                     for vid_shots, vid_frames in zip(all_shots, frame_per_shot)]

    return [[shot_map[f.face.person.frame.number] for f in vid_features]
            for vid_features, shot_map in zip(matching_features, all_shot_maps)]


def pose_track(videos, all_shots, all_shot_poses, all_dense_poses, force=False):
    labeler, _ = Labeler.objects.get_or_create(name='posetrack')
    if force or not PersonTrack.objects.filter(video=videos[0], labeler=labeler).exists():
        for (video, vid_shots, vid_shot_poses, vid_dense_poses) in zip(
                videos, all_shots, all_shot_poses, all_dense_poses):
            pose_map = defaultdict(list, {l[0].person.frame.number: l for l in vid_dense_poses})

            log.debug('Finding tracks')
            vid_tracks = []
            for shot, known_pose in zip(vid_shots, vid_shot_poses):
                initial_frame = known_pose.person.frame.number
                track = [known_pose]

                shot_frames = range(shot.min_frame, shot.max_frame, POSE_STRIDE)
                lower = [n for n in shot_frames if n < initial_frame]
                upper = [n for n in shot_frames if n > initial_frame]

                for frame in reversed(lower):
                    closest = closest_pose(pose_map[frame], track[0])
                    if closest is None:
                        break
                    track.insert(0, closest)

                for frame in upper:
                    closest = closest_pose(pose_map[frame], track[-1])
                    if closest is None:
                        break
                    track.append(closest)

                person_track = PersonTrack(
                    video=video,
                    labeler=labeler,
                    min_frame=track[0].person.frame.number,
                    max_frame=track[-1].person.frame.number)

                vid_tracks.append([track, person_track])

            log.debug('Creating persontracks')
            PersonTrack.objects.bulk_create([p for _, p in vid_tracks])

            log.debug('Adding links to persontracks')
            ThroughModel = Person.tracks.through
            links = []
            for track, person_track in vid_tracks:
                for pose in track:
                    links.append(
                        ThroughModel(
                            tvnews_person_id=pose.person.pk, tvnews_persontrack_id=person_track.pk))
            ThroughModel.objects.bulk_create(links)

    return [list(PersonTrack.objects.filter(video=video, labeler=labeler)) for video in videos]


def pose_dist(p1, p2):
    kp1 = p1.pose_keypoints()
    kp2 = p2.pose_keypoints()

    weights = defaultdict(float, {
        Pose.LWrist: 0.4,
        Pose.RWrist: 0.4,
        Pose.Nose: 0.1,
        Pose.LElbow: 0.05,
        Pose.RElbow: 0.05
    })
    weight_vector = [weights[i] for i in range(Pose.POSE_KEYPOINTS)]

    dist = np.linalg.norm(kp2[:, :2] - kp1[:, :2], axis=1)
    weighted_dist = np.array([
        d * w for d, s1, s2, w in zip(dist, kp1[:, 2], kp2[:, 2], weight_vector)
        if s1 > 0 and s2 > 0
    ])
    return np.linalg.norm(weighted_dist)


# TODO: take max of sliding window, not whole range
def animated_score(track):
    poses = list(Pose.objects.filter(person__tracks=track).order_by('person__frame__number'))
    dists = [pose_dist(poses[i], poses[i + 1]) for i in range(len(poses) - 1)]
    w = min(POSE_STRIDE * 5, len(dists) - 1)
    return max([np.mean(dists[i:i + w]) for i in range(0, len(dists) - w)])

# Do shot segmentation on a larger set of videos

# Goal 1. Histogram of shot lengths
#

def animatedness(videos, exemplar):
    videos = videos[:10]
    with Timer('Detecting shots'):
        all_shots = shot_detect(videos)
        face_frame_per_shot = [[shot_frame_to_detect(shot) for shot in vid_shots]
                               for vid_shots in all_shots]

    with Timer('Detecting sparse face'):
        all_faces = face_detect(videos, face_frame_per_shot)
    print([f.id for l in all_faces[0] for f in l])
    exit()

    with Timer('Filtering invalid faces'):
        filtered_faces = filter_invalid_faces(all_faces)
    log.debug('faces: {} --> {}'.format(
        sum(len(f) for f in all_faces[0]), sum(len(f) for f in filtered_faces[0])))

    with Timer('Embedding faces'):
        all_features = face_embed(videos, filtered_faces)

    with Timer('Stiching shots'):
        stitched_shots, shot_faces, shot_features = shot_stitch(
            videos, all_shots, face_frame_per_shot, filtered_faces, all_features)

    with Timer('Detecting identities'):
        matching_features, indices = identity_detect(videos, exemplar, shot_features)
        matching_shots, matching_faces = unzip([
            unzip([(vid_shots[j], vid_faces[j][k]) for (j, k) in vid_indices])
            for (vid_shots, vid_faces, vid_indices) in zip(stitched_shots, shot_faces, indices)
        ])
        log.debug('shots: {} --> {}'.format(len(stitched_shots[0]), len(matching_shots[0])))

    with Timer('Computing sparse poses to find shots with hands in view'):
        pose_frame_per_shot, matching_shots, matching_faces = unzip([
            unzip(
                sorted(
                    [(face.person.frame.number, shot, face)
                     for (face, shot) in zip(vid_faces, vid_shots)],
                    key=itemgetter(0)))
            for (vid_faces, vid_shots) in zip(matching_faces, matching_shots)
        ])

    with Timer('Computing sparse poses'):
        all_poses = pose_detect(videos, pose_frame_per_shot)
        assert (len(all_poses[0]) == len(matching_faces[0]))
        matching_poses = match_poses_to_faces(all_poses, matching_faces)
        assert (len(matching_poses[0]) == len(matching_faces[0]))

    with Timer('Filtering invalid poses'):
        filtered_poses, indices = filter_invalid_poses(matching_poses)
        filtered_shots = [[vid_shots[i] for i in vid_indices]
                          for vid_shots, vid_indices in zip(matching_shots, indices)]
        log.debug('shots: {} --> {}'.format(len(matching_poses[0]), len(filtered_poses[0])))

    with Timer('Computing dense poses for animatedness'):
        pose_frames_per_shot = [
            sum([
                list(range(shot.min_frame, shot.max_frame + 1, POSE_STRIDE)) for shot in vid_shots
            ], []) for vid_shots in filtered_shots
        ]
        all_dense_poses = pose_detect(videos, pose_frames_per_shot)

    with Timer('Tracking poses'):
        all_tracks = pose_track(videos, filtered_shots, filtered_poses, all_dense_poses)

    for video, vid_tracks in zip(videos, all_tracks):
        scores = [(track.id, animated_score(track)) for track in vid_tracks]
        print(sorted(scores, key=itemgetter(1)))


def main():
    # video = Video.objects.get(path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4')
    # video = Video.objects.get(
    #     path='tvnews/videos/MSNBCW_20130404_060000_Hardball_With_Chris_Matthews.mp4')
    # video = Video.objects.get(
    #     path='tvnews/videos/MSNBCW_20150520_230000_Hardball_With_Chris_Matthews.mp4')
    # video = Video.objects.get(
    #     path='tvnews/videos/MSNBCW_20160915_033000_Hardball_With_Chris_Matthews.mp4')
    video = Video.objects.get(path='tvnews/videos/CNNW_20160727_000000_Anderson_Cooper_360.mp4')
    if False:
        with Timer('Deleting objects'):
            # Shot.objects.filter(video=video).delete()
            Person.objects.filter(frame__video=video).delete()
            Face.objects.filter(person__frame__video=video).delete()
            FaceFeatures.objects.filter(face__person__frame__video=video).delete()
            Frame.tags.through.objects.filter(tvnews_frame__video=video).delete()
            # Pose.objects.filter(person__frame__video=video).delete()
            # PersonTrack.objects.filter(video=video).delete()

    # log.debug('Fetching videos')
    # videos_with_shots = list(Video.objects.annotate(
    #     c=Subquery(
    #         Shot.objects.filter(video=OuterRef('pk')).values('video') \
    #         .annotate(c=Count('video')).values('c')
    #     )).filter(c__isnull=False))
    # pcache.set('videos_with_shots', videos_with_shots)

    videos_with_shots = pcache.get('videos_with_shots')

    animatedness(videos_with_shots, "chris-matthews.jpg")


if __name__ == '__main__':
    main()
