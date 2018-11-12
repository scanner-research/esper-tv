from esper.prelude import *
from collections import defaultdict
from functools import reduce
import inspect
import os

queries = []


def query(name):
    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])
    filename = module.__file__

    def wrapper(f):
        lines = inspect.getsource(f).split('\n')
        lines = lines[:-1]  # Seems to include a trailing newline

        # Hacky way to get just the function body
        i = 0
        while True:
            if "():" in lines[i]:
                break
            i = i + 1

        fn = lines[i:]
        fn += ['FN = ' + f.__name__]
        queries.append([name, '\n'.join(fn)])

        return f

    return wrapper


@query("All faces")
def all_faces():
    from query.models import Face
    from esper.stdlib import qs_to_result
    return qs_to_result(Face.objects.all(), stride=1000)


@query("All videos")
def all_videos():
    from query.models import Video
    from esper.stdlib import qs_to_result
    return qs_to_result(Video.objects.all())


#@query("Frames with a man left of a woman")
def man_left_of_woman():
    frames = []
    frames_qs = Frame.objects.annotate(
        c=Subquery(
            Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(
                c=Count('*')).values('c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        faces = list(
            FaceGender.objects.filter(
                face__frame=frame, face__labeler__name='mtcnn',
                labeler__name='rudecarnie').select_related('face', 'gender'))
        good = None
        for face1 in faces:
            for face2 in faces:
                if face1.id == face2.id: continue
                if face1.gender.name == 'male' and \
                    face2.gender.name == 'female' and \
                    face1.face.bbox_x2 < face2.face.bbox_x1 and \
                    face1.face.height() > 0.3 and face2.face.height() > 0.3:
                    good = (face1.face, face2.face)
                    break
            else:
                continue
            break
        if good is not None:
            frames.append((frame, good))

    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.id,
        'objects': [bbox_to_dict(f) for f in faces]
    } for (frame, faces) in frames], 'Frame')


#@query("Frames with two poses with two hands above head")
def two_poses_with_two_hands_above_head():
    def hands_above_head(kp):
        return kp[Pose.LWrist][1] < kp[Pose.Nose][1] and kp[Pose.RWrist][1] < kp[Pose.Nose][1]

    frames = []
    frames_qs = Frame.objects.annotate(
        c=Subquery(
            Pose.objects.filter(frame=OuterRef('pk')).values('frame').annotate(
                c=Count('*')).values('c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses(
            'pose',
            hands_above_head, [Pose.Nose, Pose.RWrist, Pose.LWrist],
            poses=Pose.objects.filter(frame=frame))
        if len(filtered) >= 2:
            frames.append((frame, filtered))

    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.id,
        'objects': [pose_to_dict(p) for p in poses]
    } for (frame, poses) in frames], 'Frame')


@query("Non-handlabeled random faces/genders")
def not_handlabeled():
    from query.models import Labeler, Tag, FaceGender
    from esper.stdlib import qs_to_result
    import random
    l = Labeler.objects.get(name='rudecarnie')
    t = Tag.objects.get(name='handlabeled-face:labeled')
    i = random.randint(0, FaceGender.objects.aggregate(Max('id'))['id__max'])
    return qs_to_result(
        FaceGender.objects.filter(labeler=l, id__gte=i).exclude(
            Q(face__frame__tags=t)
            | Q(face__shot__in_commercial=True)
            | Q(face__shot__video__commercials_labeled=False)
            | Q(face__shot__isnull=True)),
        stride=1000)


@query("Handlabeled faces/genders")
def handlabeled():
    from query.models import FaceGender
    from esper.stdlib import qs_to_result
    return qs_to_result(
        FaceGender.objects.filter(labeler__name='handlabeled-gender').annotate(
            identity=F('face__faceidentity__identity')))

@query("Cars")
def cars():
    from query.models import Object
    from esper.stdlib import qs_to_result
    return qs_to_result(Object.objects.filter(label=3, probability__gte=0.9))

@query("Donald Trump")
def donald_trump():
    from query.models import FaceIdentity
    from esper.stdlib import qs_to_result
    return qs_to_result(FaceIdentity.objects.filter(identity__name='donald trump', probability__gt=0.99))

@query('Two identities')
def two_identities():
    person1 = 'sean hannity'
    person2 = 'paul manafort'
    identity_threshold = 0.7
    def shots_with_identity(name):
        return {
            x['face__shot__id'] for x in FaceIdentity.objects.filter(
                identity__name=name.lower(), probability__gt=identity_threshold
            ).values('face__shot__id')
        }
    shots = shots_with_identity(person1) & shots_with_identity(person2)
    return qs_to_result(
        FaceIdentity.objects.filter(face__shot__id__in=list(shots)),
        limit=100000
    )

