from query.datasets.prelude import *
from query.datasets.tvnews.shot_detect import shot_detect
from query.datasets.tvnews.face_detect import face_detect
from query.datasets.tvnews.face_embed import face_embed
from query.datasets.tvnews.pose_detect import pose_detect
from sklearn.neighbors import NearestNeighbors
import traceback

FEATURE_DISTANCE_THRESHOLD = 1.0
POSE_STRIDE = 3


def shot_frame_to_detect(shot):
    return (shot.min_frame + shot.max_frame) / 2


# Simple K-NN based identity detector
def identity_detect(videos, exemplar, features):
    log.debug('Loading features')
    ids, vectors = zip(*[((i, j), f.load_features())
                         for i, vid_features in enumerate(features)
                         for j, f in enumerate(vid_features)])

    log.debug('Building k-nn tree')
    feat_nn = NearestNeighbors().fit(np.vstack(vectors))

    log.debug('Doing look-up')
    exemplar_vector = FaceFeatures.objects.get(
        face=exemplar, labeler__name='facenet').load_features()
    dists, id_indices = feat_nn.kneighbors([exemplar_vector], min(10000, len(vectors)))

    face_map = defaultdict(list)
    for (dist, k) in zip(dists[0], id_indices[0]):
        (i, j) = ids[k]
        if dist > FEATURE_DISTANCE_THRESHOLD:
            break

        face_map[videos[i].id].append(features[i][j])

    return [face_map[video.id] for video in videos]


# Remove faces with negative coords and small height
def filter_invalid_faces(all_faces):
    def inrange(v):
        return 0 <= v and v <= 1

    def valid_bbox(f):
        return f.bbox_y2 - f.bbox_y1 >= .1 and inrange(f.bbox_x1) and inrange(f.bbox_x2) \
            and inrange(f.bbox_y1) and inrange(f.bbox_y2)

    return [[f for f in vid_faces if valid_bbox(f)] for vid_faces in all_faces]


# Get shots corresponding to matched faces
def features_to_shots(matching_features, all_shots, frame_per_shot):
    all_shot_maps = [{frame: shot
                      for shot, frame in zip(vid_shots, vid_frames)}
                     for vid_shots, vid_frames in zip(all_shots, frame_per_shot)]

    return [[shot_map[f.face.person.frame.number] for f in vid_features]
            for vid_features, shot_map in zip(matching_features, all_shot_maps)]


def closest_pose(candidates, target):
    if len(candidates) == 0: return None
    noses = [pose.pose_keypoints()[Pose.Nose] for pose in candidates]
    filtered_noses = [(nose[:2], i) for i, nose in enumerate(noses) if nose[2] > 0]
    if len(filtered_noses) == 0: return None
    noses, indices = zip(*filtered_noses)
    target = target.pose_keypoints()[Pose.Nose][:2] if type(target) is not np.ndarray else target
    dists = np.linalg.norm(np.array(noses) - target, axis=1)
    closest = candidates[indices[np.argmin(dists)]]
    return closest


def pose_track(videos, matching_shots, matching_features, all_poses, force=False):
    labeler, _ = Labeler.objects.get_or_create(name='posetrack')
    if not force and PersonTrack.objects.filter(video=videos[0], labeler=labeler).exists():
        return [list(PersonTrack.objects.filter(video=video, labeler=labeler)) for video in videos]

    all_tracks = []
    for (video, vid_shots, vid_features, vid_poses) in zip(videos, matching_shots,
                                                           matching_features, all_poses):
        pose_map = defaultdict(list)
        for pose in vid_poses:
            pose_map[pose.person.frame.number].append(pose)

        log.debug('Finding tracks')
        vid_tracks = []
        for shot, features in zip(vid_shots, vid_features):
            mid_frame = shot_frame_to_detect(shot)
            initial_poses = pose_map[mid_frame]
            track_initial = closest_pose(pose_map[mid_frame], bbox_midpoint(features.face))
            track = [track_initial]
            if track_initial is None:
                continue

            shot_frames = range(shot.min_frame, shot.max_frame, POSE_STRIDE)
            lower = [n for n in shot_frames if n < mid_frame]
            upper = [n for n in shot_frames if n > mid_frame]

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

            person = features.face.person
            track_initial.person = person
            person_track = PersonTrack(
                video=video,
                labeler=labeler,
                min_frame=track[0].person.frame.number,
                max_frame=track[-1].person.frame.number)

            vid_tracks.append([track, person_track])

        log.debug('Creating')
        PersonTrack.objects.bulk_create([p for _, p in vid_tracks])

        log.debug('Adding to tracks?')
        ThroughModel = Person.tracks.through
        links = []
        for track, person_track in vid_tracks:
            for pose in track:
                links.append(
                    ThroughModel(
                        tvnews_person_id=pose.person.pk, tvnews_persontrack_id=person_track.pk))
        ThroughModel.objects.bulk_create(links)

        log.debug('Updating')
        Pose.objects.bulk_update(sum([p for p, _ in vid_tracks], []))
        all_tracks.append([p for _, p in vid_tracks])

    return all_tracks

