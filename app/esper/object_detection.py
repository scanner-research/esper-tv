from scannertools.object_detection import ObjectDetectionPipeline
from scannertools import BoundOp
from esper.prelude import ScannerWrapper, Timer
from query.models import Object, Video, Frame, ScannerJob
import scannerpy
from scannerpy.stdlib import readers
import json

with Timer('Loading scanner'):
    db_wrapper = ScannerWrapper(multiworker=True)
    db = db_wrapper.db

pipeline = ObjectDetectionPipeline(db)

videos = db_wrapper.filter_videos(Video.objects.all()[1:100], pipeline)
print('Processing {} videos'.format(len(videos)))

def source_builder():
    frame = db.sources.FrameColumn()
    frame_sampled = db.streams.Gather(frame)
    frame_ids = db.sources.SQL(
        config=db_wrapper.sql_config(),
        query=db.protobufs.SQLQuery(
            fields='query_frame.id as id, query_frame.number as number',
            id='query_frame.id',
            group='number',
            table='query_frame INNER JOIN query_video ON query_frame.video_id = query_video.id',
        ))

    with Timer('Loading frames'):
        frames = [
            [f['number'] for f in
             Frame.objects.filter(video=v).values('number').order_by('number')]
            for v in videos
        ]

    return {
        'frame': BoundOp(
            op=frame, args=[db.table(v.path).column('frame') for v in videos]),
        'frame_sampled': BoundOp(op=frame_sampled, args=frames),
        'frame_ids': BoundOp(op=frame_ids, args=[{'filter': 'query_video.id = {}'.format(v.id)} for v in videos])
    }

@scannerpy.register_python_op(name='ToJson')
def to_json(config, bboxes: bytes, frame_id: bytes) -> bytes:
    bboxes = readers.bboxes(bboxes, config.protobufs)
    frame_id = json.loads(frame_id.decode('utf-8'))[0]['id']
    return json.dumps([{
        'bbox_x1': bb.x1,
        'bbox_x2': bb.x2,
        'bbox_y1': bb.y1,
        'bbox_y2': bb.y2,
        'probability': bb.score,
        'label': bb.label,
        'frame_id': frame_id
    } for bb in bboxes])

def sink_builder(inputs, output_ops):
    jsonified = db.ops.ToJson(bboxes=output_ops['bboxes'], frame_id=inputs['frame_ids']['op'])
    sql_sink = db_wrapper.sql_sink(Object, insert=True)
    return BoundOp(op=sql_sink(jsonified), args=[{'job_name': v.path + '_objdet'} for v in videos])

pipeline.execute(
    source_builder=source_builder,
    sink_builder=sink_builder)