@query("Commercials")
def commercials():
    from query.models import Commercial
    from esper.stdlib import qs_to_result
    return qs_to_result(Commercial.objects.filter(labeler__name='haotian-commercials'))


@query("Positive segments")
def positive_segments():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Segment.objects.filter(labeler__name='haotian-segments',
                               polarity__isnull=False).order_by('-polarity'))


@query("Negative segments")
def negative_segments():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Segment.objects.filter(labeler__name='haotian-segments',
                               polarity__isnull=False).order_by('polarity'))


@query("Segments about Donald Trump")
def segments_about_donald_trump():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='person',
            things__name='donald trump'))

@query("Segments about North Korea")
def segments_about_north_korea():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='location',
            things__name='north korea'))


@query("Segments about immigration")
def segments_about_immigration():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='topic',
            things__name='immigration'))

@query("Sunday morning news shows")
def sunday_morning_news_shows():
    from query.models import Video
    from esper.stdlib import qs_to_result
    return qs_to_result(
        Video.objects.filter(
            time__week_day=1,
            time__hour=6))

@query("Fox News videos")
def fox_news_videos():
    from query.models import Video
    from esper.stdlib import qs_to_result
    return qs_to_result(Video.objects.filter(channel__name='FOXNEWS'))


#@query("Talking heads face tracks")
def talking_heads_tracks():
    return qs_to_result(
        PersonTrack.objects.filter(
            id__in=Person.objects.filter(frame__video__id=791) \
            .annotate(
                c=Subquery(
                    Face.objects.filter(person=OuterRef('pk')) \
                    .annotate(height=F('bbox_y2') - F('bbox_y1')) \
                    .filter(labeler__name='mtcnn', height__gte=0.3) \
                    .values('person') \
                    .annotate(c=Count('*')) \
                    .values('c'),
                    models.IntegerField())) \
            .filter(c__gt=0) \
            .values('tracks')))


#@query("Faces on Poppy Harlow")
def faces_on_poppy_harlow():
    return qs_to_result(
        Face.objects.filter(frame__video__show='CNN Newsroom With Poppy Harlow'), stride=24)


#@query("Female faces on Poppy Harlow")
def female_faces_on_poppy_harlow():
    return qs_to_result(
        Face.objects.filter(
            frame__video__show__name='CNN Newsroom With Poppy Harlow',
            facegender__gender__name='F'),
        stride=24)


#@query("Talking heads on Poppy Harlow")
def talking_heads_on_poppy_harlow():
    return qs_to_result(
        Face.objects.annotate(height=F('bbox_y2') - F('bbox_y1')).filter(
            height__gte=0.3,
            frame__video__show='CNN Newsroom With Poppy Harlow',
            facegender__gender__name='female'),
        stride=24)


#@query("Two female faces on Poppy Harlow")
def two_female_faces_on_poppy_harlow():
    r = []
    try:
        for video in Video.objects.filter(show__name='CNN Newsroom With Poppy Harlow'):
            for frame in Frame.objects.filter(video=video):
                faces = list(
                    Face.objects.annotate(height=F('bbox_y2') - F('bbox_y1')).filter(
                        labeler__name='mtcnn',
                        frame=frame,
                        facegender__gender__name='F',
                        height__gte=0.2))
                if len(faces) == 2:
                    r.append({
                        'video': frame.video.id,
                        'min_frame': frame.number,
                        'objects': [bbox_to_dict(f) for f in faces]
                    })
                if len(r) > 100:
                    raise Break()
    except Break:
        pass
    return simple_result(r, 'Frame')


#@query("Faces like Poppy Harlow")
def faces_like_poppy_harlow():
    id = 4457280
    FaceFeatures.compute_distances(id)
    return qs_to_result(
        Face.objects.filter(facefeatures__distto__isnull=False).order_by('facefeatures__distto'))


#@query("Faces unlike Poppy Harlow")
def faces_unlike_poppy_harlow():
    id = 4457280
    FaceFeatures.compute_distances(id)
    return qs_to_result(
        Face.objects.filter(facefeatures__distto__isnull=False).order_by('-facefeatures__distto'))


