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

@query("People sitting")
def people_sitting():
    def is_sitting(kp):
        def ang(v):
            return math.atan2(v[1], v[0]) / math.pi * 180
        def is_angled(v):
            v /= np.linalg.norm(v)
            v[1] = -v[1]  # correct for image coordinates
            a = ang(v)
            return a > 0 or a < -140
        return is_angled(kp[Pose.LKnee] - kp[Pose.LHip]) or is_angled(kp[Pose.RKnee] - kp[Pose.RHip])
        
    frames_qs = Frame.objects.filter(video__channel='CNN') \
        .annotate(
            pose_count=Subquery(
                Pose.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')), 
            woman_count=Subquery(
                Face.objects.filter(frame=OuterRef('pk'), gender__name='female').values('frame').annotate(c=Count('*')).values('c'), 
                output_field=models.IntegerField())) \
        .filter(pose_count__gt=0, pose_count__lt=6, woman_count__gt=0).order_by('id').select_related('video')
        
    frames = []        
    for frame in frames_qs[:100000:10]:
        filtered = filter_poses('pose', is_sitting, [Pose.LAnkle, Pose.LKnee, Pose.RAnkle, Pose.RKnee, Pose.RHip, Pose.LHip], poses=Pose.objects.filter(frame=frame))
        
        if len(filtered) > 0:
            frames.append((frame, filtered))

    return simple_result([{
        'video': frame.video.id,
        'start_frame': frame.id,
        'objects': [pose_to_dict(p) for p in poses]
    } for (frame, poses) in frames], 'Frame')

@query("Obama pictures")
def obama_pictures():
    id = 3938394
    FaceFeatures.compute_distances(id)
    sq = Face.objects.filter(track=OuterRef('pk'), labeler__name='mtcnn', facefeatures__distto__lte=1.0).values('track').annotate(c=Count('*'))
    out_tracks = []

    def close(x, y):
        return abs(x - y) < 0.02

    tracks = list(FaceTrack.objects.annotate(duration=Track.duration(), c=Subquery(sq.values('c'), models.IntegerField())).filter(duration__gt=0, c__gt=0))
    faces = list(Face.objects.filter(track__in=tracks).select_related('frame'))
    face_tracks = {t.id: (t, []) for t in tracks}
    for f in faces:
        face_tracks[f.track_id][1].append(f)

    for track, faces in face_tracks.values():
        faces.sort(lambda a, b: a.frame.number - b.frame.number)
        valid = True
        for i in range(len(faces)-1):
            if not (close(faces[i].bbox_x1, faces[i+1].bbox_x1) and
                close(faces[i].bbox_y1, faces[i+1].bbox_y1) and
                close(faces[i].bbox_x2, faces[i+1].bbox_x2) and
                close(faces[i].bbox_y2, faces[i+1].bbox_y2)):
                valid = False
                break
        if valid:
            out_tracks.append((track, faces[0]))

    return simple_result([{
        'video': t.video_id,
        'start_frame': Frame.objects.get(video=t.video, number=t.min_frame).id,
        'end_frame': Frame.objects.get(video=t.video, number=t.max_frame).id,
        'objects': [bbox_to_dict(f)]
    } for (t, f) in out_tracks], 'FaceTrack')
