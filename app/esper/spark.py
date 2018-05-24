from esper.prelude import *

spark = SparkWrapper()

shot_labeler = Labeler.objects.get(name='shot-histogram')
commercial_labeler = Labeler.objects.get(name='haotian-commercials')
segment_labeler = Labeler.objects.get(name='haotian-segments')
speaker_labeler, _ = Labeler.objects.get_or_create(name='lium')
rudecarnie = Labeler.objects.get(name='rudecarnie')
mtcnn = Labeler.objects.get(name='mtcnn')


def load_videos():
    return spark.qs_to_df(
        Video.objects.all().annotate(
            hour=Extract('time', 'hour'), duration=Cast(F('num_frames') / F('fps'), models.IntegerField())) \
        .values('path', 'num_frames', 'fps', 'show_id', 'channel_id', 'hour', 'duration'))


def track_fields(qs, more_fields=[]):
    return qs.annotate(
            hour=Extract('video__time', 'hour'),
            week_day=Extract('video__time', 'week_day'),
            duration=Cast(
                (F('max_frame') - F('min_frame')) / F('video__fps'),
                models.FloatField())) \
        .values(*(['id', 'min_frame', 'max_frame', 'video__channel', 'video__show', 'duration', 'hour',
                   'video_id', 'week_day', 'video__time'] + more_fields)) \
        .order_by('id')


def load_shots():
    return spark.qs_to_df(track_fields(Shot.objects.filter(labeler=shot_labeler)))


def load_commercials():
    return spark.qs_to_df(track_fields(Commercial.objects.filter(labeler=commercial_labeler)))


def load_segments():
    return spark.qs_to_df(
        track_fields(Segment.objects.filter(labeler=segment_labeler), ['polarity', 'subjectivity']))


def match_segments(df, commercials, segments):
    with Timer('collect'):
        fields = ['id', 'min_frame', 'max_frame', 'video_id']
        shots_list = df.select(*fields).collect()
        commercials_list = commercials.select(*fields).collect()
        segments_list = segments.select(*fields).collect()

    with Timer('group by key'):
        grouped_shots = collect(shots_list, itemgetter('video_id'))
        grouped_commercials = collect(commercials_list, itemgetter('video_id'))
        grouped_segments = collect(segments_list, itemgetter('video_id'))

    def inrange(a, b):
        return b['min_frame'] <= a['min_frame'] and a['max_frame'] <= b['max_frame']

    in_commercial_dict = {d['id']: False for d in tqdm(shots_list)}
    segment_col = []
    for video_id, vid_shots in tqdm(iter(list(grouped_shots.items()))):
        if video_id not in grouped_commercials: continue
        vid_commercials = grouped_commercials[video_id]
        vid_segments = grouped_segments[video_id]

        for shot in vid_shots:
            segment_id = None
            for commercial in vid_commercials:
                if inrange(shot, commercial):
                    in_commercial_dict[shot['id']] = True
                    break
            for segment in vid_segments:
                if inrange(shot, segment):
                    segment_id = segment['id']
                    break
            segment_col.append([shot['id'], segment_id])

    sorted_col = [[k, in_commercial_dict[k]] for k in tqdm(sorted(in_commercial_dict.keys()))]
    df1 = spark.append_column(df, 'in_commercial', sorted_col)
    return spark.append_column(df1, 'segment_id', sorted(segment_col, key=itemgetter(0)))


def load_speakers():
    return spark.qs_to_df(
        track_fields(Speaker.objects.filter(labeler=speaker_labeler), ['gender_id']))


def load_speakers2(speakers, commercials, segments):
    return match_segments(speakers, commercials, segments)


def load_shots2(shots, commercials, segments):
    return match_segments(shots, commercials, segments)


def load_genders():
    return spark.qs_to_df(FaceGender.objects \
        .annotate(height=F('face__bbox_y2') - F('face__bbox_y1')) \
        .filter(labeler=rudecarnie, face__labeler=mtcnn) \
        .annotate(
            duration=Cast(
                (F('face__shot__max_frame') - F('face__shot__min_frame')) / F('face__shot__video__fps'),
                models.FloatField()),
            hour=Extract('face__person__frame__video__time', 'hour'),
            week_day=Extract('face__person__frame__video__time', 'week_day')) \
        .values('id', 'gender', 'height', 'duration', 'face__person__frame__video__channel', 'face__person__frame__video__show', 'face__person__frame__video__id', 'hour', 'face__id', 'face__shot', 'week_day', 'face__is_host'))


def load_faces():
    return spark.qs_to_df(Face.objects \
        .annotate(height=F('bbox_y2') - F('bbox_y1')) \
        .filter(labeler=mtcnn) \
        .annotate(
            duration=Cast(
                (F('shot__max_frame') - F('shot__min_frame')) / F('shot__video__fps'),
                models.FloatField()),
            hour=Extract('person__frame__video__time', 'hour')) \
        .values('id', 'duration', 'person__frame__video__channel', 'person__frame__video__show', 'hour', 'shot', 'is_host'))


def filter_hosts(speakers2, faces, shots):
    with Timer('collect'):
        fields = ['id', 'min_frame', 'max_frame', 'video_id']
        speakers_list = speakers2.select(*fields).collect()
        hosts = faces.where(faces.is_host == True)
        shots_list = shots.join(hosts, shots.id == faces.shot_id, 'inner').select(*fields).collect()

    with Timer('group by key'):
        grouped_shots = collect(shots_list, itemgetter('video_id'))
        grouped_speakers = collect(speakers_list, itemgetter('video_id'))

    def inrange(a, b):
        return b['min_frame'] <= a['min_frame'] and a['max_frame'] <= b['max_frame']

    has_host_dict = {d['id']: False for d in tqdm(speakers_list)}
    for video_id, vid_speakers in tqdm(list(grouped_speakers.items())):
        if video_id not in grouped_shots: continue
        vid_shots = grouped_shots[video_id]

        for speaker in vid_speakers:
            for shot in vid_shots:
                if inrange(speaker, shot):
                    has_host_dict[speaker['id']] = True
                    break

    sorted_col = [[k, has_host_dict[k]] for k in tqdm(sorted(has_host_dict.keys()))]
    df1 = spark.append_column(speakers2, 'has_host', sorted_col)
    return df1


def load_segment_links():
    return spark.qs_to_df(
        Segment.things.through.objects.filter(tvnews_segment__labeler=segment_labeler) \
        .values('id', 'tvnews_segment_id', 'tvnews_thing_id').order_by('id'))


def load_things():
    return spark.qs_to_df(Thing.objects.values('id', 'name', 'type').order_by('id'))
