from esper.temporal_rangelist import TemporalRange, TemporalRangeList
from esper.prelude import collect
from operator import itemgetter, attrgetter
from query.models import Video

'''
Convert an iterable collection of rows to a collection of temporal rangelists.
Returns a dict that maps from values of the groupby field to temporal
rangelists.

@array is a list of rows of data, and @accessor takes in a row and a field name
and returns the value. For example, accessor(row, 'id').

For example, if groupby is "video_id", groups the dataframe rows by the
video_id field and returns a dict matching each unique video_id to a temporal
rangelist.

Schema defines how to get start, end, and payload for each temporal range from
a single row in the dataframe. In particular, for each row in the dataframe,
creates TemporalRange(accessor(row, schema['start']),
                accessor(row, schema['end']),
                accessor(row, schema['payload']))
'''
def iterable_to_trlists(iterable, accessor, groupby="video_id", schema=None):
    if schema is None:
        schema = {
            "start": "min_frame",
            "end": "max_frame",
            "payload": "id"
        }
    dictbykey = {}
    for row in iterable:
        if accessor(row, groupby) in dictbykey:
            dictbykey[accessor(row, groupby)].append(row)
        else:
            dictbykey[accessor(row, groupby)] = [row]
    
    trlists = {}
    for key in dictbykey.keys():
        trlists[key] = TemporalRangeList([
            TemporalRange(accessor(row, schema['start']),
                accessor(row, schema['end']),
                accessor(row, schema['payload']))
            for row in dictbykey[key]])

    return trlists

'''
Converts a Spark dataframe to a collection of temporal rangelists.
'''
def df_to_trlists(dataframe, groupby="video_id", schema=None):
    dfmaterialized = dataframe.collect()

    def row_accessor(row, field):
        return row[field]

    return iterable_to_trlists(dfmaterialized, row_accessor, groupby, schema)

'''
Converts a Django queryset to a collection of temporal rangelists.
'''
def qs_to_trlists(qs, groupby="video_id", schema=None):
    def row_accessor(row, field):
        return attrgetter(field)(row)

    return iterable_to_trlists(qs, row_accessor, groupby, schema)

'''
Gets a result for the esper widget from a dict that maps video IDs to temporal
rangelists. Assumes that the Temporal Ranges store start and end in terms of
frames.
'''
def trlists_to_result(trlists, color="red"):
    materialized_results = {}
    full_count = 0
    for video in trlists:
        trlist = trlists[video].get_temporal_ranges()
        if len(trlist) == 0:
            continue
        materialized_results[video] = [
            {'track': tr.get_payload(), 'min_frame': tr.get_start(),
                'max_frame': tr.get_end(), 'video': video}
            for tr in trlist]
        full_count += 1
    videos = collect(Video.objects.filter(id__in=trlists.keys()).all(),
            attrgetter('id'))

    groups = [{
        'type': 'contiguous',
        'label': video,
        'num_frames': videos[video][0].num_frames,
        'elements': [{
            'video': video,
            'segments': sorted(materialized_results[video], 
                key=itemgetter('min_frame')),
            'color': color
        }]
    } for video in sorted(materialized_results.keys())]

    return {'result': groups, 'count': full_count, 'type': 'Video'}

''' Gets a result for trlists, assuming that the objects are bounding boxes. '''
def trlists_to_result_bbox(trlists):
    materialized_results = []
    for video in trlists:
        trlist = trlists[video].get_temporal_ranges()
        if len(trlist) == 0:
            continue
        for tr in trlist:
            materialized_results.append({
                'video': video,
                'min_frame': (tr.get_start() + tr.get_end()) / 2,
                'objects': [{
                        'id': video,
                        'type': 'bbox',
                        'bbox_x1': bbox['x1'],
                        'bbox_x2': bbox['x2'],
                        'bbox_y1': bbox['y1'],
                        'bbox_y2': bbox['y2'],
                    } for bbox in tr.get_payload()['objects']]
                })

    groups = [{'type': 'flat', 'label': '', 'elements': [r]}
            for r in materialized_results]

    return {'result': groups, 'count': len(list(trlists.keys())), 'type': 'Video'}

'''
Add trlists to result as another set of segments to display. Modifies result.
'''
def add_trlists_to_result(result, trlists, color="red"):
    # Get a base group to copy for new videos
    base_group = result['result'][0]

    # Put trlists into a good format
    materialized_results = {}
    full_count = 0
    for video in trlists:
        trlist = trlists[video].get_temporal_ranges()
        if len(trlist) == 0:
            continue
        materialized_results[video] = [
            {'track': tr.get_payload(), 'min_frame': tr.get_start(),
                'max_frame': tr.get_end(), 'video': video}
            for tr in trlist]
        full_count += 1
    videos = collect(Video.objects.filter(id__in=materialized_results.keys()).all(),
            attrgetter('id'))

    for video in videos.keys():
        matching_group = None
        new_segments = {
            'video': video,
            'segments': sorted(materialized_results[video],
                key=itemgetter('min_frame')),
            'color': color
        }
        for group in result['result']:
            if group['label'] == video:
                matching_group = group
                break
        if matching_group is None:
            new_elements = []
            for element in base_group['elements']:
                new_element = {
                    'video': video,
                    'segments': [],
                    'color': element['color']
                }
                new_elements.append(new_element)
            new_elements.append(new_segments)
            result['result'].append({
                'type': 'contiguous',
                'label': video,
                'num_frames': videos[video][0].num_frames,
                'elements': new_elements
            })
            result['count'] += 1
        else:
            group['elements'].append(new_segments)

    # add in empty segment lists for videos in results that don't appear in
    # trlists
    for group in result['result']:
        if group['label'] not in videos.keys():
            group['elements'].append({
                'video': group['label'],
                'segments': [],
                'color': color
            })

