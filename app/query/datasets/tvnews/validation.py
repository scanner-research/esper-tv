from query.datasets.prelude import *
from sklearn import metrics

gender_names = {g.id: g.name for g in Gender.objects.all()}
gender_ids = {v: k for k, v in gender_names.iteritems()}


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
    totals = {k1: {k2: defaultdict(int) for k2 in counts} for k1 in labelers}

    for frame in handlabeled_frames:
        frame_genders = defaultdict(list, collect(all_genders[frame.id],
                                                  itemgetter('labeler__name')))
        shot = Shot.objects.get(
            video=frame.video, min_frame__lte=frame.number, max_frame__gte=frame.number)
        duration = (shot.max_frame - shot.min_frame) / shot.video.fps
        for k in labelers:
            has_gender = set()
            for g in frame_genders[k]:
                has_gender.add(g['gender'])
                totals[k]['multicount'][g['gender']] += 1  #duration
            for g in has_gender:
                totals[k]['singlecount'][g] += 1  #duration

    def P(y, yhat):
        indices = {'M': 0, 'F': 1, 'U': 2}
        return float(gender_cmat[indices[y]][indices[yhat]]) / sum(
            [gender_cmat[i][indices[yhat]] for i in indices.values()])

    print(gender_cmat)
    print(P('M', 'F'))
    print(P('U', 'F'))
    print(P('M', 'M'))

    for c in counts:
        base = totals['rudecarnie'][c]
        for g in ['M', 'F', 'U']:
            totals['rudecarnie-adj'][c][gender_ids[g]] = sum(
                [base[gender_ids[g2]] * P(g, g2) for g2 in ['M', 'F', 'U']])

    d = totals
    print('== {} =='.format(name))
    flat_dict = {(i, j): {gender_names[k]: d[i][j][k]
                          for k in d[i][j].keys()}
                 for i in d.keys() for j in d[i].keys()}

    for l in labelers:
        for c in counts:
            flat_dict[(l, c)]['M/F'] = float(d[l][c][gender_ids['M']]) / d[l][c][gender_ids['F']]

    df = pd.DataFrame.from_dict(flat_dict, orient='index').reset_index()
    print(df.pivot_table(index=['level_1', 'level_0']))
    print('')


# if __name__ == '__main__':
#     screentime_validation('All faces', lambda x: x)
#     # screentime_validation(
#     #     'Face height > 0.2',
#     #     lambda qs: qs.annotate(height=F('face__bbox_y2') - F('face__bbox_y1')).filter(height__gte=0.2))