#@query("MTCNN missed face bboxes vs. handlabeled")
def mtcnn_vs_handlabeled():
    labeler_names = [l['labeler__name'] for l in Face.objects.values('labeler__name').distinct()]

    videos = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for frame in Frame.objects.filter(
            Q(video__show='Situation Room With Wolf Blitzer') | \
            Q(video__show='Special Report With Bret Baier')) \
        .filter(face__labeler__name='handlabeled') \
        .select_related('video') \
        .order_by('id')[:50000:5]:
        faces = list(Face.objects.filter(frame=frame).select_related('labeler'))
        has_mtcnn = any([f.labeler.name == 'mtcnn' for f in faces])
        has_handlabeled = any([f.labeler.name == 'handlabeled' for f in faces])
        if not has_mtcnn or not has_handlabeled:
            continue
        for face in faces:
            videos[frame.video.id][frame.id][face.labeler.name].append(face)

    AREA_THRESHOLD = 0.02
    DIST_THRESHOLD = 0.10

    mistakes = defaultdict(lambda: defaultdict(tuple))
    for video, frames in list(videos.items()):
        for frame, labelers in list(frames.items()):
            labeler = 'handlabeled'
            faces = labelers[labeler]
            for face in faces:
                if bbox_area(face) < AREA_THRESHOLD:
                    continue

                mistake = True
                for other_labeler in labeler_names:
                    if labeler == other_labeler: continue
                    other_faces = labelers[other_labeler] if other_labeler in labelers else []
                    for other_face in other_faces:
                        if bbox_dist(face, other_face) < DIST_THRESHOLD:
                            mistake = False
                            break

                    if mistake:
                        mistakes[video][frame] = (faces, other_faces)
                        break
                else:
                    continue
                break

    result = []
    for video, frames in list(mistakes.items())[:100]:
        for frame, (faces, other_faces) in list(frames.items()):
            result.append({
                'video': video,
                'min_frame': frame,
                'objects': [bbox_to_dict(f) for f in faces + other_faces]
            })

    return simple_result(result, 'Frame')


#@query("MTCNN missed face bboxes vs. OpenPose")
def mtcnn_vs_openpose():
    labeler_names = ['mtcnn', 'openpose']

    videos = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    frames = Frame.objects.all() \
        .annotate(c=Subquery(
            Pose.objects.filter(frame=OuterRef('pk')).values('frame') \
            .annotate(c=Count('*')).values('c'), models.IntegerField())) \
        .filter(c__gt=0) \
        .select_related('video') \
        .order_by('id')
    for frame in frames[:50000:5]:
        faces = list(Face.objects.filter(frame=frame))
        poses = list(Pose.objects.filter(frame=frame))
        for face in faces:
            videos[frame.video.id][frame.id]['mtcnn'].append(face)
        for pose in poses:
            videos[frame.video.id][frame.id]['openpose'].append(pose)

    AREA_THRESHOLD = 0.02
    DIST_THRESHOLD = 0.10

    mistakes = defaultdict(lambda: defaultdict(tuple))
    for video, frames in list(videos.items()):
        for frame, labelers in list(frames.items()):
            labeler = 'openpose'
            faces = labelers[labeler]
            for face in faces:
                if bbox_area(face) < AREA_THRESHOLD:
                    continue

                mistake = True
                for other_labeler in labeler_names:
                    if labeler == other_labeler: continue
                    other_faces = labelers[other_labeler] if other_labeler in labelers else []
                    for other_face in other_faces:
                        if bbox_dist(face, other_face) < DIST_THRESHOLD:
                            mistake = False
                            break

                    if mistake and len(other_faces) > 0:
                        mistakes[video][frame] = (faces, other_faces)
                        break
                else:
                    continue
                break

    result = []
    for video, frames in list(mistakes.items())[:100]:
        for frame, (faces, other_faces) in list(frames.items()):
            result.append({
                'video': video,
                'min_frame': frame,
                'objects': [bbox_to_dict(f) for f in other_faces + faces]
            })

    return simple_result(result, 'Frame')


#@query("People sitting")
def people_sitting():
    def is_sitting(kp):
        def ang(v):
            return math.atan2(v[1], v[0]) / math.pi * 180

        def is_angled(v):
            v /= np.linalg.norm(v)
            v[1] = -v[1]  # correct for image coordinates
            a = ang(v)
            return a > 0 or a < -140

        return is_angled(kp[Pose.LKnee] - kp[Pose.LHip]) or is_angled(
            kp[Pose.RKnee] - kp[Pose.RHip])

    frames_qs = Frame.objects.filter(video__channel='CNN') \
        .annotate(
            pose_count=Subquery(
                Pose.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')),
            woman_count=Subquery(
                Face.objects.filter(frame=OuterRef('pk'), facegender__gender__name='female').values('frame').annotate(c=Count('*')).values('c'),
                models.IntegerField())) \
        .filter(pose_count__gt=0, pose_count__lt=6, woman_count__gt=0).order_by('id').select_related('video')

    frames = []
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses(
            'pose',
            is_sitting, [Pose.LAnkle, Pose.LKnee, Pose.RAnkle, Pose.RKnee, Pose.RHip, Pose.LHip],
            poses=Pose.objects.filter(frame=frame))

        if len(filtered) > 0:
            frames.append((frame, filtered))

    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.number,
        'objects': [pose_to_dict(p) for p in poses]
    } for (frame, poses) in frames], 'Frame')


