from query.datasets.prelude import *
from query.datasets.queries import *


@query("Fox News videos")
def fox_news_videos():
    return qs_to_result(Frame.objects.filter(number=0, video__channel='FOXNEWS'))


@query("Talking heads face tracks")
def talking_heads_tracks():
    return qs_to_result(
        FaceTrack.objects.filter(id__in=Face.objects.annotate(
            height=F('bbox_y2') - F('bbox_y1')).filter(
                frame__video__id=791, labeler__name='mtcnn',
                height__gte=0.3).distinct('track').values('track')),
        segment=True)


@query("Faces on Poppy Harlow")
def faces_on_poppy_harlow():
    return qs_to_result(
        Face.objects.filter(frame__video__show='CNN Newsroom With Poppy Harlow'),
        group=True,
        stride=24)


@query("Female faces on Poppy Harlow")
def female_faces_on_poppy_harlow():
    returnqs_to_result(
        Face.objects.filter(
            frame__video__show='CNN Newsroom With Poppy Harlow', gender__name='fem ale'),
        group=True,
        stride=24)


@query("Talking heads on Poppy Harlow")
def talking_heads_on_poppy_harlow():
    return qs_to_result(
        Face.objects.annotate(height=F('bbox_y2') - F('bbox_y1')).filter(
            height__gte=0.3,
            frame__video__show='CNN Newsroom With Poppy Harlow',
            gender__name='female'),
        group=True,
        stride=24)


@query("Two female faces on Poppy Harlow")
def two_female_faces_on_poppy_harlow():
    r = []
    for video in Video.objects.filter(show='CNN Newsroom With Poppy Harlow'):
        for frame in Frame.objects.filter(video=video).annotate(
                n=F('number') % math.ceil(video.fps)).filter(n=0)[:1000:10]:
            faces = list(
                Face.objects.annotate(height=F('bbox_y2') - F('bbox_y1')).filter(
                    labeler__name='mtcnn', frame=frame, gender__name='female', height__gte=0.2))
            if len(faces) == 2:
                r.append({
                    'video': frame.video.id,
                    'start_frame': frame.id,
                    'objects': [bbox_to_dict(f) for f in faces]
                })
    return simple_result(r, 'Frame')


@query("Faces like Poppy Harlow")
def faces_like_poppy_harlow():
    id = 4457280
    FaceFeatures.dropTempFeatureModel()
    FaceFeatures.getTempFeatureModel([id])
    result = qs_to_result(Face.objects.all().order_by('facefeaturestemp__distto_{}'.format(id)))


@query("Faces unlike Poppy Harlow")
def faces_unlike_poppy_harlow():
    id = 4457280
    FaceFeatures.dropTempFeatureModel()
    FaceFeatures.getTempFeatureModel([id])
    result = qs_to_result(
        Face.objects.filter(**{'facefeaturestemp__distto_{}__gte'.format(id): 1.7}).order_by(
            'facefeaturestemp__distto_{}'.format(id)))


@query("Differing bounding boxes")
def differing_bounding_boxes():
    labeler_names = [l['labeler__name'] for l in Face.objects.values('labeler__name').distinct()]

    videos = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for frame in Frame.objects.filter(
            Q(video__show='Situation Room With Wolf Blitzer') | Q(
                video__show='Special Report With Bret Baier')).filter(
                    face__labeler__name='handlabeled').select_related('video')[:50000:5]:
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
    for video, frames in videos.iteritems():
        for frame, labelers in frames.iteritems():
            for labeler, faces in labelers.iteritems():
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
    for video, frames in list(mistakes.iteritems())[:100]:
        for frame, (faces, other_faces) in frames.iteritems():
            result.append({
                'video': video,
                'start_frame': frame,
                'objects': [bbox_to_dict(f) for f in faces + other_faces]
            })

    return {'result': result, 'count': len(result), 'type': 'Frame'}
