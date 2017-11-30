from query.datasets.prelude import *
from collections import defaultdict
import inspect

queries = defaultdict(list)


def query(name):
    frame = inspect.stack()[1]
    module = inspect.getmodule(frame[0])
    filename = module.__file__
    dataset = os.path.abspath(filename).split('/')[-2]

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
        queries[dataset].append([name, '\n'.join(fn)])

        return f

    return wrapper


@query("All faces")
def all_faces():
    return qs_to_result(Face.objects.all(), group=True)


@query("All videos")
def all_videos():
    return qs_to_result(Frame.objects.filter(number=0))


@query("Frames with a man left of a woman")
def man_left_of_woman():
    frames = []
    frames_qs = Frame.objects.annotate(c=Subquery(
        Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values(
            'c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        faces = list(
            Face.objects.filter(frame=frame, labeler__name='mtcnn').select_related('gender'))
        good = None
        for face1 in faces:
            for face2 in faces:
                if face1.id == face2.id: continue
                if face1.gender.name == 'male' and \
                    face2.gender.name == 'female' and \
                    face1.bbox_x2 < face2.bbox_x1 and \
                    face1.height() > 0.3 and face2.height() > 0.3:
                    good = (face1, face2)
                    break
            else:
                continue
            break
        if good is not None:
            frames.append((frame, good))

    return simple_result([{
        'video': frame.video.id,
        'start_frame': frame.id,
        'objects': [bbox_to_dict(f) for f in faces]
    } for (frame, faces) in frames], 'Frame')


@query("Frames with two poses with two hands above head")
def two_poses_with_two_hands_above_head():
    def hands_above_head(kp):
        return kp[Pose.LWrist][1] < kp[Pose.Nose][1] and kp[Pose.RWrist][1] < kp[Pose.Nose][1]

    frames = []
    frames_qs = Frame.objects.annotate(c=Subquery(
        Pose.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values(
            'c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses(
            'pose',
            hands_above_head, [Pose.Nose, Pose.RWrist, Pose.LWrist],
            poses=Pose.objects.filter(frame=frame))
        if len(filtered) >= 2:
            frames.append((frame, filtered))

    return simple_result([{
        'video': frame.video.id,
        'start_frame': frame.id,
        'objects': [pose_to_dict(p) for p in poses]
    } for (frame, poses) in frames], 'Frame')
