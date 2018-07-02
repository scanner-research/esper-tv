from esper.stdlib import *
from esper.prelude import *
from esper.spark import *
from esper.validation import *
import pyspark.sql.functions as func
from pyspark.sql.types import BooleanType, IntegerType
from collections import defaultdict


spark = SparkWrapper()


def get_shows():
    return spark.load('query_show').alias('shows')


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
    myudf = func.udf(hour_helper, IntegerType())
    df = df.withColumn(
        'hour', myudf('video_id', 'min_frame')
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
        'videos.year'
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
        'videos.year'
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
    
    myudf = func.udf(in_commercial_helper, BooleanType())
    df = df.withColumn(
        'in_commercial', myudf('video_id', 'min_frame', 'max_frame')
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
    )
    
    speakers = speakers.withColumn(
        'duration', (speakers.max_frame - speakers.min_frame) / speakers.fps
    )
    speakers = _annotate_in_commercial(speakers)
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
    )
    
    segments = segments.withColumn(
        'duration', (segments.max_frame - segments.min_frame) / segments.fps
    )
    segments = _annotate_in_commercial(segments)
    return segments


def get_faces():
    faces = spark.load('query_face').alias('faces')
    
    shots = get_shots().alias('shots')
    faces = faces.join(
        shots, faces.shot_id == shots.id
    ).select(
        'faces.*',
        'shots.show_id', 
        'shots.canonical_show_id',
        'shots.channel_id',
        'shots.duration',
        'shots.in_commercial'
    )
    
    faces = faces.withColumn('height', faces.bbox_y2 - faces.bbox_y1)
    faces = faces.withColumn('width', faces.bbox_x2 - faces.bbox_x1)
    faces = faces.withColumn('area', faces.height * faces.width)
    
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
        'faces.show_id', 
        'faces.canonical_show_id',
        'faces.channel_id',
        'faces.duration',
        'faces.in_commercial'
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
        'faces.show_id', 
        'faces.canonical_show_id',
        'faces.channel_id',
        'faces.duration',
        'faces.in_commercial'
    )
    
    return face_identities