#@query("Obama pictures")
def obama_pictures():
    def close(x, y):
        return abs(x - y) < 0.02

    id = 3938394
    FaceFeatures.compute_distances(id)
    sq = Face.objects.filter(
        tracks=OuterRef('pk'), labeler__name='mtcnn',
        facefeatures__distto__lte=1.0).values('tracks').annotate(c=Count('*'))
    out_tracks = []

    face_tracks = {}  #{t.id: (t, []) for t in tracks}
    for track in \
        PersonTrack.objects.filter(labeler__name='featuretrack') \
        .annotate(
            duration=Track.duration(),
            c=Subquery(sq.values('c'), models.IntegerField())) \
        .filter(duration__gt=0, c__gt=0):

        faces = list(
            Face.objects.filter(tracks=track,
                                labeler__name='mtcnn').select_related('frame'))
        face_tracks[track.id] = (track, faces)

    for track, faces in list(face_tracks.values()):
        faces.sort(lambda a, b: a.person.frame.number - b.person.frame.number)
        valid = True
        for i in range(len(faces) - 1):
            if not (close(faces[i].bbox_x1, faces[i + 1].bbox_x1)
                    and close(faces[i].bbox_y1, faces[i + 1].bbox_y1)
                    and close(faces[i].bbox_x2, faces[i + 1].bbox_x2)
                    and close(faces[i].bbox_y2, faces[i + 1].bbox_y2)):
                valid = False
                break
        if valid:
            out_tracks.append((track, faces[0]))

    return simple_result([{
        'video': t.video_id,
        'min_frame': Frame.objects.get(video=t.video, number=t.min_frame).id,
        'max_frame': Frame.objects.get(video=t.video, number=t.max_frame).id,
        'objects': [bbox_to_dict(f)]
    } for (t, f) in out_tracks], 'FaceTrack')

@query("Frames with two women")
def frames_with_two_women():
    face_qs = FaceGender.objects.filter(gender__name='F', face__shot__in_commercial=False)
    frames = list(Frame.objects.annotate(c=qs_child_count(face_qs, 'face__frame')) \
        .filter(c=2)[:1000:10])

    return qs_to_result(face_qs.filter(face__frame__in=frames))

def panels():
    from query.base_models import BoundingBox
    from query.models import Labeler, Face, Frame
    from esper.stdlib import qs_to_result
    from django.db.models import OuterRef, Count, IntegerField

    mtcnn = Labeler.objects.get(name='mtcnn')
    face_qs = Face.objects.annotate(height=BoundingBox.height_expr()).filter(
        height__gte=0.25, labeler=mtcnn, shot__in_commercial=False)
    frames = Frame.objects.annotate(c=Subquery(
        face_qs.filter(frame=OuterRef('pk')) \
        .values('frame') \
        .annotate(c=Count('*')) \
        .values('c'), IntegerField())) \
        .filter(c__gte=3, c__lte=3).order_by('id')

    output_frames = []
    for frame in frames[:10000:10]:
        faces = list(face_qs.filter(frame=frame))
        y = faces[0].bbox_y1
        valid = True
        for i in range(1, len(faces)):
            if abs(faces[i].bbox_y1 - y) > 0.05:
                valid = False
                break
        if valid:
            output_frames.append((frame, faces))

    return output_frames


@query("Panels")
def panels_():
    from esper.queries import panels
    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.number,
        'objects': [bbox_to_dict(f) for f in faces]
    } for (frame, faces) in panels()], 'Frame')


#@query("Animated Rachel Maddow")
def animated_rachel_maddow():
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

    tracks = list(PersonTrack.objects.filter(video__path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4') \
        .annotate(c=Subquery(
            Face.objects.filter(tracks=OuterRef('pk')) \
            .filter(labeler__name='tinyfaces', facefeatures__distto__isnull=False, facefeatures__distto__lte=1.0) \
            .values('tracks')
            .annotate(c=Count('*'))
            .values('c'), models.IntegerField()
            )) \
        .filter(c__gt=0))

    all_dists = []
    for track in tracks:
        poses = list(Pose.objects.filter(tracks=track).order_by('frame__number'))
        dists = [pose_dist(poses[i], poses[i + 1]) for i in range(len(poses) - 1)]
        all_dists.append((track, np.mean(dists)))
    all_dists.sort(key=itemgetter(1), reverse=True)

    return simple_result([{
        'video':
        t.video.id,
        'track':
        t.id,
        'min_frame':
        Frame.objects.get(video=t.video, number=t.min_frame).id,
        'max_frame':
        Frame.objects.get(video=t.video, number=t.max_frame).id,
        'metadata': [['score', '{:.03f}'.format(score)]],
        'objects':
        [bbox_to_dict(Face.objects.filter(frame__number=t.min_frame, tracks=t)[0])]
    } for t, score in all_dists], 'PersonTrack')


