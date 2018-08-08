from esper.prelude import *
from query.models import Labeler
from scannerpy.stdlib import readers
from scipy.spatial import distance
from unionfind import unionfind
import bisect

LABELER, _ = Labeler.objects.get_or_create(name='shot-histogram')
cwd = os.path.dirname(os.path.abspath(__file__))


def compute_histograms(db, videos, force=False):
    log.debug('Computing histograms on {} videos'.format(len(videos)))

    def output_name(video):
        return video.path + '_hist'

    # ingest_if_missing(db, videos)

    frame = db.ops.FrameInput()
    histogram = db.ops.Histogram(frame=frame, device=DeviceType.CPU, batch=500)
    output = db.ops.Output(columns=[histogram])
    jobs = [
        Job(op_args={
            frame: db.table(video.path).column('frame'),
            output: output_name(video)
        }) for video in videos
        if force or not db.has_table(output_name(video))
        or not db.table(output_name(video)).committed()
    ]

    if len(jobs) > 0:
        log.debug('Running Scanner histogram job on {} videos'.format(len(jobs)))

        db.run(
            output,
            jobs,
            force=True,
            io_packet_size=100000,
            work_packet_size=500,
            pipeline_instances_per_node=24)

    return [db.table(output_name(video)) for video in videos]


WINDOW_SIZE = 500
GROUP_THRESHOLD = 10
STD_DEV_FACTOR = 1
MAGNITUDE_THRESHOLD = 5000


def compute_shot_boundaries_scanner(db, videos, tables):
    log.debug('Computing shot boundaries on {} videos'.format(len(videos)))

    def output_name(video):
        return video.path + '_shots'

    batch = 1000000

    log.debug('Registering ops')
    try:
        db.register_op('ShotDetection', ['histogram'], ['shots'], unbounded_state=True)
        db.register_python_kernel(
            'ShotDetection', DeviceType.CPU, cwd + '/shot_kernel.py', batch=batch)
    except ScannerException:
        pass

    log.debug('Building jobs')
    histogram = db.ops.Input()
    shots = db.ops.ShotDetection(histogram=histogram)
    output = db.ops.Output(columns=[shots])
    jobs = [
        Job(op_args={
            histogram: t.column('histogram'),
            output: output_name(video)
        }) for video, t in zip(videos, tables)
        if not db.has_table(output_name(video)) or not db.table(output_name(video)).committed()
    ]

    log.debug('Running Scanner shot detection job on {} videos'.format(len(jobs)))
    ts = db.run(
        output,
        jobs,
        force=True,
        io_packet_size=batch,
        work_packet_size=batch,
        pipeline_instances_per_node=1,
        task_timeout=600)
    log.debug('Done')

    out_tables = [db.table(output_name(video)) for video in videos]
    boundaries = [[pickle.loads(b) for _, b in t.column('shots').load(rows=[t.num_rows() - 1])]
                  for t in out_tables]

    return boundaries


def compute_shot_boundaries(table):
    log.debug('Loading histograms')
    hists = [h for _, h in table.column('histogram').load(readers.histograms)]
    log.debug('Loaded!')

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
        precision, recall,
        len(boundaries) / float(len(gt))))


def boundaries_to_shots(video, boundaries):
    shots = []
    for i in range(len(boundaries) - 1):
        start = 0 if i == 0 else boundaries[i]
        end = boundaries[i + 1] - 1
        shots.append({
            'video_id': video.id,
            'labeler_id': LABELER.id,
            'min_frame': start,
            'max_frame': end
        })
    return shots


# Known issues:
# 1. Tends to miss cuts half-screen cuts (from two people to one)
# 2. Overall low precision
# 3. False positives in long segments with little movement

# TODO:
# Better debugging tools
# Potentially exclude lower third and/or top of the frame