# Concrete TODO
# 1. Improve shot detection (better debug, better parameters, better method?)
# 2. Run full pipeline on a few videos to get stats on total runtime, runtime
#    of each stage, number of frames filtered, etc.
# 3. Integrate optimizations as necessary for efficiency or accuracy

# MAIN TODOs:
# 1. Devise a plan for downloading/processing full dataset
# 2. Get a state of the world (current data, annotations) and desired state (all tasks we want irrespective of length)

def pose_detect_for_person(videos, exemplar):
    log.debug('Detecting shots')
    all_shots = shot_detect(videos)
    face_frame_per_shot = [[shot_frame_to_detect(shot) for shot in vid_shots]
                           for vid_shots in all_shots]

    log.debug('Detecting faces')
    all_faces = face_detect(videos, face_frame_per_shot)
    filtered_faces = filter_invalid_faces(all_faces)

    log.debug('Embedding faces')
    features = face_embed(videos, filtered_faces)

    log.debug('Detecting identities')
    matching_features = identity_detect(videos, exemplar, features)

    log.debug('Matching features to shots')
    matching_shots = features_to_shots(matching_features, all_shots, face_frame_per_shot)
    pose_frames_per_shot = [
        sum([
            sorted(
                list(
                    set(range(shot.min_frame, shot.max_frame + 1, POSE_STRIDE)) | set(
                        [shot_frame_to_detect(shot)]))) for shot in vid_shots
        ], []) for vid_shots in matching_shots
    ]

    print(len(pose_frames_per_shot[0]))

    # Can filter poses if faces is large and y position is not too high in image
    log.debug('Detecting poses')
    all_poses = pose_detect(videos, pose_frames_per_shot, force=True)

    log.debug('Tracking poses')
    tracks = pose_track(videos, matching_shots, matching_features, all_poses)

    return tracks


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
    return np.mean(dists)

# TODO:
# 1. Draw poses on top of video
# 2. Need better way to debug shots
# 3. Get Esper hooked up on Ocean
# 4. Ask where person is more animated than usual

def animatedness(videos, exemplar):
    all_tracks = pose_detect_for_person(videos, exemplar)
    for video, vid_tracks in zip(videos, all_tracks):
        scores = [(track.id, animated_score(track)) for track in vid_tracks]
        print(sorted(scores, key=itemgetter(1)))


def main():
    # video = Video.objects.get(path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4')
    video = Video.objects.get(
        path='tvnews/videos/MSNBCW_20130404_060000_Hardball_With_Chris_Matthews.mp4')
    if False:
        # Shot.objects.filter(video=video).delete()
        Person.objects.filter(frame__video=video).delete()
        Face.objects.filter(person__frame__video=video).delete()
        FaceFeatures.objects.filter(face__person__frame__video=video).delete()
        Pose.objects.filter(person__frame__video=video).delete()
        PersonTrack.objects.filter(video=video).delete()
    rachel_id = 107838
    chris_id = 113005
    animatedness([video], chris_id)


if __name__ == '__main__':
    main()
