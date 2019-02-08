import pyspark.sql.functions as func
from pyspark.sql.types import BooleanType, IntegerType, StringType, DoubleType
from collections import defaultdict, Counter
import datetime
import calendar
import sys

from esper.widget import *
from esper.prelude import *
from esper.spark import *
from esper.validation import *

from query.models import Labeler

spark = SparkWrapper()


def get_shows():
    shows = spark.load('query_show').alias('shows')

    show_hosts = spark.load('query_show_hosts')
    show_id_to_host_count = Counter()
    for e in show_hosts.collect():
        show_id_to_host_count[e.show_id] += 1

    def num_hosts_helper(show_id):
        return int(show_id_to_host_count[show_id])

    my_udf = func.udf(num_hosts_helper, IntegerType())
    shows = shows.withColumn('num_hosts', my_udf('id'))
    return shows


def get_videos():
    videos = spark.load('query_video').alias('videos')

    shows = get_shows()
    videos = videos.join(
        shows, videos.show_id == shows.id
    ).select(
        'videos.*', 'shows.canonical_show_id'
    )

    videos = videos.withColumn('duration', videos.num_frames / videos.fps)
    videos = videos.withColumn('hour', func.hour(videos.time))
    videos = videos.withColumn('month', func.month(videos.time))
    videos = videos.withColumn('year', func.year(videos.time))
    videos = videos.withColumn(
        'duration', videos.num_frames / videos.fps
    )

    def week_day_helper(time):
        year, month, day = (int(x) for x in time.split(' ')[0].split('-'))
        weekday = datetime.date(year, month, day)
        return weekday.isoweekday()

    my_udf = func.udf(week_day_helper, IntegerType())
    videos = videos.withColumn('week_day', my_udf('time'))

    return videos


def _annotate_hour(df):
    assert ('video_id' in df.columns)
    assert ('min_frame' in df.columns)

    video_id_to_hour_fps = defaultdict(lambda: (0, 29.97))
    for v in get_videos().select('id', 'fps', 'hour').collect():
        video_id_to_hour_fps[v.id] = (v.hour, v.fps)
    def hour_helper(video_id, min_frame):
        start_hour, fps = video_id_to_hour_fps[video_id]
        hour_offset = (min_frame / fps) / 3600.
        return int(start_hour + hour_offset) % 24
    my_udf = func.udf(hour_helper, IntegerType())
    df = df.withColumn(
        'hour', my_udf('video_id', 'min_frame')
    )
    return df


def get_commercials():
    commercials = spark.load('query_commercial').alias('commercials')

    videos = get_videos().alias('videos')
    commercials = commercials.join(
        videos, commercials.video_id == videos.id
    ).select(
        'commercials.*',
        'videos.fps',
        'videos.show_id',
        'videos.canonical_show_id',
        'videos.channel_id',
        'videos.month',
        'videos.year',
        'videos.week_day',
        'videos.time'
    )

    commercials = commercials.withColumn(
        'duration', (commercials.max_frame - commercials.min_frame) / commercials.fps
    )
    commercials = _annotate_hour(commercials)
    return commercials


def get_frames():
    frames = spark.load('query_frame').alias('frames')
    return frames

def get_shots():
    shots = spark.load('query_shot').alias('shots')

    videos = get_videos().alias('videos')
    shots = shots.join(
        videos, shots.video_id == videos.id
    ).select(
        'shots.*',
        'videos.fps',
        'videos.show_id',
        'videos.canonical_show_id',
        'videos.channel_id',
        'videos.month',
        'videos.year',
        'videos.week_day',
        'videos.time'
    )

    shots = shots.withColumn(
        'duration', (shots.max_frame - shots.min_frame) / shots.fps
    )
    shots = _annotate_hour(shots)
    return shots


def _annotate_in_commercial(df):
    assert ('video_id' in df.columns)
    assert ('min_frame' in df.columns)
    assert ('max_frame' in df.columns)

    video_id_to_commericals = defaultdict(list)
    for c in get_commercials().select('video_id', 'min_frame', 'max_frame').collect():
        video_id_to_commericals[c.video_id].append(
            (c.min_frame, c.max_frame)
        )
    def in_commercial_helper(video_id, min_frame, max_frame):
        if video_id in video_id_to_commericals:
            for c_min, c_max in video_id_to_commericals[video_id]:
                if min_frame >= c_min and min_frame < c_max:
                    return True
                if max_frame <= c_max and max_frame > c_min:
                    return True
        return False

    my_udf = func.udf(in_commercial_helper, BooleanType())
    df = df.withColumn(
        'in_commercial', my_udf('video_id', 'min_frame', 'max_frame')
    )
    return df


