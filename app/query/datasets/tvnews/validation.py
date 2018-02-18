from query.datasets.prelude import *
from sklearn import metrics


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

    face_precision = true_pos / float(true_pos + false_pos)
    face_recall = true_pos / float(true_pos + false_neg)
    print('== {} =='.format(name))
    print('# labels: {}'.format(true_pos + false_neg))
    print('Precision: {:.3f}, recall: {:.3f}'.format(face_precision, face_recall))
    print('')

    return face_pairs, (face_precision, face_recall)


def gender_validation(name, face_pairs):
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
    print('== {} =='.format(name))
    print('# labels: {}'.format(len(y_true)))
    print('Accuracy: {:.3f}'.format(gender_accuracy))
    print('')

    mat = metrics.confusion_matrix(y_true, y_pred)
    # plot_confusion_matrix(mat, [d['name'] for d in Gender.objects.values('name').order_by('id')])
    plot_confusion_matrix(
        mat, [d['name'] for d in Gender.objects.values('name').order_by('id')], normalize=True)

    return gender_accuracy
