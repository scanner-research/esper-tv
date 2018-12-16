from esper.prelude import Timer, unzip, par_for, pcache, batch
from query.models import Video, Frame, Face
from scannertools import kube, face_embedding
from esper.kube import make_cluster, cluster_config, worker_config
from esper.scannerutil import ScannerWrapper, ScannerSQLPipeline, ScannerSQLTable
from esper.scanner_bench import bench, ScannerJobConfig
import scannerpy
import json
import pickle
from tqdm import tqdm
from django.db.models import Count, OuterRef, Subquery
from scannerpy import DeviceType
import json
from scannerpy.stdlib import writers
from scannerpy import register_python_op
import os

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


class FaceEmbeddingPipeline(face_embedding.FaceEmbeddingPipeline):
    additional_sources = ['faces']

    def build_pipeline(self):
        bboxes = self._db.ops.BboxesFromJson(bboxes=self._sources['faces'].op, dilate=1.05)
        return {
            'embeddings':
            getattr(self._db.ops, 'EmbedFaces{}'.format('GPU' if self._db.has_gpu() else 'CPU'))(
                frame=self._sources['frame_sampled'].op,
                bboxes=bboxes,
                model_dir=self._model_dir,
                device=DeviceType.GPU if self._db.has_gpu() else DeviceType.CPU)
        }


embed_faces = FaceEmbeddingPipeline.make_runner()

def frames_for_video(video):
    return [f['number'] for f in
            Frame.objects.filter(video=video).annotate(
                c=Subquery(Face.objects.filter(frame=OuterRef('pk')).values('frame').annotate(c=Count('*')).values('c')))
            .filter(c__gte=1)
            .values('number').order_by('number')]

if False:
    with Timer('benchmark'):
        videos = videos[:30]
        def run_pipeline(db, videos, frames, **kwargs):
            return embed_faces(
                db,
                videos=[v.for_scannertools() for v in videos],
                frames=frames,
                faces=[ScannerSQLTable(Face, v) #num_elements=len(f))
                       for v, f in zip(videos, frames)],
                cache=False,
                **kwargs)

        cfg = cluster_config(
            num_workers=5, worker=worker_config('n1-standard-32'), pipelines=[face_embedding.FaceEmbeddingPipeline])
        configs = [(cfg, [
            ScannerJobConfig(io_packet_size=500, work_packet_size=20, pipelines_per_worker=4),
            ScannerJobConfig(io_packet_size=1000, work_packet_size=20, pipelines_per_worker=4),
            ScannerJobConfig(io_packet_size=1000, work_packet_size=80, pipelines_per_worker=4),
            ScannerJobConfig(io_packet_size=1000, work_packet_size=20, pipelines_per_worker=8),
        ])]
        bench('embedding', {'videos': videos, 'frames': [frames_for_video(v) for v in videos]},
              run_pipeline, configs, no_delete=True, force=True)

    exit()

# Export packed embeddings and IDs into single files
if False:
    def get_ids(video):
        return [f['id'] for f in Face.objects.filter(frame__video=video).order_by('frame__number', 'id').values('id')]

    all_ids = par_for(get_ids, videos, workers=4)

    import struct
    with open('/app/data/embs/sevenyears_ids.bin', 'wb') as f:
        for ids in tqdm(all_ids):
            f.write(b''.join([struct.pack('=Q', i) for i in ids]))

    with open('/app/data/embs/sevenyears_embs.bin', 'wb') as f:
        for i in tqdm(list(range(len(videos)))):
            f.write(open('/app/data/embs/{:07d}.bin'.format(i), 'rb').read())
            f.flush()

if __name__ == "__main__":
    videos = list(Video.objects.filter(threeyears_dataset=False).order_by('id'))

    videos = videos
    cfg = cluster_config(
        num_workers=50, worker=worker_config('n1-standard-32'),
        pipelines=[face_embedding.FaceEmbeddingPipeline])

    # with make_cluster(cfg, sql_pool=4, no_delete=True) as db_wrapper:
    if True:
        db_wrapper = ScannerWrapper.create()

        db = db_wrapper.db
        def load_frames():
            return par_for(frames_for_video, videos, workers=8)
        frames = pcache.get('frames', load_frames)
        videos, frames = unzip([(v, f) for (v, f) in zip(videos, frames) if len(f) > 0])
        videos = list(videos)
        frames = list(frames)
        embs = embed_faces(
            db,
            videos=[v.for_scannertools() for v in videos],
            frames=frames,
            faces=[ScannerSQLTable(Face, v, num_elements=len(f))
                   for v, f in zip(videos, frames)],
            run_opts={
                'io_packet_size': 500,
                'work_packet_size': 20,
                'pipeline_instances_per_node': 4
            })


        def load_embs(i):
            path = '/app/data/embs/{:07d}.bin'.format(i)
            if os.path.isfile(path):
                return

            print(i)
            flat_emb = [emb.tobytes() for frame_embs in embs[i].load() for emb in frame_embs]
            with open(path, 'wb') as f:
                f.write(b''.join(flat_emb))

        print('embs', len(embs))
        for i in tqdm(range(len(embs))):
            load_embs(i)

        # for l in tqdm(list(batch(list(range(len(embs))), 100))):
        #     par_for(load_embs, l, workers=8, progress=False)
