from esper.prelude import *

LABELER, _ = Labeler.objects.get_or_create(name='featuretrack')


def dist(feat1, feat2):
    return np.sum(np.square(np.subtract(feat1, feat2)))


def track_faces(videos, all_features):
    threshold = 0.65
    sequence_time = 5
    min_feat_threshold = 3

    all_tracks = []
    for (video, vid_features) in zip(videos, all_features):
        log.debug(video.path)

        fps = video.fps

        # [first_frame, last_frame, all_features, avg_feature, sum_feature]
        recent_features = []
        faces_len = len(vid_features)
        in_seq = 0
        short_seq = 0
        low_confidence = 0

        old_frame_id = 0
        #index in the face array NOT the face id
        tracks = []
        for face_idx in range(faces_len):
            curr_face = vid_features[face_idx]
            curr_feature = np.array(json.loads(str(curr_face.features)))
            curr_face_id = curr_face.face.id
            curr_frame_id = curr_face.face.person.frame.number
            confidence = curr_face.face.bbox_score
            #                if confidence < .98:
            #                    low_confidence += 1
            #                    continue

            if old_frame_id != curr_frame_id:
                keep_set = []
                complete_set = []
                for feat in recent_features:
                    if float(curr_frame_id - feat[1]) / fps > sequence_time:
                        complete_set.append(feat)
                    else:
                        keep_set.append(feat)
                if len(keep_set) != len(recent_features):
                    recent_features = keep_set
                    if len(complete_set) > 0:
                        for item in complete_set:
                            seq_len = len(item[2])
                            if (seq_len < min_feat_threshold):
                                short_seq += len(item[2])
                                continue
                            track = PersonTrack(min_frame=0, max_frame=0, video=video, labeler=LABELER)
                            track.save()
                            tracks.append(track)
                            last_frame = None
                            for seq_face_id in item[2]:
                                seq_face = Face.objects.get(id=seq_face_id)
                                if seq_face.person.frame.number == last_frame: continue
                                seq_face.person.tracks.add(track)
                                in_seq += 1
                                seq_face.save()
                                last_frame = seq_face.person.frame.number

                old_frame_id = curr_frame_id
            best_match = -1
            best_distance = 10000.0
            for i in range(len(recent_features)):
                curr_dist = dist(curr_feature, recent_features[i][3])
                if curr_dist < best_distance:
                    best_distance = curr_dist
                    best_match = i

            if best_match == -1 or best_distance > threshold:
                recent_features.append(
                    [curr_frame_id, curr_frame_id, [curr_face_id], curr_feature, curr_feature])
            else:
                recent_features[best_match][1] = curr_frame_id
                recent_features[best_match][2].append(curr_face_id)
                recent_features[best_match][4] = np.add(recent_features[best_match][4],
                                                        curr_feature)
                recent_features[best_match][3] = np.divide(recent_features[best_match][4],
                                                           len(recent_features[best_match][2]))

        for item in recent_features:
            seq_len = len(item[2])
            if (seq_len < min_feat_threshold):
                short_seq += len(item[2])
                continue
            track = PersonTrack(min_frame=0, max_frame=0, video=video, labeler=LABELER)
            track.save()
            tracks.append(track)
            last_frame = None
            for seq_face_id in item[2]:
                seq_face = Face.objects.get(id=seq_face_id)
                if seq_face.person.frame.number == last_frame: continue
                seq_face.person.tracks.add(track)
                in_seq += 1
                seq_face.save()
                last_frame = seq_face.person.frame.number
        log.debug('total faces: ', faces_len)
        log.debug('in output seq: ', in_seq)
        log.debug('dropped in short seq: ', short_seq)
        log.debug('low confidence', low_confidence)
        log.debug('accounted for: ', (low_confidence + short_seq + in_seq))

        all_tracks.append(track)
    return all_tracks