@query("Audio labels")
def audio_labels():
    from query.models import Speaker
    from esper.stdlib import qs_to_result
    return qs_to_result(Speaker.objects.all(), group=True, limit=10000)


@query("Topic labels")
def all_topics():
    from query.models import Segment
    from esper.stdlib import qs_to_result
    return qs_to_result(Segment.objects.filter(labeler__name='handlabeled-topic'), group=True, limit=10000)


@query("Random videos w/o topic labels")
def random_without_topics():
    from query.models import Video, Thing
    import random
    t = Tag.objects.get(name='handlabeled-topic:labeled')
    i = random.randint(0, Video.objects.aggregate(Max('id'))['id__max'])

    videos = Video.objects.filter(id__gte=i).exclude(videotag__tag=t)
    return {
        'result':[{
            'type': 'contiguous',
            'elements': [{
                'video': v.id,
                'min_frame': 0,
                'max_frame': v.num_frames - 1,
                'things': []
            }]
        } for v in videos[:1000:10]]
    }


@query("Non-handlabeled random audio")
def nonhandlabeled_random_audio():
    from query.models import Video, Speaker, Commercial
    from esper.stdlib import qs_to_result
    from django.db.models import Subquery, Count

    videos = Video.objects.annotate(
        c=Subquery(
            Speaker.objects.filter(video=OuterRef('pk')).values('video').annotate(
                c=Count('video')).values('c'))) \
        .filter(c__gt=0).order_by('?')[:3]

    conds = []
    for v in videos:
        commercials = list(Commercial.objects.filter(video=v).values())
        dur = int(300 * v.fps)
        for i in range(10):
            start = random.randint(0, v.num_frames - dur - 1)
            end = start + dur
            in_commercial = False
            for c in commercials:
                minf, maxf = (c['min_frame'], c['max_frame'])
                if (minf <= start and start <= max) or (minf <= end and end <= maxf) \
                    or (start <= minf and minf <= end and start <= maxf and maxf <= end):
                    in_commercial = True
                    break
            if not in_commercial:
                break
        else:
            continue
        conds.append({'video': v, 'min_frame__gte': start, 'max_frame__lte': end})

    return qs_to_result(
        Speaker.objects.filter(labeler__name='lium').filter(
            reduce(lambda a, b: a | b, [Q(**c) for c in conds])),
        group=True,
        limit=None)


@query("Caption search")
def caption_search():
    from esper.captions import topic_search
    from query.models import Video

    results = topic_search(['TACO BELL'])
    videos = {v.id: v for v in Video.objects.all()}

    def convert_time(k, t):
        return int((t - 7) * videos[k].fps)

    flattened = [(v.id, l.start, l.end) for v in results.documents for l in v.locations]
    random.shuffle(flattened)
    return simple_result([{
        'video': k,
        'min_frame': convert_time(k, t1),
        'max_frame': convert_time(k, t2)
    } for k, t1, t2 in flattened[:100]], '_')


@query('Face search')
def face_search():
    emb = embed_google_images.name_to_embedding('Wolf Blitzer')
    face_ids = [x for x, _ in face_knn(features=emb, max_threshold=0.4)][::10]
    return qs_to_result(
        Face.objects.filter(id__in=face_ids), custom_order_by_id=face_ids, limit=len(face_ids))


@query('Groups of faces by distance threshold')
def groups_of_faces_by_distance_threshold():
    emb = embed_google_images.name_to_embedding('Wolf Blitzer')

    increment = 0.05
    min_thresh = 0.0
    max_thresh = 1.0
    max_results_per_group = 50
    exclude_labeled = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    face_sims = face_knn(features=emb, min_threshold=min_thresh, max_threshold=max_thresh)

    results_by_bucket = {}
    for t in frange(min_thresh, max_thresh, increment):
        face_ids = [x for x, _ in filter(lambda z: z[1] >= t and z[1] < t + increment, face_sims)]
        if len(face_ids) != 0:
            faces = face_qs.filter(
                id__in=random.sample(face_ids, k=min(len(face_ids), max_results_per_group))
            ).distinct('frame__video')
            if faces.count() == 0:
                continue
            results = qs_to_result(faces, limit=max_results_per_group, custom_order_by_id=face_ids)
            results_by_bucket[(t, t + increment, len(face_ids))] = results

    if len(results_by_bucket) == 0:
        raise Exception('No results to show')

    agg_results = [('in range=({:0.2f}, {:0.2f}), count={}'.format(k[0], k[1], k[2]), results_by_bucket[k])
                   for k in sorted(results_by_bucket.keys())]

    return group_results(agg_results)


