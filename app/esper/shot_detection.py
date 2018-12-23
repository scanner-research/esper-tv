from scannertools import shot_detection, kube
from esper.scannerutil import ScannerSQLTable, ScannerSQLPipeline
from esper.prelude import  Timer, Notifier, pcache, unzip
from query.models import Video, Frame
from esper.kube import cluster_config, worker_config, make_cluster
from esper.scanner_bench import ScannerJobConfig, bench
import attr
import scannerpy
import json
import pickle


# db = scannerpy.Database()
# print('making trace')
# db.profiler(665).write_trace('shots.tar.gz')
# print('done')
# exit()


with Timer('Loading videos'):
    videos = list(Video.objects.filter(threeyears_dataset=False).order_by('id'))
    #videos = videos[:1]
    print('Found {} videos'.format(len(videos)))

def run_pipeline(db, videos, **kwargs):
    return shot_detection.compute_histograms(
        db,
        videos=[v.for_scannertools() for v in videos],
        **kwargs)

if False:
    with Timer('Benchmarking histograms'):
        # configs = [
        #     (attr.evolve(cluster_config, worker=attr.evolve(
        #         worker_config, type=kube.MachineTypeName(name='n1-standard-4'))),
        #      [ScannerJobConfig(
        #          io_packet_size=1000,
        #          work_packet_size=20,
        #          batch=20)]),
        #     (attr.evolve(cluster_config, worker=attr.evolve(
        #         worker_config, type=kube.MachineTypeName(name='n1-standard-8'))),
        #      [ScannerJobConfig(
        #          io_packet_size=1000,
        #          work_packet_size=20,
        #          batch=20)]),
        #     (attr.evolve(cluster_config, worker=attr.evolve(
        #         worker_config, type=kube.MachineTypeName(name='n1-standard-32'))),
        #      [ScannerJobConfig(
        #          io_packet_size=10000,
        #          work_packet_size=400,
        #          batch=400)]),
        # ]

        # configs = [
        #     (cluster_config,
        #      [ScannerJobConfig(io_packet_size=30000, work_packet_size=400, batch=400),
        #       ScannerJobConfig(io_packet_size=20000, work_packet_size=400, batch=400),
        #       ScannerJobConfig(io_packet_size=10000, work_packet_size=400, batch=400),
        #       ScannerJobConfig(io_packet_size=10000, work_packet_size=400, batch=40),
        #       ScannerJobConfig(io_packet_size=10000, work_packet_size=1000, batch=1000)])
        # ]

        configs = [(cluster_config, [ScannerJobConfig(io_packet_size=10000, work_packet_size=400, batch=400)])]

        bench('hist', videos, run_pipeline, configs, sample_size=50, no_delete=True, force=True)

import sys
import os
@scannerpy.register_python_op()
class BoundariesToJson(scannerpy.Kernel):
    def new_stream(self, args):
        self._video_id = args['video_id']
        print(os.getpid(), 'NEW STREAM {}'.format(self._video_id))
        sys.stdout.flush()

    def execute(self, boundaries: bytes) -> bytes:
        if boundaries == b'\0':
            return json.dumps([])
        else:
            print(os.getpid(), 'EXECUTE', self._video_id)
            sys.stdout.flush()
            return json.dumps([{'video_id': self._video_id, 'number': n, 'shot_boundary': True} for n in pickle.loads(boundaries)])

class ShotBoundaryPipeline(ScannerSQLPipeline, shot_detection.ShotBoundaryPipeline):
    json_kernel = 'BoundariesToJson'
    db_class = Frame
    custom_opts = ['video_ids']

    def committed(self, *args):
        return False

    def _build_jobs(self, cache):
        jobs = super(ShotBoundaryPipeline, self)._build_jobs(cache)
        for (job, video_id) in zip(jobs, self._custom_opts['video_ids']):
            job._op_args[self._json_kernel_instance] = {'video_id': video_id}
        return jobs


compute_shot_boundaries = ShotBoundaryPipeline.make_runner()

# with Timer('Histogram'):
#     cfg = cluster_config(
#         num_workers=300,
#         worker=worker_config('n1-standard-16'))
#     with make_cluster(cfg, no_delete=True) as db_wrapper:

# videos = videos
#videos = list(Video.objects.filter(id__gte=91250, id__lte=91350))
# videos = [Video.objects.get(id=63970)]
videos = videos

with Timer('Shot boundaries'):
    cfg = cluster_config(
        num_workers=60,
        worker=worker_config('n1-highmem-16'),
        workers_per_node=2,
        num_load_workers=1,
        num_save_workers=2)
    with make_cluster(cfg, no_delete=True) as db_wrapper:

    # from esper.scannerutil import ScannerWrapper
    # if True:
    #     db_wrapper = ScannerWrapper.create()

        db = db_wrapper.db

        job_config = ScannerJobConfig(io_packet_size=10000, work_packet_size=400, batch=400)
        hists = run_pipeline(db, videos, batch=job_config.batch, run_opts={
            'io_packet_size': job_config.io_packet_size,
            'work_packet_size': job_config.work_packet_size,
        })
        print('hists', len(hists))

        hists, videos = unzip([(h, v) for (h, v) in zip(hists, videos) if v.num_frames < 800000])
        boundaries = compute_shot_boundaries(
            db,
            videos=[v.for_scannertools() for v in videos],
            db_videos=videos,
            video_ids=[v.id for v in videos],
            histograms=hists)
        # print(len([v for (v, b) in zip(videos, boundaries) if b is None]))



Notifier().notify('done')
