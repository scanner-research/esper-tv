from esper.temporal_rangelist import TemporalRange, TemporalRangeList

'''
Convert a dataframe to a collection of temporal rangelists. Returns a dict that
maps from values of the groupby field to temporal rangelists.

For example, if groupby is "video_id", groups the dataframe rows by the
video_id field and returns a dict matching each unique video_id to a temporal
rangelist.

Schema defines how to get start, end, and label for each temporal range from
a single row in the dataframe. In particular, for each row in the dataframe,
creates TemporalRange((row[schema['start']], row[schema['end']],
    row[schema['label']]).
'''
def df_to_trlists(dataframe, groupby="video_id", schema=None):
    if schema is None:
        schema = {
            "start": "min_frame",
            "end": "max_frame",
            "label": "id"
        }
    dfmaterialized = dataframe.collect()
    dictbykey = {}
    for row in dfmaterialized:
        if row[groupby] in dictbykey:
            dictbykey[row[groupby]].append(row)
        else:
            dictbykey[row[groupby]] = [row]
    
    trlists = {}
    for key in dictbykey.keys():
        trlists[key] = TemporalRangeList([
            TemporalRange(row[schema['start']], row[schema['end']],
                row[schema['label']])
            for row in dictbykey[key]])

    return trlists

'''
Gets a result for the esper widget from a dict that maps video IDs to temporal
rangelists. Assumes that the Temporal Ranges store start and end in terms of
frames.
'''
def trlists_to_result(trlists):
    materialized_results = {}
    full_count = 0
    for video in trlists:
        trlist = trlists[video].get_temporal_ranges()
        if len(trlist) == 0:
            continue
        materialized_results[video] = [
            {'track': tr.get_label(), 'min_frame': tr.get_start(),
                'max_frame': tr.get_end(), 'video': video}
            for tr in trlist]
        full_count += 1

    groups = [{
        'type': 'contiguous',
        'label': '',
        'elements': materialized_results[video]
    } for video in sorted(materialized_results.keys())]

    return {'result': groups, 'count': full_count, 'type': 'Video'}