@query('Face search by id')
def face_search_by_id():
     # Wolf Blitzer
#     target_face_ids = [975965, 5254043, 844004, 105093, 3801699, 4440669, 265071]
#     not_target_face_ids =  [
#         1039037, 3132700, 3584906, 2057919, 3642645, 249473, 129685, 2569834, 5366608,
#         4831099, 2172821, 1981350, 1095709, 4427683, 1762835]

    # Melania Trump
#     target_face_ids = [
#         2869846, 3851770, 3567361, 401073, 3943919, 5245641, 198592, 5460319, 5056617,
#         1663045, 3794909, 1916340, 1373079, 2698088, 414847, 4608072]
#     not_target_face_ids = []

    # Bernie Sanders
    target_face_ids = [
        644710, 4686364, 2678025, 62032, 13248, 4846879, 4804861, 561270, 2651257,
        2083010, 2117202, 1848221, 2495606, 4465870, 3801638, 865102, 3861979, 4146727,
        3358820, 2087225, 1032403, 1137346, 2220864, 5384396, 3885087, 5107580, 2856632,
        335131, 4371949, 533850, 5384760, 3335516]
    not_target_face_ids = [
        2656438, 1410140, 4568590, 2646929, 1521533, 1212395, 178315, 1755096, 3476158,
        3310952, 1168204, 3062342, 1010748, 1275607, 2190958, 2779945, 415610, 1744917,
        5210138, 3288162, 5137166, 4169061, 3774070, 2595170, 382055, 2365443, 712023,
        5214225, 178251, 1039121, 5336597, 525714, 4522167, 3613622, 5161408, 2091095,
        741985, 521, 2589969, 5120596, 284825, 3361576, 1684384, 4437468, 5214225,
        178251]


    increment = 0.05
    min_thresh = 0.0
    max_thresh = 1.0
    max_results_per_group = 50
    exclude_labeled = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    face_sims = face_knn(ids=target_face_ids, min_threshold=min_thresh, max_threshold=max_thresh,
                         not_ids=not_target_face_ids)

    face_sims_by_bucket = {}
    idx = 0
    max_idx = len(face_sims)
    for t in frange(min_thresh, max_thresh, increment):
        start_idx = idx
        cur_thresh = t + increment
        while idx < max_idx and face_sims[idx][1] < cur_thresh:
            idx += 1
        face_sims_by_bucket[t] = face_sims[start_idx:idx]

    results_by_bucket = {}
    for t in frange(min_thresh, max_thresh, increment):
        face_ids = [x for x, _ in face_sims_by_bucket[t]]
        if len(face_ids) != 0:
            faces = face_qs.filter(
                id__in=random.sample(face_ids, k=min(len(face_ids), max_results_per_group))
            ).distinct('frame__video')
            if faces.count() == 0:
                continue
            results = qs_to_result(faces, limit=max_results_per_group, custom_order_by_id=face_ids)
            results_by_bucket[(t, t + increment, len(face_ids))] = results

    if len(results_by_bucket) == 0:
        raise Exception('No results to show')

    agg_results = [('in range=({:0.2f}, {:0.2f}), count={}'.format(k[0], k[1], k[2]), results_by_bucket[k])
                   for k in sorted(results_by_bucket.keys())]

    return group_results(agg_results)


# @query('Face search using svm by id')
# def face_search_svm_by_id():
#     # Wolf Blitzer
# #     target_face_ids = [975965, 5254043, 844004, 105093, 3801699, 4440669, 265071]
# #     not_target_face_ids =  [
# #         1039037, 3132700, 3584906, 2057919, 3642645, 249473, 129685, 2569834, 5366608,
# #         4831099, 2172821, 1981350, 1095709, 4427683, 1762835]

#     # Melania Trump
#     target_face_ids = [
#         2869846, 3851770, 3567361, 401073, 3943919, 5245641, 198592, 5460319, 5056617,
#         1663045, 3794909, 1916340, 1373079, 2698088, 414847, 4608072]
#     not_target_face_ids = []

#     # Bernie Sanders
#     # target_face_ids = [
#     #     644710, 4686364, 2678025, 62032, 13248, 4846879, 4804861, 561270, 2651257,
#     #     2083010, 2117202, 1848221, 2495606, 4465870, 3801638, 865102, 3861979, 4146727,
#     #     3358820, 2087225, 1032403, 1137346, 2220864, 5384396, 3885087, 5107580, 2856632,
#     #     335131, 4371949, 533850, 5384760, 3335516]
#     # not_target_face_ids = [
#     #     2656438, 1410140, 4568590, 2646929, 1521533, 1212395, 178315, 1755096, 3476158,
#     #     3310952, 1168204, 3062342, 1010748, 1275607, 2190958, 2779945, 415610, 1744917,
#     #     5210138, 3288162, 5137166, 4169061, 3774070, 2595170, 382055, 2365443, 712023,
#     #     5214225, 178251, 1039121, 5336597, 525714, 4522167, 3613622, 5161408, 2091095,
#     #     741985, 521, 2589969, 5120596, 284825, 3361576, 1684384, 4437468, 5214225,
#     #     178251]