def shot_detect(videos, save=True, evaluate=False, force=False):
    def load_combined():
        def load_shots():
            log.debug('Loading shots')

            log.debug('Connecting to database...')
            with make_scanner_db(kube=False) as db:
                log.debug('Connected!')
                db._load_db_metadata()

                def loader(t):
                    try:
                        return pickle.loads(
                            next(t.column('shots').load(rows=[t.num_rows() - 1]))[1])
                    except Exception:
                        traceback.print_exc()
                        print((t.name()))
                        return None

                log.debug('Getting tables')
                shots, indices = unzip([
                    (db.table(v.path + '_shots'), i) for i, v in tqdm(list(enumerate(videos)))
                    if db.has_table(v.path + '_shots') and db.table(v.path + '_shots').committed()
                ])
                log.debug('Loading tables')

                return par_for(loader, shots, workers=64), indices

        all_boundaries, indices = pcache.get('all_boundaries', load_shots)

        log.debug('Filtering bad results')
        indices2, filtered_boundaries = unzip(
            [(idx, combined) for idx, combined in tqdm(list(zip(indices, all_boundaries)))
             if combined is not None])

        log.debug('Converting to shots')
        all_shots, all_blackframes = unzip(
            [(boundaries_to_shots(video, vid_boundaries), vid_blackframes)
             for video, (
                 vid_boundaries,
                 vid_blackframes) in tqdm(list(zip(gather(videos, indices2), filtered_boundaries)))])

        log.debug('Done!')
        return indices2, all_shots, all_blackframes

    return pcache.get('all_shots_blackframes', load_combined, method='pickle')

    # all_tables = compute_histograms(db, videos, force)

    # videos, all_tables = unzip(
    #     [(v, db.table(v.path + '_hist')) for v in videos
    #      if db.has_table(v.path + '_hist') and db.table(v.path + '_hist').committed()])

    # all_boundaries = compute_shot_boundaries_scanner(db, videos, all_tables)
    # exit()

    # all_boundaries = [compute_shot_boundaries(t) for t in all_tables]

    # videos_without_shots = set([v['path'] for v in Video.objects.annotate(
    #     c=Subquery(
    #         Shot.objects.filter(video=OuterRef('pk')).values('video') \
    #         .annotate(c=Count('video')).values('c')
    #     )).filter(c__isnull=True).values('path')])

    # log.debug('Bulk fetch videos')
    # to_load = [
    #     v for v in videos
    #     if db.has_table(v.path + '_shots') and db.table(v.path + '_shots').committed()
    # ]

    # # log.debug('Bulk load shots')
    # # shots = bulk_load(db, to_load)
    # # pcache.set('all_shots_2', shots)
    # shots = zip([v.path for v in to_load], pcache.get('all_shots_2'))

    # log.debug('Depickling')
    # video_map = {v.path: v for v in videos}
    # # pickled_shots = pickle.load(open('/app/notebooks/all_shots.pkl', 'rb'))
    # pickled_shots = shots
    # videos, all_boundaries, all_black_frames = unzip([(video_map[path.replace(
    #     '_shots', '')], t[0], t[1]) for (path, t) in pickled_shots if t is not None])

    if save:
        log.debug('Saving shots')
        for (video, vid_shots) in tqdm(list(zip(videos, all_shots))):
            Shot.objects.filter(video=video, labeler=LABELER).delete()
            Shot.objects.bulk_create(vid_shots)

    log.debug('Done')
    exit()

    if evaluate:
        log.debug('Evaluating shot results')
        evaluate_boundaries(all_boundaries[0])

    if not save:
        return all_shots

    def load_shots():
        log.debug('Loading shots')
        shot_map = defaultdict(list)
        shots = Shot.objects.filter(labeler=LABELER).values('id', 'min_frame', 'max_frame',
                                                            'video__id')
        for shot in tqdm(shots.iterator()):
            shot_map[shot['video__id']].append(shot)

        log.debug('loaded')
        shots = [shot_map[v.id] for v in videos]
        return [[(t['id'], t['min_frame'], t['max_frame'], t['video__id']) for t in l]
                for l in shots]

        shots = pcache.get('shots', load_shots)
        shots = [[{
            'id': t[0],
            'min_frame': t[1],
            'max_frame': t[2],
            'video__id': t[3]
        } for t in l] for l in shots]
        return shots

    # def load_shots(video):
    #     return list(
    #         Shot.objects.filter(video=video, labeler=LABELER).order_by('min_frame').values(
    #             'id', 'min_frame', 'max_frame', 'video__id'))

    # return par_for(load_shots, videos)


