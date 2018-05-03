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
    return qs_to_result(Face.objects.all(), stride=1000)


@query("All videos")
def all_videos():
    return qs_to_result(Video.objects.all())


#@query("Frames with a man left of a woman")
def man_left_of_woman():
    frames = []
    frames_qs = Frame.objects.annotate(
        c=Subquery(
            Face.objects.filter(person__frame=OuterRef('pk')).values('person__frame').annotate(
                c=Count('*')).values('c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        faces = list(
            FaceGender.objects.filter(
                face__person__frame=frame, face__labeler__name='mtcnn',
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
            Pose.objects.filter(person__frame=OuterRef('pk')).values('person__frame').annotate(
                c=Count('*')).values('c'))).filter(c__gt=0).order_by('id').select_related('video')
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses(
            'pose',
            hands_above_head, [Pose.Nose, Pose.RWrist, Pose.LWrist],
            poses=Pose.objects.filter(person__frame=frame))
        if len(filtered) >= 2:
            frames.append((frame, filtered))

    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.id,
        'objects': [pose_to_dict(p) for p in poses]
    } for (frame, poses) in frames], 'Frame')


@query('Groups of faces by distance threshold')
def groups_of_faces_by_distance_threshold():

    def frange(x, y, jump):
        while x < y:
            yield x
            x += jump

    def group_multiple_results(agg_results):
        groups = []
        count = 0
        ty_name = None
        for label, result in agg_results:
            ty_name = result['type']
            count += result['count']
            elements = [x['elements'][0] for x in result['result']]
            groups.append({'type': 'flat', 'label': label, 'elements': elements})
            
        return  {'result': groups, 'count': count, 'type': ty_name}

    emb = embed_google_images.name_to_embedding('Wolf Blitzer')
    
    increment = 0.05
    min_thresh = 0.0
    max_thresh = 1.0
    max_results_per_group = 50
    exclude_labeled = True

    if exclude_labeled:
        face_qs = UnlabeledFace.objects
    else:
        face_qs = Face.objects
   
    results_by_bucket = {}
    for t in frange(min_thresh, max_thresh, increment):
        face_ids = face_knn(features=emb, min_threshold=t, max_threshold=t + increment)
        if len(face_ids) != 0:
            faces = face_qs.filter(id__in=face_ids[:max_results_per_group]).distinct('person__frame__video')
            results = qs_to_result(faces, limit=max_results_per_group)
            results_by_bucket[(t, t + increment)] = results
    
    if len(results_by_bucket) == 0:
        raise Exception('No results to show')

    agg_results = [(
        'threshold=({}, {})'.format(k[0], k[1]),
        results_by_bucket[k]
    ) for k in sorted(results_by_bucket.keys())]

    return group_multiple_results(agg_results)

