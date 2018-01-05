from query.datasets.prelude import *
from scannerpy.stdlib import parsers
from scipy.spatial import distance
from unionfind import unionfind
import bisect


LABELER, _ = Labeler.objects.get_or_create(name='shot-histogram')
cwd = os.path.dirname(os.path.abspath(__file__))


def compute_histograms(videos, force=False):
    def output_name_hist(video):
        return video.path + '_hist'

    def output_name_shots(video):
        return video.path + '_shots'


    with Database(prefetch_table_metadata=False) as db:
        db.register_op('ShotDetection', ['histogram'], ['shots'], stencil=[0])
        db.register_python_kernel('ShotDetection', DeviceType.CPU, cwd + '/shot_kernel.py')
        # ingest_if_missing(db, videos)
        
        frame = db.ops.FrameInput()
        histogram = db.ops.Histogram(frame=frame, device=DeviceType.GPU)
        output = db.ops.Output(columns=[histogram])
        jobs = [
            Job(op_args={frame: db.table(video.path).column('frame'),
                         output: output_name_hist(video)}) for video in videos
            if not db.has_table(output_name_hist(video)) or force
        ]
        if len(jobs) > 0:
            raise Exception(video.path)
            bulk_job = BulkJob(output=output, jobs=jobs)
            logging.debug('Running Scanner histogram job on {} videos...'.format(len(jobs)))
            db.run(bulk_job, force=True, io_packet_size=10000)

        log.debug('Loading histograms...')
        for video in videos:
            t = db.table(output_name_hist(video))
            histogram = db.ops.Input()
            shots = db.ops.ShotDetection(histogram=histogram, stencil=range(t.num_rows()))
            output = db.ops.Output(columns=[shots])
            jobs = [
                Job(op_args={histogram: t.column('histogram'), 
                             output: output_name_shots(video)})
            ]
            bulk_job = BulkJob(output=output, jobs=jobs)
            logging.debug('Running Scanner shot detection job on {} videos'.format(len(jobs)))
            db.run(bulk_job, force=True, io_packet_size=200000, work_packet_size=200000, pipeline_instances_per_node=1)

        exit()

        # hists = [[
        #     h for _, h in db.table(output_name(video)).load(['histogram'], parsers.histograms)
        # ] for video in videos]
        # log.debug('Loaded!')

        return hists


WINDOW_SIZE = 500
GROUP_THRESHOLD = 10
STD_DEV_FACTOR = 1
MAGNITUDE_THRESHOLD = 5000


def compute_shot_boundaries(hists):
    # Compute the mean difference between each pair of adjacent frames
    log.debug('Computing means')
    diffs = np.array([
        np.mean([distance.chebyshev(hists[i - 1][j], hists[i][j]) for j in range(3)])
        for i in range(1, len(hists))
    ])
    diffs = np.insert(diffs, 0, 0)
    n = len(diffs)

    # Do simple outlier detection to find boundaries between shots
    log.debug('Detecting outliers')
    boundaries = []
    for i in range(1, n):
        window = diffs[max(i - WINDOW_SIZE / 2, 0):min(i + WINDOW_SIZE / 2, n)]
        if diffs[i] > MAGNITUDE_THRESHOLD and \
           diffs[i] - np.mean(window) > STD_DEV_FACTOR * np.std(window):
            boundaries.append(i)

    log.debug('Grouping adjacent frames')
    u = unionfind(len(boundaries))
    for i, bi in enumerate(boundaries):
        for j, bj in enumerate(boundaries):
            if abs(bi - bj) < GROUP_THRESHOLD:
                u.unite(i, j)
                break

    grouped_boundaries = [boundaries[g[len(g) / 2]] for g in u.groups()]

    return grouped_boundaries


def evaluate_boundaries(boundaries):
    gt = [
        226, 822, 2652, 3893, 4058, 4195, 4326, 4450, 4583, 4766, 5021, 5202, 5294, 5411, 6584,
        7140, 7236, 7388, 7547, 7673, 7823, 7984, 8148, 8338, 8494, 8625, 8914, 9042, 9207, 9308,
        11395, 11823, 12198, 12563, 13516, 13878, 13991, 14162, 14237, 14333, 14488, 14688, 14770,
        14825, 15017, 15537, 15701, 15866, 16012, 16112, 16295, 16452, 16601, 16880, 17018, 17184,
        17310, 17446, 17962, 18713, 18860, 19120, 19395, 19543, 19660, 19839, 19970, 20079, 20248,
        20291, 20862
    ]
    gt = [n - 20 for n in gt]

    DIST_THRESHOLD = 15
    gt_copy = gt[:]

    boundaries = [n for n in boundaries if n < gt[-1]]

    tp = 0
    fp = 0
    for i in boundaries:
        valid = None
        for k, j in enumerate(gt_copy):
            if abs(i - j) < DIST_THRESHOLD:
                valid = k
                break
        if valid is None:
            fp += 1
        else:
            tp += 1
            gt_copy = gt_copy[:k] + gt_copy[(k + 1):]

    fn = len(gt_copy)

    precision = tp / float(tp + fp)
    recall = tp / float(tp + fn)
    log.debug('# est shots: {}, # gt shots: {}'.format(len(boundaries), len(gt)))
    log.debug('remaining shots: {}'.format(gt_copy))
    log.debug('tp: {}, fp: {}, fn: {}'.format(tp, fp, fn))

    log.info('Precision: {:.3f}, recall: {:.3f}, #det/#gt: {:.3f}'.format(
        precision, recall, len(boundaries) / float(len(gt))))


def boundaries_to_shots(video, boundaries):
    shots = []
    for i in range(len(boundaries) - 1):
        start = 0 if i == 0 else boundaries[i]
        end = boundaries[i + 1] - 1
        shots.append(Shot(video=video, labeler=LABELER, min_frame=start, max_frame=end))
    return shots


