from esper.prelude import *
from .queries import query

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


@query("Panels (SQL)")
def panels_():
    from esper.queries.panels_sql import panels
    return simple_result([{
        'video': frame.video.id,
        'min_frame': frame.number,
        'objects': [bbox_to_dict(f) for f in faces]
    } for (frame, faces) in panels()], 'Frame')