def get_speakers():
    speakers = spark.load('query_speaker').alias('speakers')

    videos = get_videos().alias('videos')
    speakers = speakers.join(
        videos, speakers.video_id == videos.id
    ).select(
        'speakers.*',
        'videos.fps',
        'videos.show_id',
        'videos.canonical_show_id',
        'videos.channel_id',
        'videos.week_day',
        'videos.time'
    )

    speakers = speakers.withColumn(
        'duration', (speakers.max_frame - speakers.min_frame) / speakers.fps
    )

    # TODO: annotate has_host field properly
    speakers = speakers.withColumn(
        'has_host', func.lit(False)
    )

    speakers = _annotate_in_commercial(speakers)
    speakers = _annotate_hour(speakers)
    return speakers


def get_segments():
    segments = spark.load('query_segment').alias('segments')
    segments = segments.where(segments.labeler_id == Labeler.objects.get(name='haotian-segments').id)

    videos = get_videos().alias('videos')
    segments = segments.join(
        videos, segments.video_id == videos.id
    ).select(
        'segments.*',
        'videos.fps',
        'videos.show_id',
        'videos.canonical_show_id',
        'videos.channel_id',
        'videos.week_day',
        'videos.time'
    )

    segments = segments.withColumn(
        'duration', (segments.max_frame - segments.min_frame) / segments.fps
    )
    segments = _annotate_in_commercial(segments)
    return segments


def get_topics():
    topics = spark.load('query_topic').alias('topics')
    return topics


def get_segment_topics():
    segments = get_segments()
    segment_topics = spark.load('query_segment_topics').alias('segment_topics')
    segment_topics = segment_topics.join(
        segments, segment_topics.segment_id == segments.id
    ).select(
        'segment_topics.*',
        segments.min_frame,
        segments.max_frame,
        segments.video_id
    )

    return segment_topics


def get_clothing():
    return spark.load('query_clothing').alias('clothing')


def get_hair_colors():
    return spark.load('query_haircolor').alias('hair_colors')


def get_hair_lengths():
    return spark.load('query_hairlength').alias('hair_length')


def interval_overlap_join(df1, df2):
    video_id_to_intervals = defaultdict(list)
    for c in df2.collect():
        video_id_to_intervals[c.video_id].append(
            (c.min_frame, c.max_frame, c)
        )

    output_intervals = []
    for row in df1.collect():
        for (start, end, row2) in video_id_to_intervals[row.video_id]:
            if row.min_frame < end and row.max_frame > start:
                row_dict = row.asDict()
                for k, v in row2.asDict().items():
                    if k == 'id':
                        continue
                    row_dict[k] = v
                row_dict['min_frame'] = max(row.min_frame, start)
                row_dict['max_frame'] = min(row.max_frame, end)
                row_dict['duration'] = (row_dict['max_frame'] - row_dict['min_frame']) / row.fps
                output_intervals.append(row_dict)
                break

    print(output_intervals[0])


NULL_IDENTITY_ID = -1


