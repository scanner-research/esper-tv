from query.datasets.prelude import *
from query.datasets.queries import *
from functools import reduce


@query("Non-handlabeled random faces/genders")
def not_handlabeled():
    import random
    l = Labeler.objects.get(name='rudecarnie')
    t = Tag.objects.get(name='handlabeled-face:labeled')
    i = random.randint(0, FaceGender.objects.aggregate(Max('id'))['id__max'])
    return qs_to_result(
        FaceGender.objects.filter(labeler=l, id__gte=i).exclude(
            Q(face__person__frame__tags=t)
            | Q(face__shot__in_commercial=True)
            | Q(face__shot__video__commercials_labeled=False)
            | Q(face__shot__isnull=True)),
        stride=1000)


@query("Handlabeled faces/genders")
def handlabeled():
    return qs_to_result(
        FaceGender.objects.filter(labeler__name='handlabeled-gender').annotate(
            identity=F('face__faceidentity__identity')))


@query("Donald Trump")
def donald_trump():
    return qs_to_result(FaceIdentity.objects.filter(identity__name='donald trump'))


@query("Commercials")
def commercials():
    return qs_to_result(Commercial.objects.filter(labeler__name='haotian-commercials'))


@query("Positive segments")
def positive_segments():
    return qs_to_result(
        Segment.objects.filter(labeler__name='haotian-segments',
                               polarity__isnull=False).order_by('-polarity'))


@query("Negative segments")
def negative_segments():
    return qs_to_result(
        Segment.objects.filter(labeler__name='haotian-segments',
                               polarity__isnull=False).order_by('polarity'))


@query("Segments about Donald Trump")
def segments_about_donald_trump():
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='person',
            things__name='donald trump'))

@query("Segments about North Korea")
def segments_about_donald_trump():
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='location',
            things__name='north korea'))


@query("Segments about immigration")
def segments_about_immigration():
    return qs_to_result(
        Segment.objects.filter(
            labeler__name='haotian-segments',
            things__type__name='topic',
            things__name='immigration'))

@query("Sunday morning news shows")
def sunday_morning_news_shows():
    return qs_to_result(
        Video.objects.filter(
            time__week_day=1,
            time__hour=6))

@query("Fox News videos")
def fox_news_videos():
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
        Face.objects.filter(person__frame__video__show='CNN Newsroom With Poppy Harlow'), stride=24)


#@query("Female faces on Poppy Harlow")
def female_faces_on_poppy_harlow():
    return qs_to_result(
        Face.objects.filter(
            person__frame__video__show__name='CNN Newsroom With Poppy Harlow',
            facegender__gender__name='F'),
        stride=24)


#@query("Talking heads on Poppy Harlow")
def talking_heads_on_poppy_harlow():
    return qs_to_result(
        Face.objects.annotate(height=F('bbox_y2') - F('bbox_y1')).filter(
            height__gte=0.3,
            person__frame__video__show='CNN Newsroom With Poppy Harlow',
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
                        person__frame=frame,
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
        .filter(person__face__labeler__name='handlabeled') \
        .select_related('video') \
        .order_by('id')[:50000:5]:
        faces = list(Face.objects.filter(person__frame=frame).select_related('labeler'))
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
            Pose.objects.filter(person__frame=OuterRef('pk')).values('person__frame') \
            .annotate(c=Count('*')).values('c'), models.IntegerField())) \
        .filter(c__gt=0) \
        .select_related('video') \
        .order_by('id')
    for frame in frames[:50000:5]:
        faces = list(Face.objects.filter(person__frame=frame))
        poses = list(Pose.objects.filter(person__frame=frame))
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
                Pose.objects.filter(person__frame=OuterRef('pk')).values('person__frame').annotate(c=Count('*')).values('c')),
            woman_count=Subquery(
                Face.objects.filter(person__frame=OuterRef('pk'), facegender__gender__name='female').values('person__frame').annotate(c=Count('*')).values('c'),
                models.IntegerField())) \
        .filter(pose_count__gt=0, pose_count__lt=6, woman_count__gt=0).order_by('id').select_related('video')

    frames = []
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses(
            'pose',
            is_sitting, [Pose.LAnkle, Pose.LKnee, Pose.RAnkle, Pose.RKnee, Pose.RHip, Pose.LHip],
            poses=Pose.objects.filter(person__frame=frame))

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
        person__tracks=OuterRef('pk'), labeler__name='mtcnn',
        facefeatures__distto__lte=1.0).values('person__tracks').annotate(c=Count('*'))
    out_tracks = []

    face_tracks = {}  #{t.id: (t, []) for t in tracks}
    for track in \
        PersonTrack.objects.filter(labeler__name='featuretrack') \
        .annotate(
            duration=Track.duration(),
            c=Subquery(sq.values('c'), models.IntegerField())) \
        .filter(duration__gt=0, c__gt=0):

        faces = list(
            Face.objects.filter(person__tracks=track,
                                labeler__name='mtcnn').select_related('person__frame'))
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
    frames = list(Frame.objects.annotate(c=qs_child_count(face_qs, 'face__person__frame')) \
        .filter(c=2)[:1000:10])

    return qs_to_result(face_qs.filter(face__person__frame__in=frames))

