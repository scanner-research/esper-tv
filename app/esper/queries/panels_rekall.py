from esper.prelude import *
from .queries import query

@query('Panels (rekall)')
def panels_rekall():
    from query.models import LabeledCommercial, Face
    from rekall.video_interval_collection import VideoIntervalCollection
    from rekall.parsers import in_array, bbox_payload_parser
    from rekall.merge_ops import payload_plus
    from rekall.bbox_predicates import height_at_least, same_value, left_of
    from rekall.spatial_predicates import scene_graph
    from rekall.payload_predicates import payload_satisfies
    from esper.rekall import intrvllists_to_result_bbox

    MIN_FACE_HEIGHT = 0.3
    EPSILON = 0.05

    # Get list of sandbox video IDs
    sandbox_videos = [
        row.video_id
        for row in LabeledCommercial.objects.distinct('video_id')
    ]

    faces_qs = Face.objects.filter(shot__video_id__in=sandbox_videos).annotate(
        video_id=F("shot__video_id"),
        min_frame=F("shot__min_frame"),
        max_frame=F("shot__max_frame")
    )

    # One interval for each face
    faces = VideoIntervalCollection.from_django_qs(
            faces_qs,
            with_payload=in_array(
                bbox_payload_parser(
                    VideoIntervalCollection.django_accessor)))

    # Merge shots
    faces = faces.coalesce(payload_merge_op=payload_plus)

    # Define a scene graph for things that look like panels
    three_faces_scene_graph = {
        'nodes': [
            { 'name': 'face1', 'predicates': [ height_at_least(MIN_FACE_HEIGHT) ] },
            { 'name': 'face2', 'predicates': [ height_at_least(MIN_FACE_HEIGHT) ] },
            { 'name': 'face3', 'predicates': [ height_at_least(MIN_FACE_HEIGHT) ] }
        ],
        'edges': [
            { 'start': 'face1', 'end': 'face2',
                'predicates': [ same_value('y1', epsilon=EPSILON), left_of() ] }, 
            { 'start': 'face2', 'end': 'face3',
                'predicates': [ same_value('y1', epsilon=EPSILON), left_of() ] }, 
        ]
    }

    panels = faces.filter(payload_satisfies(
        scene_graph(three_faces_scene_graph, exact=True)
    ))

    return intrvllists_to_result_bbox(panels.get_allintervals())