def _annotate_host_probability(faces, identity_threshold=0.5):
    labelers = get_labelers()
    labelers = labelers.where(
        labelers.name.contains('face-identity:') |
        labelers.name.contains('face-identity-converted:')
    )

    face_identities = spark.load('query_faceidentity').alias('face_identity')
    face_identities = face_identities.where(
        face_identities.probability > identity_threshold)
    face_identities = face_identities.join(
        labelers, face_identities.labeler_id == labelers.id,
        'left_outer')

    faces2 = get_faces(annotate_host_probability=False).alias('faces2')

    face_identities = face_identities.join(
        faces2, face_identities.face_id == faces2.id
    ).select(
        'face_identity.face_id',
        'face_identity.identity_id',
        'face_identity.labeler_id',
        'face_identity.probability',
        'faces2.show_id',
        'faces2.canonical_show_id', # Need this to get the hosts
        'faces2.channel_id'
    )

    print('Constructing host probability udf...', file=sys.stderr)

    # Annotate host probabilities
    canonical_show_id_to_host_ids = defaultdict(set)
    canonical_show_hosts = spark.load('query_canonicalshow_hosts')
    for e in canonical_show_hosts.collect():
        canonical_show_id_to_host_ids[e.canonicalshow_id].add(e.identity_id)
    print('  {} canonical shows have hosts'.format(
          len(canonical_show_id_to_host_ids)), file=sys.stderr)

    # Fall back to all channel staff if no host info is annotated
    channel_id_to_host_ids = defaultdict(set)
    for e in get_videos().select(
        'channel_id', 'canonical_show_id'
    ).distinct().collect():
        channel_id_to_host_ids[e.channel_id].update(
            canonical_show_id_to_host_ids[e.canonical_show_id])
    for channel_id, hosts in channel_id_to_host_ids.items():
        print('  channel_id={} has {} unique hosts'.format(
              channel_id, len(hosts)), file=sys.stderr)

    def is_host_helper(identity_id, canonical_show_id, channel_id):
        # Use a looser defintiion
        return identity_id in channel_id_to_host_ids[channel_id]
#         if canonical_show_id not in canonical_show_id_to_host_ids:
#             return identity_id in channel_id_to_host_ids[channel_id]
#         else:
#             return identity_id in canonical_show_id_to_host_ids[canonical_show_id]

    host_filter_udf = func.udf(is_host_helper, BooleanType())
    host_identities = face_identities.filter(
        host_filter_udf('identity_id', 'canonical_show_id', 'channel_id'))

    face_id_to_host_prob = defaultdict(float)
    for host in host_identities.collect():
        # If the face has multiple labels that indicate a host, take the highest probability one
        # This might happen if we mannually labeled a number of Wolf Blitzers while using the
        # partially-supervised approach to label the others
        if face_id_to_host_prob[host.face_id] < host.probability:
            face_id_to_host_prob[host.face_id] = host.probability

    def host_probability_helper(face_id):
        return face_id_to_host_prob.get(face_id, 0.)

    host_prob_udf = func.udf(host_probability_helper, DoubleType())
    faces = faces.withColumn('host_probability', host_prob_udf('id'))
    return faces


# Lazily Cached
_faces_wo_hosts = None
_faces_w_hosts = None


def get_faces(annotate_host_probability=True):
    global _faces_w_hosts, _faces_wo_hosts
    if annotate_host_probability:
        if _faces_w_hosts is not None:
            return _faces_w_hosts
    else:
        if _faces_wo_hosts is not None:
            return _faces_wo_hosts

    faces = spark.load('query_face').alias('faces')

    videos = get_videos()
    frames = get_frames()
    haircolors = get_hair_colors()
    hairlengths = get_hair_lengths()
    clothing = get_clothing()
    faces = faces.join(
        frames, faces.frame_id == frames.id
    ).join(
        videos, frames.video_id == videos.id
    ).where(
        (videos.corrupted == False) & (videos.duplicate == False)
    ).join(
        haircolors.where(haircolors.labeler_id == Labeler.objects.get(name='haotian-hairstyle').id), 
        faces.id == haircolors.face_id, 'left_outer'
    ).join(
        hairlengths.where(hairlengths.labeler_id == Labeler.objects.get(name='haotian-hairstyle').id), 
        faces.id == hairlengths.face_id, 'left_outer'
    ).join(
        clothing.where(clothing.labeler_id == Labeler.objects.get(name='haotian-clothing').id), 
        faces.id == clothing.face_id, 'left_outer'
    ).select(
        'faces.*',
        videos.show_id,
        videos.canonical_show_id,
        videos.channel_id,
        videos.time,
        videos.fps,
        videos.week_day,
        videos.threeyears_dataset,
        frames.video_id,
        frames.number,
        haircolors.color_id.alias('haircolor_id'),
        clothing.clothing_id.alias('clothing_id'),
        hairlengths.length_id.alias('hairlength_id')
    ).where(
        ((videos.threeyears_dataset == True) & (frames.number % func.floor(videos.fps * 3) == 0)) | \
        ((videos.threeyears_dataset == False) & (frames.number % func.ceil(videos.fps * 3) == 0))
    )

    faces = faces.withColumn('height', faces.bbox_y2 - faces.bbox_y1)
    faces = faces.withColumn('width', faces.bbox_x2 - faces.bbox_x1)
    faces = faces.withColumn('area', faces.height * faces.width)
    faces = faces.withColumn('duration', func.lit(3))
    faces = faces.withColumn('min_frame', faces.number)
    faces = faces.withColumn('max_frame', faces.number + func.floor(faces.fps * 3) - 1)

    faces = _annotate_hour(faces)
    faces = _annotate_in_commercial(faces)

    if annotate_host_probability:
        faces = _annotate_host_probability(faces)
        _faces_w_hosts = faces
    else:
        _faces_wo_hosts = faces
    return faces


