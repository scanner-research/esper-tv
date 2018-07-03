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
        'videos.week_day'
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
        'videos.week_day'
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
        'videos.week_day'
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
        'videos.week_day'
    )
    
    segments = segments.withColumn(
        'duration', (segments.max_frame - segments.min_frame) / segments.fps
    )
    segments = _annotate_in_commercial(segments)
    return segments


def _annotate_host_probability(faces, threshold=0.3):
    face_identities = spark.load('query_faceidentity').alias('face_identity')
    face_identities = face_identities.where(face_identities.probability > threshold)
    
    faces = get_faces(annotate_host_probability=False).alias('faces')
    faces = faces.where(faces.in_commercial == False)
    
    face_identities = face_identities.join(
        faces, face_identities.face_id == faces.id
    ).select(
        'face_identity.face_id',
        'face_identity.identity_id',
        'face_identity.labeler_id',
        'face_identity.probability',
        'faces.show_id', 
        'faces.canonical_show_id',
        'faces.channel_id',
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
        return face_id_to_host_prob[face_id]
    
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
        'shots.duration',
        'shots.in_commercial',
        'shots.hour',
        'shots.week_day'
    )
    
    faces = faces.withColumn('height', faces.bbox_y2 - faces.bbox_y1)
    faces = faces.withColumn('width', faces.bbox_x2 - faces.bbox_x1)
    faces = faces.withColumn('area', faces.height * faces.width)
    
    if annotate_host_probability:
        faces = _annotate_host_probability(faces)
    
    return faces
    

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
        'faces.in_commercial',
        'faces.hour',
        'faces.week_day',
        'faces.is_host',
        'faces.host_probability'
    )
    
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
        'faces.in_commercial',
        'faces.hour',
        'faces.week_day',
        'faces.is_host',
        'faces.host_probability'
    )
    
    return face_identities