# Known issues:
# 1. Tends to miss cuts half-screen cuts (from two people to one)
# 2. Overall low precision
# 3. False positives in long segments with little movement

# TODO:
# Better debugging tools
# Potentially exclude lower third and/or top of the frame


def shot_detect(videos, save=True, evaluate=False, force=False):
    if evaluate or force or not Shot.objects.filter(video=videos[0], labeler=LABELER).exists():

        log.debug('Computing histograms')
        all_hists = compute_histograms(videos, force)

        log.debug('Computing shot boundaries')
        all_boundaries = [compute_shot_boundaries(vid_hists) for vid_hists in all_hists]

        log.debug('Converting to shots')
        all_shots = [
            boundaries_to_shots(video, vid_boundaries)
            for video, vid_boundaries in zip(videos, all_boundaries)
        ]

        log.debug('Computed {} shots'.format(len(all_shots[0])))

        if save:
            log.debug('Saving shots')
            for (video, vid_shots) in zip(videos, all_shots):
                Shot.objects.filter(video=video, labeler=LABELER).delete()
                Shot.objects.bulk_create(vid_shots)

        if evaluate:
            log.debug('Evaluating shot results')
            evaluate_boundaries(all_boundaries[0])

        if not save:
            return all_shots

    return [
        list(
            Shot.objects.filter(video=video, labeler=LABELER).order_by('min_frame').select_related(
                'video')) for video in videos
    ]


STITCHED_LABELER, _ = Labeler.objects.get_or_create(name='shot-stitched')
FEATURE_DISTANCE_THRESHOLD = 0.5

def should_stitch((left_faces, left_features), (right_faces, right_features)):
    if len(left_faces) == 0 or len(right_faces) == 0 or len(left_faces) != len(right_faces):
        return False

    for face1, feat1 in zip(left_faces, left_features):
        found = False
        for i, (face2, feat2) in enumerate(zip(right_faces, right_features)):
            if bbox_iou(face1, face2) > 0.5 and distance.euclidean(feat1.load_features(), feat2.load_features()) < FEATURE_DISTANCE_THRESHOLD:
                right_faces = right_faces[:i] + right_faces[(i + 1):]
                right_features = right_features[:i] + right_features[(i + 1):]
                found = True
                break
        if not found:
            return False

    return len(right_faces) == 0


def shot_stitch(videos, all_shots, all_shot_frames, all_faces, all_features, force=False):
    if force or not Shot.objects.filter(video=videos[0], labeler=STITCHED_LABELER).exists():
        for k, (vid_shots, vid_shot_frames, vid_faces, vid_features) in \
            enumerate(zip(all_shots, all_shot_frames, all_faces, all_features)):

            log.debug('{}/{}'.format(k + 1, len(all_shots)))

            frame_map = defaultdict(lambda: ([], []), {
                frame_faces[0].person.frame.number: (frame_faces, frame_features)
                for (frame_faces, frame_features) in zip(vid_faces, vid_features)
            })

            u = unionfind(len(vid_shots))

            for i in range(len(vid_shots) - 1):
                left = frame_map[vid_shot_frames[i]]
                right = frame_map[vid_shot_frames[i + 1]]

                if should_stitch(left, right):
                    u.unite(i, i + 1)

            new_shots = []

            for group in u.groups():
                group = sorted(group)
                shot0 = vid_shots[group[0]]
                shot0.max_frame = vid_shots[group[-1]].max_frame
                new_shots.append(
                    Shot(
                        video=shot0.video,
                        min_frame=shot0.min_frame,
                        max_frame=vid_shots[group[-1]].max_frame,
                        labeler=STITCHED_LABELER))

        log.debug('{} --> {}'.format(len(vid_shots), len(new_shots)))
        Shot.objects.bulk_create(new_shots)

    all_shots = []
    all_shot_faces = []
    all_shot_features = []
    for (video, vid_faces, vid_features) in zip(videos, all_faces, all_features):
        frame_map = defaultdict(list, {
            frame_faces[0].person.frame.number: (frame_faces, frame_features)
            for (frame_faces, frame_features) in zip(vid_faces, vid_features)
        })
        frames = sorted(frame_map.keys())
        shots = list(
            Shot.objects.filter(video=video, labeler=STITCHED_LABELER).order_by('min_frame')
            .select_related('video'))
        shot_faces = []
        shot_features = []
        for shot in shots:
            idx = bisect.bisect_right(frames, shot.min_frame)
            if idx == len(frames) or frames[idx] > shot.max_frame:
                shot_faces.append([])
                shot_features.append([])
            else:
                shot_faces.append(frame_map[frames[idx]][0])
                shot_features.append(frame_map[frames[idx]][1])

        assert(len(shots) == len(shot_faces) and len(shots) == len(shot_features))

        all_shots.append(shots)
        all_shot_faces.append(shot_faces)
        all_shot_features.append(shot_features)

    return all_shots, all_shot_faces, all_shot_features

def foo(videos):
    return shot_detect(videos, save=False)

def main():
    with open('all_videos_dl.txt') as f:
        videos = ['tvnews/videos/{}.mp4'.format(s.strip()) for s in f.readlines()]
    videos = [Video(path=path) for path in videos]

    for i in range(740, len(videos), 1):
        log.debug(i, videos[i])
        shot_detect(videos[i:i+1], save=False)
    exit()

    with ProcessPoolExecutor(max_workers=8) as executor:
        batch = 5
        list(tqdm(executor.map(foo, [videos[i:i+batch] for i in range(0, len(videos), batch)])))

    video = Video.objects.get(path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4')
    shot_detect([video], save=False, evaluate=True)


if __name__ == '__main__':
    main()
