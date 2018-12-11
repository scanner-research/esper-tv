from esper.prelude import Timer, unzip, par_for
from query.models import Video, Frame, Face, FaceGender, Labeler, Gender
from scannertools import kube, gender_detection
from esper.kube import make_cluster, cluster_config, worker_config
from esper.scannerutil import ScannerWrapper, ScannerSQLPipeline, ScannerSQLTable
from esper.scanner_bench import bench, ScannerJobConfig
import scannerpy
import json
import pickle
from tqdm import tqdm
from scannerpy.stdlib import writers
from django.db.models import Count, OuterRef, Subquery

labeler_id = Labeler.objects.get(name='rudecarnie').id
gender_ids = {g.name: g.id for g in Gender.objects.all()}

@scannerpy.register_python_op(name='GendersToJson')
def genders_to_json(config, genders: bytes, faces: bytes) -> bytes:
    genders = pickle.loads(genders)
    faces = json.loads(faces.decode('utf-8'))
    return json.dumps([
        {'face_id': face['id'],
         'gender_id': gender_ids[gender_str],
         'probability': score.item(),
         'labeler_id': labeler_id}
        for ((gender_str, score), face) in zip(genders, faces)
    ])

class GenderDetectionPipeline(ScannerSQLPipeline, gender_detection.GenderDetectionPipeline):
    db_class = FaceGender
    json_kernel = 'GendersToJson'
    additional_sources = ['faces']

    def build_pipeline(self):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['faces'].op)
        return {
            'genders': self._db.ops.DetectGender(
                frame=self._sources['frame_sampled'].op,
                bboxes=bboxes,
                model_dir=self._model_dir),
            'faces': self._sources['faces'].op
        }

detect_genders = GenderDetectionPipeline.make_runner()

videos = Video.objects.filter(threeyears_dataset=False).order_by('id')

def frames_for_video(video):
    return [f['number'] for f in
            Frame.objects.filter(video=video).annotate(
                c=Subquery(Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')))
            .filter(c__gte=1)
            .values('number').order_by('number')]

if False:
    with Timer('benchmark'):
        videos = videos[:50]
        def run_pipeline(db, videos, frames, **kwargs):
            return detect_genders(
                db,
                db_videos=videos,
                videos=[v.for_scannertools() for v in videos],
                frames=frames,
                faces=[ScannerSQLTable(Face, v) #num_elements=len(f))
                       for v, f in zip(videos, frames)],
                cache=False,
                **kwargs)

        cfg = cluster_config(
            num_workers=5, worker=worker_config('n1-standard-32'), pipelines=[GenderDetectionPipeline])
        configs = [(cfg, [
            ScannerJobConfig(io_packet_size=1000, work_packet_size=20, pipelines_per_worker=4),
            ScannerJobConfig(io_packet_size=1000, work_packet_size=20, pipelines_per_worker=8),
            ScannerJobConfig(io_packet_size=1000, work_packet_size=20, pipelines_per_worker=16)
        ])]
        bench('gender', {'videos': videos, 'frames': [frames_for_video(v) for v in videos]},
              run_pipeline, configs, no_delete=True, force=True)


    exit()

videos = videos
cfg = cluster_config(
    num_workers=50, worker=worker_config('n1-standard-32'),
    pipelines=[gender_detection.GenderDetectionPipeline])

with make_cluster(cfg, sql_pool=4, no_delete=True) as db_wrapper:
    db = db_wrapper.db

# if True:
#     db_wrapper = ScannerWrapper.create()

    frames = par_for(frames_for_video, videos, workers=8)
    videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
    videos = list(videos)
    frames = list(frames)
    detect_genders(
        db,
        videos=[v.for_scannertools() for v in videos],
        db_videos=videos,
        frames=frames,
        faces=[ScannerSQLTable(Face, v, num_elements=len(f))
               for v, f in zip(videos, frames)],
        run_opts={
            'io_packet_size': 500,
            'work_packet_size': 20,
            'pipeline_instances_per_node': 4
        })
