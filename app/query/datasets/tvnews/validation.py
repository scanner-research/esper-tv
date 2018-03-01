from query.datasets.prelude import *
from sklearn import metrics

gender_names = {g.id: g.name for g in Gender.objects.all()}
gender_ids = {v: k for k, v in gender_names.iteritems()}


def bootstrap(pred_statistic, pred_sample, true_statistic, true_sample, k=500, trials=10000):
    def invert(l):
        return {k: [d[k] for d in l] for k in l[0].keys()}

    all_stats = invert([pred_statistic(np.random.choice(pred_sample, k)) for _ in range(trials)])
    true_stat = true_statistic(true_sample)
    pred_stat = pred_statistic(pred_sample)
    return {
        k: {
            'est': pred_stat[k],
            'bias': np.mean(k_stats - np.full(k_stats.shape, true_stat[k])),
            'std': np.std(k_stats),
        }
        for k, k_stats in all_stats.iteritems()
    }


def face_validation(name, face_filter):
    handlabeled_frames = list(Frame.objects.filter(tags__name='handlabeled-face:labeled'))
    all_faces = collect(
        face_filter(
            Face.objects.filter(person__frame__in=handlabeled_frames).values_with(
                'labeler__name', 'person__frame__id')),
        itemgetter('person__frame__id'))
    auto_labeler = 'mtcnn'
    gt_labeler = 'handlabeled-face'
    true_pos = 0
    false_pos = 0
    false_neg = 0

    def face_in_list(candidate, faces, threshold=0.3):
        if len(faces) == 0: return None
        ious = [bbox_iou2(candidate, face) for face in faces]
        imax = np.argmax(ious)
        if ious[imax] > threshold:
            return faces[imax]
        else:
            return None

    face_pairs = []
    missed_faces = []
    for frame in handlabeled_frames:
        if frame.id not in all_faces:
            continue
        frame_faces = defaultdict(list, collect(all_faces[frame.id], itemgetter('labeler__name')))
        for auto_face in frame_faces[auto_labeler]:
            gt_face = face_in_list(auto_face, frame_faces[gt_labeler])
            if gt_face is not None:
                true_pos += 1
                face_pairs.append([auto_face, gt_face])
            else:
                false_pos += 1

        for gt_face in frame_faces[gt_labeler]:
            if face_in_list(gt_face, frame_faces[auto_labeler]) is None:
                false_neg += 1
                missed_faces.append(gt_face)

    face_precision = true_pos / float(true_pos + false_pos)
    face_recall = true_pos / float(true_pos + false_neg)
    print('== {} =='.format(name))
    print('# labels: {}'.format(true_pos + false_neg))
    print('Precision: {:.3f}, recall: {:.3f}'.format(face_precision, face_recall))
    print('')

    return face_pairs, missed_faces, (face_precision, face_recall)


def gender_validation(name, (face_pairs, missed_faces, _)):
    handlabeled_frames = list(Frame.objects.filter(tags__name='handlabeled-face:labeled'))
    all_genders = defaultdict(
        list,
        collect(
            FaceGender.objects.filter(face__person__frame__in=handlabeled_frames).values_with(
                'labeler__name', 'face__person__frame__id'),
            itemgetter('face__person__frame__id')))
    auto_labeler = 'rudecarnie'
    gt_labeler = 'handlabeled-gender'
    true_pos = 0
    false_pos = 0
    false_neg = 0

    face_pairs_dict = {auto['id']: gt for (auto, gt) in face_pairs}

    y_true = []
    y_pred = []
    for frame in handlabeled_frames:
        frame_genders = defaultdict(list, collect(all_genders[frame.id],
                                                  itemgetter('labeler__name')))
        gt_genders = {d['face']: d for d in frame_genders[gt_labeler]}
        for auto_gender in frame_genders[auto_labeler]:
            if not auto_gender['face'] in face_pairs_dict:
                continue
            gt_face = face_pairs_dict[auto_gender['face']]
            gt_gender = gt_genders[gt_face['id']]
            y_true.append(gt_gender['gender'])
            y_pred.append(auto_gender['gender'])

    gender_accuracy = metrics.accuracy_score(y_true, y_pred)

    total_distribution = defaultdict(int)
    for y in y_true:
        total_distribution[y] += 1

    missed_distribution = defaultdict(int)
    for face in missed_faces:
        missed_distribution[FaceGender.objects.get(face_id=face['id']).gender_id] += 1

    def print_distribution(name, dist):
        print('{}:'.format(name))
        pprint({
            gender_names[k]: '{:.3f}'.format(v / float(sum(dist.values())))
            for k, v in dist.iteritems()
        })

    print('== {} =='.format(name))
    print('# labels: {}'.format(len(y_true)))
    print('Accuracy: {:.3f}'.format(gender_accuracy))
    print_distribution('Total distribution', total_distribution)
    print_distribution('Missed distribution', missed_distribution)
    print('')

    mat = metrics.confusion_matrix(y_true, y_pred)
    # plot_confusion_matrix(mat, [d['name'] for d in Gender.objects.values('name').order_by('id')])
    plot_confusion_matrix(
        mat, [d['name'] for d in Gender.objects.values('name').order_by('id')], normalize=True)

    return gender_accuracy, mat