def _annotate_size_percentile(face_genders, gender_threshold=0.9):
    face_genders2 = face_genders.where(face_genders.probability > gender_threshold)

    num_buckets = 10000
    face_genders2 = face_genders2.withColumn(
        'height_bucket', (face_genders2.height * num_buckets).cast(IntegerType())
    )

    key_to_size_buckets = defaultdict(lambda: {})
    for x in face_genders2.groupBy(
                'gender_id', 'in_commercial', 'height_bucket'
            ).count().collect():
        key_to_size_buckets[(
            x['gender_id'], x['in_commercial']
        )][x['height_bucket']] = x['count']

    key_to_size_cdf_buckets = defaultdict(lambda: ([0.] * num_buckets) + [100.])
    for k, size_buckets in key_to_size_buckets.items():
        denom = sum(size_buckets.values())
        acc_sum = 0.
        for b in range(num_buckets):
            acc_sum += size_buckets.get(b, 0.)
            key_to_size_cdf_buckets[k][b] = 100. * acc_sum / denom

    def size_percentile_helper(gender_id, in_commercial, height):
        return key_to_size_cdf_buckets[(gender_id, in_commercial)][int(height * num_buckets)]

    size_percentile_udf = func.udf(size_percentile_helper, DoubleType())
    face_genders = face_genders.withColumn(
        'size_percentile',
        size_percentile_udf('gender_id', 'in_commercial', 'height')
    )
    return face_genders


GENDER_FULL_NAME_MAP = {'M': 'male', 'F': 'female', 'U': 'unknown'}


def _annotate_male_female_probability(face_genders):
    """
    Adds male_probability and female_probability columns
    """
    gender_map = {
        x.id : GENDER_FULL_NAME_MAP[x.name]
        for x in spark.load('query_gender').select('id', 'name').collect()
        if x.name != 'U'
    }

    def build_udf(gid):
        gid_copy = gid
        def gender_prob_helper(gender_id, probability):
            return probability if gid_copy == gender_id else 1. - probability
        return func.udf(gender_prob_helper, DoubleType())

    for gid, gname in gender_map.items():
        gender_prob_udf = build_udf(gid)
        face_genders = face_genders.withColumn('{}_probability'.format(gname),
                                               gender_prob_udf('gender_id', 'probability'))

    return face_genders


def get_face_genders(include_bbox=False, annotate_host_probability=True):
    face_genders = spark.load('query_facegender').alias('face_genders')
    
    cols = [
        'face_genders.*',
        'faces.height',
        'faces.width',
        'faces.area',
        'faces.blurriness',
        'faces.shot_id',
        'faces.video_id',
        'faces.show_id',
        'faces.canonical_show_id',
        'faces.channel_id',
        'faces.duration',
        'faces.min_frame',
        'faces.max_frame',
        'faces.fps',
        'faces.in_commercial',
        'faces.hour',
        'faces.week_day',
        'faces.time',
        'faces.is_host',
        'faces.haircolor_id',
        'faces.hairlength_id',
        'faces.clothing_id',
    ]
    if annotate_host_probability:
        cols.append('faces.host_probability')
    if include_bbox:
        cols = cols + ['faces.bbox_x1',
                'faces.bbox_x2',
                'faces.bbox_y1',
                'faces.bbox_y2']

    faces = get_faces(annotate_host_probability=annotate_host_probability).alias('faces')
    face_genders = face_genders.join(
        faces, face_genders.face_id == faces.id
    ).select(*cols)

    face_genders = _annotate_size_percentile(face_genders)
    face_genders = _annotate_male_female_probability(face_genders)
    return face_genders


def get_labelers():
    labelers = spark.load('query_labeler').alias('labeler')
    return labelers


