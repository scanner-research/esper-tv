from esper.prelude import par_for, unzip, pcache
from query.models import Video, Face, Frame
from esper.scannerutil import ScannerWrapper, ScannerSQLTable
from scannertools import clothing_detection 
from django.db.models import Count, OuterRef, Subquery
from scannerpy import register_python_op, Database, DeviceType
from esper.kube import cluster_config, worker_config, make_cluster
import json
from scannerpy.stdlib import writers

def frames_for_video(video):
    return [f['number'] for f in
            Frame.objects.filter(video=video, shot_boundary=False).annotate(
                c=Subquery(Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')))
            .filter(c__gte=1)
            .values('number').order_by('number')]


@register_python_op(name='BboxesFromJson')
def bboxes_from_json(config, bboxes: bytes) -> bytes:
    dilate = config.args['dilate'] if 'dilate' in config.args else 1.0
    bboxes = json.loads(bboxes.decode('utf-8'))
    return writers.bboxes([
        config.protobufs.BoundingBox(
            x1=bb['bbox_x1']*(2.-dilate),
            x2=bb['bbox_x2']*dilate,
            y1=bb['bbox_y1']*(2.-dilate),
            y2=bb['bbox_y2']*dilate)
        for bb in bboxes
    ], config.protobufs)


class ClothingDetectionPipeline(clothing_detection.ClothingDetectionPipeline):
    def build_pipeline(self, adjust_bboxes=True):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['bboxes'].op)
        return {
            'clothing':
            getattr(self._db.ops, 'DetectClothing{}'.format('GPU' if self._device == DeviceType.GPU else 'CPU'))(
                frame=self._sources['frame_sampled'].op,
                bboxes=bboxes,
                model_path=self._model_path,
                model_def_path=self._model_def_path,
                model_key='best_model',
                adjust_bboxes=adjust_bboxes,
                device=self._device)
        }

detect_clothing = ClothingDetectionPipeline.make_runner()

videos = list(Video.objects.all().order_by('id'))

cfg = cluster_config(
    num_workers=2, worker=worker_config('n1-standard-16', gpu=2),
    pipelines=[clothing_detection.ClothingDetectionPipeline])

with make_cluster(cfg, sql_pool=2, no_delete=True) as db_wrapper:
# if True:
#     db_wrapper = ScannerWrapper(Database(enable_watchdog=False))

    db = db_wrapper.db

    frames = pcache.get('clothing_frames', lambda: par_for(frames_for_video, videos, workers=8))
    videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
    videos = list(videos)
    frames = list(frames)

    videos = videos[:5]
    frames = frames[:5]
    
    detect_clothing(
        db,
        videos=[v.for_scannertools() for v in videos],
        frames=frames,
        bboxes=[ScannerSQLTable(Face, v, num_elements=len(f),
                                filter='query_frame.shot_boundary = false')
                for v, f in zip(videos, frames)],
        run_opts={
            'io_packet_size': 500,
            'work_packet_size': 20,
            'checkpoint_frequency': 1000
        },
        device=DeviceType.GPU,
        cache=False)