#     increment = 0.2
#     min_thresh = -5.0
#     max_thresh = 1.0
#     max_results_per_group = 50
#     exclude_labeled = False

#     face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

#     face_scores = face_svm(target_face_ids, not_target_face_ids, 1000, 500, min_thresh, max_thresh)

#     face_scores_by_bucket = {}
#     idx = 0
#     max_idx = len(face_scores)
#     for t in frange(min_thresh, max_thresh, increment):
#         start_idx = idx
#         cur_thresh = t + increment
#         while idx < max_idx and face_scores[idx][1] < cur_thresh:
#             idx += 1
#         face_scores_by_bucket[t] = face_scores[start_idx:idx]

#     results_by_bucket = {}
#     for t in frange(min_thresh, max_thresh, increment):
#         face_ids = [x for x, _ in face_scores_by_bucket[t]]
#         if len(face_ids) != 0:
#             faces = face_qs.filter(
#                 id__in=random.sample(face_ids, k=min(len(face_ids), max_results_per_group))
#             ).distinct('frame__video')
#             if faces.count() == 0:
#                 continue
#             results = qs_to_result(faces, limit=max_results_per_group, custom_order_by_id=face_ids)
#             results_by_bucket[(t, t + increment, len(face_ids))] = results

#     if len(results_by_bucket) == 0:
#         raise Exception('No results to show')

#     agg_results = [('in range=({:0.2f}, {:0.2f}), count={}'.format(k[0], k[1], k[2]), results_by_bucket[k])
#                    for k in sorted(results_by_bucket.keys())]

#     return group_results(agg_results)


@query('Face search with exclusions')
def face_search_with_exclusion():
    def exclude_faces(face_ids, exclude_ids, exclude_thresh):
        excluded_face_ids = set()
        for exclude_id in exclude_ids:
            excluded_face_ids.update([x for x, _ in face_knn(id=exclude_id, max_threshold=exclude_thresh)])
        face_ids = set(face_ids)
        return face_ids - excluded_face_ids, face_ids & excluded_face_ids

    # Some params
    exclude_labeled = False
    show_excluded = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    name = 'Wolf Blitzer'

    emb = embed_google_images.name_to_embedding(name)
    face_ids = [x for x, _ in face_knn(features=emb, max_threshold=0.6)]

    kept_ids, excluded_ids = exclude_faces(
        face_ids,
        [1634585, 531076, 3273872, 2586010, 921211, 3176879, 3344886, 3660089, 249499, 2236580],
        0.4)

    if show_excluded:
        # Show the furthest faces that we kept and the faces that were excluded
        kept_results = qs_to_result(face_qs.filter(id__in=kept_ids, shot__in_commercial=False),
                                    custom_order_by_id=face_ids[::-1])
        excluded_results = qs_to_result(face_qs.filter(id__in=excluded_ids, shot__in_commercial=False))

        return group_results([('excluded', excluded_results), (name, kept_results)])
    else:
        # Show all of the faces that were kept
        return qs_to_result(face_qs.filter(id__in=kept_ids, shot__in_commercial=False),
                            custom_order_by_id=face_ids,limit=len(face_ids))


@query('Other people who are on screen with X')
def face_search_for_other_people():
    name = 'sean spicer'
    precision_thresh = 0.95
    blurriness_thresh = 10.
    n_clusters = 100
    n_examples_per_cluster = 10

    selected_face_ids = [
        x['face__id'] for x in FaceIdentity.objects.filter(
            identity__name=name, probability__gt=precision_thresh
        ).values('face__id')[:100000] # size limit
    ]

    shot_ids = [
        x['shot__id'] for x in Face.objects.filter(
            id__in=selected_face_ids
        ).distinct('shot').values('shot__id')
    ]

    other_face_ids = [
        x['id'] for x in
        Face.objects.filter(
            shot__id__in=shot_ids,
            blurriness__gt=blurriness_thresh
        ).exclude(id__in=selected_face_ids).values('id')
    ]

    clusters = defaultdict(list)
    for (i, c) in face_kmeans(other_face_ids, k=n_clusters):
        clusters[c].append(i)

    results = []
    for _, ids in sorted(clusters.items(), key=lambda x: -len(x[1])):
        results.append((
            'Cluster with {} faces'.format(len(ids)),
            qs_to_result(Face.objects.filter(id__in=ids).distinct('shot__video'),
                         limit=n_examples_per_cluster)
        ))
    return group_results(results)