STITCHED_LABELER, _ = Labeler.objects.get_or_create(name='shot-stitched')
FEATURE_DISTANCE_THRESHOLD = 0.5


def should_stitch(xxx_todo_changeme, xxx_todo_changeme1):
    (left_faces, left_features) = xxx_todo_changeme
    (right_faces, right_features) = xxx_todo_changeme1
    if len(left_faces) == 0 or len(right_faces) == 0 or len(left_faces) != len(right_faces):
        return False

    for face1, feat1 in zip(left_faces, left_features):
        found = False
        for i, (face2, feat2) in enumerate(zip(right_faces, right_features)):
            if bbox_iou2(face1, face2) > 0.5 and distance.euclidean(
                    feat1, feat2) < FEATURE_DISTANCE_THRESHOLD:
                right_faces = right_faces[:i] + right_faces[(i + 1):]
                right_features = right_features[:i] + right_features[(i + 1):]
                found = True
                break
        if not found:
            return False

    return len(right_faces) == 0


def do_stitch(xxx_todo_changeme2):
    # frame_map = defaultdict(
    #     lambda: ([], []), {
    #         frame_faces[0].person.frame.number: (frame_faces, frame_features)
    #         for (frame_faces, frame_features) in zip(vid_faces, vid_features)
    #     })

    (vid_shots, vid_shot_frames, vid_faces, vid_features) = xxx_todo_changeme2
    u = unionfind(len(vid_shots))

    for i in range(len(vid_shots) - 1):
        left = (vid_faces[i], vid_features[i])
        right = (vid_faces[i + 1], vid_features[i + 1])

        if should_stitch(left, right):
            u.unite(i, i + 1)

    new_shots = []
    indices = []
    for group in u.groups():
        group = sorted(group)
        shot0 = vid_shots[group[0]]
        shot0['max_frame'] = vid_shots[group[-1]]['max_frame']
        indices.append(group[0])
        new_shots.append({
            'video_id': shot0['video_id'],
            'min_frame': shot0['min_frame'],
            'max_frame': vid_shots[group[-1]]['max_frame'],
            'labeler_id': STITCHED_LABELER.id
        })

    return new_shots, indices


def shot_stitch(videos, all_shots, all_shot_frames, all_faces, all_features, force=False):
    if force or not Shot.objects.filter(video=videos[0], labeler=STITCHED_LABELER).exists() or True:
        log.debug('Doing shot stitch')
        # log.debug('{} --> {}'.format(len(vid_shots), len(new_shots)))

        # Shot.objects.bulk_create(new_shots)

        return unzip(
            par_for(
                do_stitch,
                list(zip(all_shots, all_shot_frames, all_faces, all_features)),
                process=True,
                workers=50))

    all_shots = []
    all_shot_faces = []
    all_shot_features = []
    for (video, vid_faces, vid_features) in zip(videos, all_faces, all_features):
        frame_map = defaultdict(
            list, {
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

        assert (len(shots) == len(shot_faces) and len(shots) == len(shot_features))

        all_shots.append(shots)
        all_shot_faces.append(shot_faces)
        all_shot_features.append(shot_features)

    return all_shots, all_shot_faces, all_shot_features


def foo(videos):
    return shot_detect(videos, save=False)


def main():
    video_map = {v.path: v for v in Video.objects.all()}
    with open('all_videos_dl.txt') as f:
        paths = ['tvnews/videos/{}.mp4'.format(s.strip()) for s in f.readlines()]
    videos = [video_map[path] for path in paths]

    shot_detect(videos, force=True)

    # video = Video.objects.get(path='tvnews/videos/MSNBC_20100827_060000_The_Rachel_Maddow_Show.mp4')
    # shot_detect([video], save=False, evaluate=True)


if __name__ == '__main__':
    main()
