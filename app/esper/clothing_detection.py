from esper.prelude import par_for, unzip, pcache
from query.models import Video, Face, Frame
from esper.scannerutil import ScannerWrapper, ScannerSQLTable, bboxes_from_json
from scannertools import clothing_detection 
from django.db.models import Count, OuterRef, Subquery
from scannerpy import register_python_op

def frames_for_video(video):
    return [f['number'] for f in
            Frame.objects.filter(video=video, shot_boundary=False).annotate(
                c=Subquery(Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')))
            .filter(c__gte=1)
            .values('number').order_by('number')]

register_python_op(name='BboxesFromJson')(bboxes_from_json)

class ClothingDetectionPipeline(clothing_detection.ClothingDetectionPipeline):
    def build_pipeline(self, adjust_bboxes=True):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['bboxes'].op)
        return {
            'clothing':
            self._db.ops.DetectClothing(
                frame=self._sources['frame_sampled'].op,
                bboxes=bboxes,
                model_path=self._model_path,
                model_def_path=self._model_def_path,
                model_key='best_model',
                adjust_bboxes=adjust_bboxes)
        }

detect_clothing = ClothingDetectionPipeline.make_runner()

videos = list(Video.objects.all().order_by('id'))

if True:
    db_wrapper = ScannerWrapper.create()
    db = db_wrapper.db

    frames = pcache.get('clothing_frames', lambda: par_for(frames_for_video, videos, workers=8))
    videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
    videos = list(videos)
    frames = list(frames)

    ClothingDetectionPipeline(db).ingest([v.for_scannertools() for v in videos])
    exit()
    
    detect_clothing(
        db,
        videos=[v.for_scannertools() for v in videos],
        frames=frames,
        bboxes=[ScannerSQLTable(Face, v, num_elements=len(f),
                                filter='query_frame.shot_boundary = false')
                for v, f in zip(videos, frames)],
        run_opts={
            'pipeline_instances_per_node': 4,
            'io_packet_size': 500,
            'work_packet_size': 20,
            'checkpoint_frequency': 1000
        })