def get_face_identities(include_bbox=False, include_name=False, annotate_host_probability=True):
    labelers = get_labelers()
    labelers = labelers.where(
        labelers.name.contains('face-identity:') |
        labelers.name.contains('face-identity-converted:') |
        labelers.name.contains('face-identity-uncommon:')
    )

    face_identities = spark.load('query_faceidentity').alias('face_identities')
    face_identities = face_identities.join(
        labelers, face_identities.labeler_id == labelers.id)

    cols = [
        'face_identities.*',
        'faces.height',
        'faces.width',
        'faces.area',
        'faces.blurriness',
        'faces.shot_id',
        'faces.video_id',
        'faces.show_id',
        'faces.canonical_show_id',
        'faces.channel_id',
        'faces.duration',
        'faces.min_frame',
        'faces.max_frame',
        'faces.fps',
        'faces.in_commercial',
        'faces.hour',
        'faces.week_day',
        'faces.time',
        'faces.is_host',
        'faces.haircolor_id',
        'faces.hairlength_id',
        'faces.clothing_id'
    ]
    if annotate_host_probability:
        cols.append('faces.host_probability')
    if include_bbox:
        cols = cols + ['faces.bbox_x1',
                'faces.bbox_x2',
                'faces.bbox_y1',
                'faces.bbox_y2']

    faces = get_faces(annotate_host_probability=annotate_host_probability).alias('faces')
    face_identities = face_identities.join(
        faces, face_identities.face_id == faces.id
    ).select(*cols)

    if include_name:
        cols.append('identities.name')
        identities = spark.load('query_identity').alias('identities')
        face_identities = face_identities.join(
            identities, face_identities.identity_id == identities.id
        ).select(*cols)

    return face_identities


def annotate_interval_overlap(df, video_id_to_intervals, new_column_name='overlap_seconds'):
    """
    df is a dataframe with video_id, min_frame, max_frame and fps
    video_id_to_intervals is a dict mapping video_id to lists of tuples of (float, float)

    returns a dataframe with a new column that contains the number of seconds overlapped
    assuming the intervals passed do not overlap
    """
    assert ('video_id' in df.columns)
    assert ('min_frame' in df.columns)
    assert ('max_frame' in df.columns)
    assert ('fps' in df.columns)
    assert (new_column_name not in df.columns)

    def overlap_helper(video_id, min_frame, max_frame, fps):
        min_sec = min_frame / fps
        max_sec = max_frame / fps

        acc_overlap = 0.
        for interval in video_id_to_intervals.get(video_id, []):
            int_min_sec, int_max_sec = interval
            assert int_min_sec <= int_max_sec
            tmp = min(max_sec, int_max_sec) - max(min_sec, int_min_sec)
            if tmp > 0:
                acc_overlap += tmp
        return acc_overlap

    overlap_udf = func.udf(overlap_helper, DoubleType())
    return df.withColumn(new_column_name, overlap_udf('video_id', 'min_frame', 'max_frame', 'fps'))


WEIGHTED_VARIANCE_COLUMN = 'WEIGHTED_VARIANCE_COLUMN'
WEIGHTED_SUM_COLUMN = 'WEIGHTED_SUM_COLUMN'


def sum_over_column(df, sum_column, group_by_columns=[],
                    group_by_key_fn=lambda x: x, probability_column=None):
    """
    Sum a column with variance and expectation
    """
    df = df.withColumn(
        WEIGHTED_VARIANCE_COLUMN,
        df[probability_column] * (1. - df[probability_column]) * (df[sum_column] ** 2)
        if probability_column is not None else func.lit(0)
    )
    df = df.withColumn(
        WEIGHTED_SUM_COLUMN,
        df[probability_column] * df[sum_column] if probability_column is not None else df[sum_column]
    )

    sum_key = 'sum({})'.format(WEIGHTED_SUM_COLUMN)
    variance_key = 'sum({})'.format(WEIGHTED_VARIANCE_COLUMN)
    if len(group_by_columns) > 0:
        result = defaultdict(float)
        variance = defaultdict(float)
        tmp_df = df.groupBy(*group_by_columns).sum(
            WEIGHTED_SUM_COLUMN, WEIGHTED_VARIANCE_COLUMN
        )
        for x in tmp_df.collect():
            group_key = group_by_key_fn(tuple(x[col] for col in group_by_columns))
            result[group_key] += x[sum_key]
            variance[group_key] += x[variance_key]
        return defaultdict(lambda: (0., 0.), { k: (result[k], variance[k]) for k in result })
    else:
        result = 0.
        variance = 0.
        for x in df.groupBy().sum(WEIGHTED_SUM_COLUMN, WEIGHTED_VARIANCE_COLUMN).collect():
            result += x[sum_key]
            variance += x[variance_key]
        return result, variance


