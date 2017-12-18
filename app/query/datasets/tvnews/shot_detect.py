from query.datasets.prelude import *
from scannerpy.stdlib import parsers
from scipy.spatial import distance

WINDOW_SIZE = 500


def compute_shot_boundaries(hists):
    # Compute the mean difference between each pair of adjacent frames
    diffs = np.array([
        np.mean([distance.chebyshev(hists[i - 1][j], hists[i][j]) for j in range(3)])
        for i in range(1, len(hists))
    ])
    diffs = np.insert(diffs, 0, 0)
    n = len(diffs)

    # Do simple outlier detection to find boundaries between shots
    boundaries = []
    for i in range(1, n):
        window = diffs[max(i - WINDOW_SIZE, 0):min(i + WINDOW_SIZE, n)]
        if diffs[i] - np.mean(window) > 3 * np.std(window):
            boundaries.append(i)
    return boundaries


def main():
    video = Video.objects.get(path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4')
    labeler, _ = Labeler.objects.get_or_create(name='shot-histogram')

    with Database() as db:
        frame = db.ops.FrameInput()
        histogram = db.ops.Histogram(frame=frame, device=DeviceType.GPU)
        output = db.ops.Output(columns=[histogram])
        job = Job(
            op_args={frame: db.table(video.path).column('frame'),
                     output: video.path + '_hist'})
        bulk_job = BulkJob(output=output, jobs=[job])
        # [hists_table] = db.run(bulk_job, force=True, io_packet_size=10000)
        hists_table = db.table(video.path + '_hist')

        print('Loading histograms...')
        hists = [h for _, h in hists_table.load(['histogram'], parsers.histograms)]
        print('Loaded!')

    print('Computing shot boundaries...')
    boundaries = compute_shot_boundaries(hists)
    print('Computed!')
    print(len(boundaries))

    shots = []
    for i in range(len(boundaries) - 1):
        start = 0 if i == 0 else boundaries[i]
        end = boundaries[i + 1] - 1
        shots.append(Shot(video=video, labeler=labeler, min_frame=start, max_frame=end))
    Shot.objects.bulk_create(shots)


if __name__ == '__main__':
    main()
