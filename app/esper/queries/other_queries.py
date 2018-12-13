from esper.prelude import *
from .queries import query

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


@query("Frames with two women")
def frames_with_two_women():
    face_qs = FaceGender.objects.filter(gender__name='F', face__shot__in_commercial=False)
    frames = list(Frame.objects.annotate(c=qs_child_count(face_qs, 'face__frame')) \
        .filter(c=2)[:1000:10])

    return qs_to_result(face_qs.filter(face__frame__in=frames))



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
    from esper.embed_google_images import name_to_embedding
    from esper.face_embeddings import knn
    emb = name_to_embedding('Wolf Blitzer')
    face_ids = [x for x, _ in knn(targets=[emb], max_threshold=0.4)][::10]
    return qs_to_result(
        Face.objects.filter(id__in=face_ids), custom_order_by_id=face_ids, limit=len(face_ids))


@query('Groups of faces by distance threshold')
def groups_of_faces_by_distance_threshold():
    from esper.embed_google_images import name_to_embedding
    from esper.face_embeddings import knn
    emb = name_to_embedding('Wolf Blitzer')

    increment = 0.05
    max_thresh = 1.0
    max_results_per_group = 50
    exclude_labeled = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    face_sims = knn(targets=[emb], max_threshold=max_thresh)

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

    from esper.face_embeddings import knn
    
    increment = 0.05
    max_thresh = 1.0
    max_results_per_group = 50
    exclude_labeled = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    face_sims = knn(ids=target_face_ids, max_threshold=max_thresh)

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


@query('Face search with exclusions')
def face_search_with_exclusion():
    from esper.embed_google_images import name_to_embedding
    from esper.face_embeddings import knn
    
    def exclude_faces(face_ids, exclude_ids, exclude_thresh):
        excluded_face_ids = set()
        for exclude_id in exclude_ids:
            excluded_face_ids.update([x for x, _ in knn(ids=[exclude_id], max_threshold=exclude_thresh)])
        face_ids = set(face_ids)
        return face_ids - excluded_face_ids, face_ids & excluded_face_ids

    # Some params
    exclude_labeled = False
    show_excluded = False

    face_qs = UnlabeledFace.objects if exclude_labeled else Face.objects

    name = 'Wolf Blitzer'

    emb = name_to_embedding(name)
    face_ids = [x for x, _ in knn(features=emb, max_threshold=0.6)]

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
    from esper.face_embeddings import kmeans
    
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
    for (i, c) in kmeans(other_face_ids, k=n_clusters):
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
