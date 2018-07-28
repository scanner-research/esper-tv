from esper.stdlib import *
from esper.prelude import *
from esper.spark import *
from esper.validation import *
import pyspark.sql.functions as func
from pyspark.sql.types import BooleanType, IntegerType, StringType, DoubleType
from collections import defaultdict, Counter
import datetime
import calendar


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


def _annotate_host_probability(faces, identity_threshold=0.3):
    face_identities = spark.load('query_faceidentity').alias('face_identity')
    face_identities = face_identities.where(face_identities.probability > identity_threshold)
    
    faces2 = get_faces(annotate_host_probability=False).alias('faces2')
    faces2 = faces2.where(faces2.in_commercial == False)
    
    face_identities = face_identities.join(
        faces2, face_identities.face_id == faces2.id
    ).select(
        'face_identity.face_id',
        'face_identity.identity_id',
        'face_identity.labeler_id',
        'face_identity.probability',
        'faces2.show_id', 
        'faces2.canonical_show_id',
        'faces2.channel_id'
    )
    
    show_id_to_host_ids = defaultdict(set)
    show_hosts = spark.load('query_show_hosts')
    for e in show_hosts.collect():
        show_id_to_host_ids[e.show_id].add(e.thing_id)
        
    def is_host_helper(identity_id, show_id):
        return identity_id in show_id_to_host_ids[show_id]
    
    host_filter_udf = func.udf(is_host_helper, BooleanType())
    host_identities = face_identities.filter(host_filter_udf('identity_id', 'show_id'))
    
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
    

def get_faces(annotate_host_probability=True):
    faces = spark.load('query_face').alias('faces')
    
    shots = get_shots().alias('shots')
    faces = faces.join(
        shots, faces.shot_id == shots.id
    ).select(
        'faces.*',
        'shots.show_id',
        'shots.video_id',
        'shots.canonical_show_id',
        'shots.channel_id',
        'shots.min_frame',
        'shots.max_frame',
        'shots.duration',
        'shots.in_commercial',
        'shots.hour',
        'shots.week_day',
        'shots.time',
        'shots.fps'
    )
    
    faces = faces.withColumn('height', faces.bbox_y2 - faces.bbox_y1)
    faces = faces.withColumn('width', faces.bbox_x2 - faces.bbox_x1)
    faces = faces.withColumn('area', faces.height * faces.width)
    
    if annotate_host_probability:
        faces = _annotate_host_probability(faces)
    
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


def get_face_genders():
    face_genders = spark.load('query_facegender').alias('face_genders')
    
    faces = get_faces().alias('faces')
    face_genders = face_genders.join(
        faces, face_genders.face_id == faces.id
    ).select(
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
        'faces.host_probability'
    )
    
    face_genders = _annotate_size_percentile(face_genders)
    return face_genders


def get_face_identities():
    face_identities = spark.load('query_faceidentity').alias('face_identities')
    
    faces = get_faces().alias('faces')
    face_identities = face_identities.join(
        faces, face_identities.face_id == faces.id
    ).select(
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
        'faces.host_probability'
    )
    
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


def sum_distinct_over_column(df, sum_column, distinct_columns, group_by_columns=[], 
                             group_by_key_fn=lambda x: x, probability_column=None):
    """
    Sum a column over distinct values 
    (this is inefficient, but Spark does not have an easy way to do it...)
    
    sum_column: column name
    distinct_columns & group_by_columns: list of column names
    group_by_key_fn: a custom function for group by applied to the group by columns
    
    returns float or dict from group_by columns to float
    """
    
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
            
        variance_inc = (x[probability_column] * (1 - x[probability_column]) * (x[sum_column] ** 2)
                        if probability_column is not None else 0.)
        sum_inc = x[sum_column] * x[probability_column] if probability_column is not None else x[sum_column]
        
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


def count_distinct_over_column(df, distinct_columns, group_by_columns=[], 
                               group_by_key_fn=lambda x: x):
    result = sum_distinct_over_column(
        df.withColumn(DUMMY_SUM_COLUMN, func.lit(1)),
        DUMMY_SUM_COLUMN,
        distinct_columns=distinct_columns,
        group_by_columns=group_by_columns,
        group_by_key_fn=group_by_key_fn
    )
    if isinstance(result, float):
        return int(result)
    else:
        return { k : int(v) for k, v in result.items() }
        