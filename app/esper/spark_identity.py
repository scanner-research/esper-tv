from esper.stdlib import *
from esper.prelude import *
from query.models import *
from esper.identity import major_canonical_shows

import pyspark.sql.functions as func
from pyspark.sql.types import BooleanType, IntegerType, StringType, DoubleType

from datetime import timedelta


def get_screen_time_with_spark(name, group_by_column, face_identities_df, 
                               resolve_id_to_name=True,
                               date_range=None):
    """
    Returns a dict from the group by key to screentime in a timedelta.
    
    Similar to:
        get_screen_time_by_show in identity.py when using canonical_show_id
        get_screen_time_by_video when using video_id # TODO: the django code doesn't 
                                                     # compute variance for this case yet
    """
    
    if date_range is not None:
        face_identities_df = face_identities_df.where(
            (face_identities_df.time >= func.to_date(func.lit(date_range[0]))) & 
            (face_identities_df.time < func.to_date(func.lit(date_range[1])))
        )
    
    thing_id = Thing.objects.get(name=name).id
    face_identities_df = face_identities_df.where(
        face_identities_df.identity_id == thing_id
    )
    
    # Remove duplicate identity labels on the same faces using max
    face_id_to_max_probability = {}
    for face_identity in face_identities_df.select('id', 'face_id', 'probability').collect():
        if face_identity.face_id in face_id_to_max_probability:
            is_new_max = face_identity.probability > face_id_to_max_probability[face_identity.face_id][1]
        else:
            is_new_max = True
        if is_new_max:
            face_id_to_max_probability[face_identity.face_id] = (
                face_identity.id, face_identity.probability
            )
    face_identity_id_set = set([x for x, _ in face_id_to_max_probability.values()])
    def filter_duplicate_helper(face_identity_id):
        return face_identity_id in face_identity_id_set
    my_filter_udf = func.udf(filter_duplicate_helper, BooleanType())
    face_identities_df = face_identities_df.filter(my_filter_udf('id'))
    
    face_identities_df = face_identities_df.withColumn(
        'exp_duration',
        face_identities_df.duration * face_identities_df.probability
    )
    face_identities_df = face_identities_df.withColumn(
        'var_duration',
        (1. - face_identities_df.probability) * face_identities_df.probability 
        * face_identities_df.duration * face_identities_df.duration
    )
    
    key_map_func = lambda x: x
    if resolve_id_to_name:
        if group_by_column == 'show_id':
            show_id_to_name = { x.id : x.name for x in Show.objects.all() }
            key_map_func = lambda x: show_id_to_name[x]
            
        elif group_by_column == 'canonical_show_id':
            canonical_show_id_to_name = { x.id : x.name for x in CanonicalShow.objects.all() }
            key_map_func = lambda x: canonical_show_id_to_name[x]
            
        elif group_by_column == 'channel_id':
            channel_id_to_name = { x.id : x.name for x in Channel.objects.all() }
            key_map_func = lambda x: channel_id_to_name[x]
            
    results = {}
    for row in face_identities_df.groupby(group_by_column).agg({
                    'exp_duration': 'sum',
                    'var_duration': 'sum',
               }).collect():
        results[key_map_func(row[group_by_column])] = (
            timedelta(seconds=row['sum(exp_duration)']), 
            row['sum(var_duration)']
        )
    return results


def get_screen_time_by_canonical_show_spark(name, face_identities_df, date_range=None):
    return {
        k : v for k, v in get_screen_time_with_spark(
            name, 'canonical_show_id', face_identities_df,
            resolve_id_to_name=True, date_range=date_range
        ).items() if k in major_canonical_shows
    }


def get_screen_time_by_video_spark(name, face_identities_df, date_range=None):
    return get_screen_time_with_spark(name, 'video_id', face_identities_df, 
                                      date_range=date_range)


def get_person_in_shot_similarity_spark(names, face_identities_df, 
                                        date_range=None, precision_thresh=0.8):
    """
    Returns a dict mapping pairs of (p1,p2) to a tuple of jaccard, (p1 & p2 | p1), (p1 & p2 | p2) 
    """
    if date_range is not None:
        face_identities_df = face_identities_df.where(
            (face_identities_df.time >= func.to_date(func.lit(date_range[0]))) & 
            (face_identities_df.time < func.to_date(func.lit(date_range[1])))
        )
    
    shot_ids_by_name = {}
    for name in names:
        shot_ids_by_name[name] = {
            x.shot_id for x in face_identities_df.where(
                (face_identities_df.identity_id == Thing.objects.get(name=name).id) & 
                (face_identities_df.probability >= precision_thresh)
            ).select('shot_id').collect()
        }
    
    sims = {}
    for p1, v1 in shot_ids_by_name.items():
        for p2, v2 in shot_ids_by_name.items():
            if p2 >= p1:
                continue
            intersection = len(v1 & v2)
            sims[(p1, p2)] = (
                intersection / len(v1 | v2), 
                intersection / len(v1), 
                intersection / len(v2)
            )
    return sims
