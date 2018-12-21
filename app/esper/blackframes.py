from query.models import Video
from scannertools import shot_detection, Pipeline
from esper.scannerutil import ScannerWrapper
from scannerpy import register_python_op
from scannerpy.stdlib import readers
import struct
from typing import Sequence
from esper.kube import make_cluster, cluster_config, worker_config
from esper.prelude import pcache, par_for
import numpy as np
import os

@register_python_op(name='IsBlack', batch=10000)
def is_black(config, hists: Sequence[bytes]) -> Sequence[bytes]:
    output = []
    for hists_batch in hists:
        h = readers.histograms(hists_batch, config.protobufs)
        threshold = 0.99 * sum(h[0])
        is_black = h[0][0] > threshold and h[1][0] > threshold and h[2][0] > threshold
        output.append(struct.pack('B', 1 if is_black else 0))
    return output

class BlackFramesPipeline(Pipeline):
    job_suffix = 'blackframes'
    base_sources = ['videos', 'histograms']
    parser_fn = lambda _: lambda buf, _: struct.unpack('B', buf)

    def build_pipeline(self):
        return {
            'blackframes': self._db.ops.IsBlack(hists=self._sources['histograms'].op)
        }

compute_black_frames = BlackFramesPipeline.make_runner()

if __name__ == "__main__":
    videos = list(Video.objects.filter(threeyears_dataset=False).order_by('id'))

    cfg = cluster_config(
        num_workers=100,
        worker=worker_config('n1-standard-32'))
    # with make_cluster(cfg, no_start=True, no_delete=True) as db_wrapper:

    if True:
        db_wrapper = ScannerWrapper.create()

        db = db_wrapper.db
        hists = shot_detection.compute_histograms(
            db,
            videos=[v.for_scannertools() for v in videos],
            run_opts={
                'io_packet_size': 10000,
                'work_packet_size': 1000
            })

        bfs = compute_black_frames(
            db,
            videos=[v.for_scannertools() for v in videos],
            histograms=hists,
            run_opts={
                'io_packet_size': 100000,
                'work_packet_size': 10000
            })

        def load_bf(i):
            path = '/app/data/blackframes/{:07d}.bin'.format(i)
            if os.path.isfile(path):
                return

            try:
                with open(path, 'wb') as f:
                    f.write(np.array(list(bfs[i].load()), dtype=np.uint8).tobytes())
            except Exception:
                print(i)

        print('Loading...')
        par_for(load_bf, list(range(len(bfs))), workers=8)