@query('Identity across major shows')
def identity_across_shows():
    from query.models import FaceIdentity
    from esper.stdlib import qs_to_result
    from esper.major_canonical_shows import MAJOR_CANONICAL_SHOWS

    name='hillary clinton'

    results = []
    for show in sorted(MAJOR_CANONICAL_SHOWS):
        qs = FaceIdentity.objects.filter(
            identity__name=name,
            face__shot__video__show__canonical_show__name=show,
            probability__gt=0.9
        )
        if qs.count() > 0:
            results.append(
                (show, qs_to_result(qs, shuffle=True, limit=10))
            )
    return group_results(results)


@query('Host with other still face')
def shots_with_host_and_still_face():
    from query.models import FaceIdentity
    from esper.stdlib import qs_to_result
    from collections import defaultdict

    host_name = 'rachel maddow'
    probability_thresh = 0.9
    host_face_height_thresh = 0.2
    other_face_height_thresh = 0.1
    host_to_other_size_ratio = 1.2 # 20% larger
    max_other_faces = 2

    shots_to_host = {
        x['face__shot__id']: (
            x['face__id'], x['face__bbox_x1'], x['face__bbox_x2'],
            x['face__bbox_y1'], x['face__bbox_y2']
        ) for x in FaceIdentity.objects.filter(
            identity__name=host_name, probability__gt=0.8,
        ).values(
            'face__id', 'face__shot__id', 'face__bbox_x1', 'face__bbox_x2',
            'face__bbox_y1', 'face__bbox_y2',
        )
    }

    def host_bbox_filter(x1, x2, y1, y2):
        # The host should be entirely on one side of the frame
        if not x1 > 0.5 and not x2 < 0.5:
            return False
        if not y2 - y1 > host_face_height_thresh:
            return False
        return True

    shots_to_host = {
        k : v for k, v in shots_to_host.items() if host_bbox_filter(*v[1:])
    }
    assert len(shots_to_host) > 0, 'No shots with host found'

    shots_to_other_faces = defaultdict(list)
    for x in Face.objects.filter(
                shot__id__in=list(shots_to_host.keys())
            ).exclude(
                id__in=[x[0] for x in shots_to_host.values()] # Host faces
            ).values(
                'shot__id', 'bbox_x1', 'bbox_x2', 'bbox_y1', 'bbox_y2'
            ):
        shot_id = x['shot__id']
        bbox = (x['bbox_x1'], x['bbox_x2'], x['bbox_y1'], x['bbox_y2'])
        shots_to_other_faces[shot_id].append(bbox)

    def shot_filter(bbox_list):
        if len(bbox_list) > max_other_faces:
            return False

        result = False
        for x1, x2, y1, y2 in bbox_list:
            _, hx1, hx2, hy1, hy2 = shots_to_host[shot_id] # Host coordinates
            # All other faces hould be on different side from host
            if (hx2 < 0.5 and x2 < 0.5) or (hx1 > 0.5 and x1 > 0.5):
                return False
            # All other faces should be smaller than the host face
            if (hy2 - hy1) / (y2 - y1) < host_to_other_size_ratio:
                return False

            result |= y2 - y1 >= other_face_height_thresh
        return result

    selected_shots = {
        shot_id for shot_id, bbox_list in shots_to_other_faces.items()
        if shot_filter(bbox_list)
    }
    assert len(selected_shots) > 0, 'No shots selected for display'

    return qs_to_result(
        Face.objects.filter(shot__id__in=list(selected_shots)),
        limit=100000
    )

@query('Hand-labeled Interviews (Sandbox)')
def handlabeled_interviews():
    from query.models import LabeledInterview
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    interviews = LabeledInterview.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(interviews))

@query('Hand-labeled Panels (Sandbox)')
def handlabeled_panels():
    from query.models import LabeledPanel
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    panels = LabeledPanel.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(panels))

@query('Hand-labeled Commercials (Sandbox)')
def handlabeled_commercials():
    from query.models import LabeledCommercial
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    commercials = LabeledCommercial.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(commercials))

@query('Multiple Timelines (Sandbox)')
def multiple_timelines():
    from query.models import LabeledInterview, LabeledPanel, LabeledCommercial
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result, add_intrvllists_to_result

    interviews = LabeledInterview.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))
    panels = LabeledPanel.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))
    commercials = LabeledCommercial.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    result = intrvllists_to_result(qs_to_intrvllists(interviews))
    add_intrvllists_to_result(result, qs_to_intrvllists(panels), color="blue")
    add_intrvllists_to_result(result, qs_to_intrvllists(commercials), color="purple")

    return result