def sum_distinct_over_column(df, sum_column, distinct_columns, group_by_columns=[],
                             group_by_key_fn=lambda x: x, probability_column=None):
    """
    Sum a column over distinct values with variance and expectation
    (this is inefficient, but Spark does not have an easy way to do it...)

    sum_column: column name
    distinct_columns & group_by_columns: list of column names
    group_by_key_fn: a custom function for group by applied to the group by columns

    returns float or dict from group_by columns to float
    """
    if distinct_columns is None or len(distinct_columns) == 0:
        print('No distinct columns. Falling back to sum non-distinct (faster)')
        return sum_over_column(
            df, sum_column,
            group_by_columns=group_by_columns,
            group_by_key_fn=group_by_key_fn,
            probability_column=probability_column
        )

    if len(group_by_columns) > 0:
        result = defaultdict(float)
        variance = defaultdict(float)
    else:
        result = 0.
        variance = 0.
    distinct_set = set()

    select_columns = [sum_column, *distinct_columns, *group_by_columns]
    if probability_column is not None:
        select_columns.append(probability_column)

    for x in df.select(*select_columns).collect():
        distinct_key = tuple(x[col] for col in distinct_columns)
        if distinct_key in distinct_set:
            continue
        else:
            distinct_set.add(distinct_key)

        if probability_column is not None:
            probability = x[probability_column]
            assert probability >= 0. and probability <= 1., '{} is out of range'.format(probability)
            variance_inc = probability * (1 - probability) * (x[sum_column] ** 2)
            sum_inc = x[sum_column] * probability
        else:
            variance_inc = 0.
            sum_inc = x[sum_column]


        if len(group_by_columns) > 0:
            group_key = group_by_key_fn(tuple(x[col] for col in group_by_columns))
            result[group_key] += sum_inc
            variance[group_key] += variance_inc
        else:
            result += sum_inc
            variance += variance_inc

    if len(group_by_columns) > 0:
        return defaultdict(lambda: (0., 0.), { k: (result[k], variance[k]) for k in result })
    else:
        return result, variance


DUMMY_SUM_COLUMN = 'DUMMY_SUM_COLUMN'


def count_distinct_over_column(df, distinct_columns, **kwargs):
    result = sum_distinct_over_column(
        df.withColumn(DUMMY_SUM_COLUMN, func.lit(1)),
        DUMMY_SUM_COLUMN, distinct_columns, **kwargs
    )
    return result


def annotate_max_identity(faces, identity_threshold=0.1):
    """
    Add a max_identity column to a dataframe derived from face
    """
    face_identities = spark.load('query_faceidentity').alias('face_identity')
    face_identities = face_identities.where(face_identities.probability > identity_threshold)

    # Annotate max identity probabilities
    face_id_to_max_identity = {}
    for face_identity in face_identities.select('face_id', 'identity_id', 'probability').collect():
        update_for_key = False
        if face_identity.face_id in face_id_to_max_identity:
            update_for_key = (face_identity.probability >
                              face_id_to_max_identity[face_identity.face_id][1])
        else:
            update_for_key = True
        if update_for_key:
            face_id_to_max_identity[face_identity.face_id] = (
                face_identity.identity_id,
                face_identity.probability
            )

    def max_identity_helper(face_id):
        if face_id in face_id_to_max_identity:
            return face_id_to_max_identity[face_id][0]
        return NULL_IDENTITY_ID

    def max_identity_probability_helper(face_id):
        if face_id in face_id_to_max_identity:
            return face_id_to_max_identity[face_id][1]
        return 0.

    max_identity_id_udf = func.udf(max_identity_helper, IntegerType())
    faces = faces.withColumn('max_identity_id', max_identity_id_udf('id'))

    max_identity_prob_udf = func.udf(max_identity_probability_helper, DoubleType())
    faces = faces.withColumn('max_identity_probability', max_identity_prob_udf('id'))
    return faces