def panels():
    mtcnn = Labeler.objects.get(name='mtcnn')
    face_qs = Face.objects.annotate(height=BoundingBox.height_expr()).filter(
        height__gte=0.25, labeler=mtcnn, shot__in_commercial=False)
    frames = Frame.objects.annotate(c=Subquery(
        face_qs.filter(person__frame=OuterRef('pk')) \
        .values('person__frame') \
        .annotate(c=Count('*')) \
        .values('c'), models.IntegerField())) \
        .filter(c__gte=3, c__lte=3).order_by('id')

    output_frames = []
    for frame in frames[:10000:10]:
        faces = list(face_qs.filter(person__frame=frame))
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
    from query.datasets.tvnews.queries import panels
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
            Face.objects.filter(person__tracks=OuterRef('pk')) \
            .filter(labeler__name='tinyfaces', facefeatures__distto__isnull=False, facefeatures__distto__lte=1.0) \
            .values('person__tracks')
            .annotate(c=Count('*'))
            .values('c'), models.IntegerField()
            )) \
        .filter(c__gt=0))

    all_dists = []
    for track in tracks:
        poses = list(Pose.objects.filter(person__tracks=track).order_by('person__frame__number'))
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
        [bbox_to_dict(Face.objects.filter(person__frame__number=t.min_frame, person__tracks=t)[0])]
    } for t, score in all_dists], 'PersonTrack')


@query("Audio labels")
def audio_labels():
    return qs_to_result(Speaker.objects.all(), group=True, limit=10000)


@query("Non-handlabeled random audio")
def nonhandlabeled_random_audio():
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
    results = caption_search('DONALD TRUMP')
    videos = {v.id: v for v in Video.objects.all()}

    def convert_time(k, t):
        return int((t - 7) * videos[k].fps)

    flattened = [(k, t1, t2) for k, l in results.items() for t1, t2 in l]
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
            ).distinct('person__frame__video')
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

    results_by_bucket = {}
    for t in frange(min_thresh, max_thresh, increment):
        face_ids = [x for x, _ in filter(lambda z: z[1] >= t and z[1] < t + increment, face_sims)]
        if len(face_ids) != 0:
            faces = face_qs.filter(
                id__in=random.sample(face_ids, k=min(len(face_ids), max_results_per_group))
            ).distinct('person__frame__video')
            results = qs_to_result(faces, limit=max_results_per_group, custom_order_by_id=face_ids)
            results_by_bucket[(t, t + increment, len(face_ids))] = results

    if len(results_by_bucket) == 0:
        raise Exception('No results to show')

    agg_results = [('in range=({:0.2f}, {:0.2f}), count={}'.format(k[0], k[1], k[2]), results_by_bucket[k])
                   for k in sorted(results_by_bucket.keys())]

    return group_results(agg_results)


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
