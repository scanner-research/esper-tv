from esper.prelude import Timer, model_defaults, Notifier
from query.models import Video, Frame, Face, Labeler
from scannertools import kube, face_detection
from esper.kube import make_cluster, cluster_config, worker_config
from esper.scanner_bench import ScannerJobConfig, bench
from esper.scannerutil import ScannerWrapper, ScannerSQLPipeline, ScannerSQLTable
import scannerpy
from scannerpy.stdlib import readers
import json
from django.db.models.fields import NOT_PROVIDED
from tqdm import tqdm

labeler_id = Labeler.objects.get(name='mtcnn').id
face_defaults = model_defaults(Face)

@scannerpy.register_python_op(name='FacesToJson')
def faces_to_json(config, bboxes: bytes, frame_ids: bytes) -> bytes:
    faces = readers.bboxes(bboxes, config.protobufs)
    frame_id = json.loads(frame_ids.decode('utf-8'))[0]['id']
    return json.dumps([
        {'frame_id': frame_id,
         'bbox_x1': f.x1,
         'bbox_x2': f.x2,
         'bbox_y1': f.y1,
         'bbox_y2': f.y2,
         'probability': f.score,
         'labeler_id': labeler_id,
         **face_defaults}
        for f in faces
    ])

class FaceDetectionPipeline(ScannerSQLPipeline, face_detection.FaceDetectionPipeline):
    db_class = Face
    json_kernel = 'FacesToJson'
    additional_sources = ['frame_ids']

    def build_pipeline(self):
        output_ops = super(FaceDetectionPipeline, self).build_pipeline()
        output_ops['frame_ids'] = self._sources['frame_ids'].op
        return output_ops

detect_faces = FaceDetectionPipeline.make_runner()

videos = list(Video.objects.filter(threeyears_dataset=False).order_by('id'))

if False:
    with Timer('benchmark'):
        videos = videos[:50]
        def run_pipeline(db, videos, frames, **kwargs):
            return face_detection.detect_faces(db, videos=[v.for_scannertools() for v in videos], frames=frames, cache=False, **kwargs)

        cfg = cluster_config(num_workers=5, worker=worker_config('n1-standard-32'))
        configs = [(cfg, [ScannerJobConfig(io_packet_size=1000, work_packet_size=20, batch=1)])]
        bench('face', {'videos': videos, 'frames': [[f['number'] for f in Frame.objects.filter(video=v).values('number').order_by('number')] for v in videos]},
              run_pipeline, configs, no_delete=True, force=True)

videos = videos

with Timer('run'):
    cfg = cluster_config(
        num_workers=80,
        worker=worker_config('n1-standard-32'),
        workers_per_node=8,
        num_load_workers=1,
        num_save_workers=1)
    with make_cluster(cfg, sql_pool=4, no_delete=True) as db_wrapper:

    # if True:
    #     db_wrapper = ScannerWrapper.create(enable_watchdog=False)

        db = db_wrapper.db

        print('Getting frames')
        frames = [[f['number'] for f in Frame.objects.filter(video=v).values('number').order_by('number')]
                  for v in tqdm(videos)]

        print('Starting detection')
        detect_faces(
            db,
            videos=[v.for_scannertools() for v in videos],
            db_videos=videos,
            frames=frames,
            frame_ids=[ScannerSQLTable(Frame, v, num_elements=len(f))
                       for v, f in zip(videos, frames)],
            run_opts={
                'io_packet_size': 1000,
                'work_packet_size': 20
            })