def screentime_validation(name, face_filter, gender_cmat):
    handlabeled_frames = list(Frame.objects.filter(tags__name='handlabeled-face:labeled'))
    all_genders = defaultdict(
        list,
        collect(
            face_filter(
                FaceGender.objects.filter(face__person__frame__in=handlabeled_frames)).values_with(
                    'labeler__name', 'face__person__frame__id', 'face__shot__id'),
            itemgetter('face__person__frame__id')))

    labelers = ['rudecarnie', 'rudecarnie-adj', 'handlabeled-gender']
    counts = ['multicount', 'singlecount']

    true_gender = []
    pred_gender = []

    for frame in handlabeled_frames:
        frame_genders = defaultdict(list, collect(all_genders[frame.id],
                                                  itemgetter('labeler__name')))
        shot = Shot.objects.get(
            video=frame.video, min_frame__lte=frame.number, max_frame__gte=frame.number)
        duration = (shot.max_frame - shot.min_frame) / shot.video.fps
        counts = defaultdict(lambda: {i: 0 for i in gender_ids.values()})
        for k in ['rudecarnie', 'handlabeled-gender']:
            for g in frame_genders[k]:
                counts[k][g['gender']] += 1

        true_gender.append(counts['handlabeled-gender'])
        pred_gender.append(counts['rudecarnie'])

    def mod_totals(totals):
        totals = {gender_names[i]: v for i, v in totals.iteritems()}
        totals['M/F'] = totals['M'] / float(totals['F'])
        return totals

    def singlecount(G, P):
        totals = {i: 0 for i in gender_ids.values()}
        for frame in G:
            for i in gender_ids.values():
                if frame[i] > 0:
                    totals[i] += 1
        return mod_totals(totals)

    def singlecount_adj(G, P):
        totals = singlecount(G)
        adj_totals = {}
        for g in gender_ids.values():
            adj_totals[g] = sum(totals[gender_names[g2]] * P(gender_names[g], gender_names[g2])
                                for g2 in gender_ids.values())
        return mod_totals(adj_totals)

    def multicount(G, P):
        totals = {i: 0 for i in gender_ids.values()}
        for frame in G:
            for i in gender_ids.values():
                totals[i] += frame[i]
        return mod_totals(totals)

    def multicount_adj(G, P):
        totals = multicount(G)
        adj_totals = {}
        for g in gender_ids.values():
            adj_totals[g] = sum(totals[gender_names[g2]] * P(gender_names[g], gender_names[g2])
                                for g2 in gender_ids.values())
        return mod_totals(adj_totals)

    def P(y, yhat):
        indices = {'M': 0, 'F': 1, 'U': 2}
        return float(gender_cmat[indices[y]][indices[yhat]]) / sum(
            [gender_cmat[i][indices[yhat]] for i in indices.values()])

    def print_results(name, r):
        print('== {} =='.format(name))
        print(pd.DataFrame.from_dict(r, orient='index')[['est', 'bias',
                                                         'std']]).reindex(['M', 'F', 'U', 'M/F'])
        print('')

    metrics = [['multicount', [multicount, multicount_adj]],
               ['singlecount', [singlecount, singlecount_adj]]]

    print('{} {} {}\n'.format('=' * 20, name, '=' * 20))
    for [name, submetrics] in metrics:
        print('======= {} =======\n'.format(name.upper()))
        print('== true ==')
        print(pd.DataFrame.from_dict(submetrics[0](true_gender, P), orient='index').rename(
            index=str, columns={
                0: 'est'
            }).reindex(['M', 'F', 'U', 'M/F']))
        print('\n')
        print_results('unadjusted', bootstrap(submetrics[0], pred_gender, submetrics[0],
                                              true_gender))
        print_results('adjusted', bootstrap(submetrics[1], pred_gender, submetrics[0], true_gender))
