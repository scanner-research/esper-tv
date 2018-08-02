from scannertools import object_detection
from esper.prelude import ScannerWrapper, Timer, ScannerSQLTable
from query.models import Object, Video, Frame, ScannerJob
import scannerpy
from scannerpy.stdlib import readers
import json


# 1. Define pipeline + auxiliary kernels

@scannerpy.register_python_op(name='BboxToJson')
def bbox_to_json(config, bboxes: bytes, frame_id: bytes) -> bytes:
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

class ObjectDetectionPipeline(object_detection.ObjectDetectionPipeline):
    additional_sources = ['frame_ids']

    def build_sink(self, db_videos):
        jsonified = self._db.ops.BboxToJson(
            bboxes=self._output_ops['bboxes'], frame_id=self._sources['frame_ids'].op)
        return ScannerWrapper(self._db).sql_sink(
            cls=Object, input=jsonified, videos=db_videos, suffix='objdet', insert=True)

    def parse_output(self):
        pass

detect_objects = ObjectDetectionPipeline.make_runner()


# 2. Gather inputs

db_wrapper = ScannerWrapper.create()
db = db_wrapper.db

videos = db_wrapper.filter_videos(Video.objects.all(), ObjectDetectionPipeline)[:1]
print('Processing {} videos'.format(len(videos)))

frames = [
    [f['number'] for f in
     Frame.objects.filter(video=v).values('number').order_by('number')]
    for v in videos
]


# 3. Run pipeline

detect_objects(
    db,
    videos=[v.for_scannertools() for v in videos],
    frames=frames,
    frame_ids=[ScannerSQLTable(Frame, v) for v in videos],
    db_videos=videos)

print('Done!')
