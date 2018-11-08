from operator import itemgetter, attrgetter
from query.models import Video
from esper.prelude import collect
import sys

sys.path.append('/app/deps/rekall')

from rekall.interval_list import Interval, IntervalList

def iterable_to_intrvllists(iterable, accessor, groupby="video_id", schema=None):
    """
    Convert an iterable collection of rows to a collection of intervallists.
    Returns a dict that maps from values of the groupby field to temporal
    rangelists.

    @array is a list of rows of data, and @accessor takes in a row and a field name
    and returns the value. For example, accessor(row, 'id').

    For example, if groupby is "video_id", groups the dataframe rows by the
    video_id field and returns a dict matching each unique video_id to a temporal
    rangelist.

    Schema defines how to get start, end, and payload for each interval from
    a single row in the dataframe. In particular, for each row in the dataframe,
    creates Interval(accessor(row, schema['start']),
                    accessor(row, schema['end']),
                    accessor(row, schema['payload']))
    """
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
    
    intrvllists = {}
    for key in dictbykey.keys():
        intrvllists[key] = IntervalList([
            Interval(accessor(row, schema['start']),
                accessor(row, schema['end']),
                accessor(row, schema['payload']))
            for row in dictbykey[key]])

    return intrvllists

def df_to_intrvllists(dataframe, groupby="video_id", schema=None):
    """ Converts a Spark dataframe to a collection of intervallists.
    """
    dfmaterialized = dataframe.collect()

    def row_accessor(row, field):
        return row[field]

    return iterable_to_intrvllists(dfmaterialized, row_accessor, groupby, schema)

def qs_to_intrvllists(qs, groupby="video_id", schema=None):
    """ Converts a Django queryset to a collection of intervallists.
    """
    def row_accessor(row, field):
        return attrgetter(field)(row)

    return iterable_to_intrvllists(qs, row_accessor, groupby, schema)

def topic_search_to_intrvllists(topic_search_result, video_ids=None, payload=0):
    """
    Converts a topic search result from esper.captions to IntervalLists.

    @topic_search_result is just the output from captions#topic_search.

    Returns a dict from video IDs to IntervalLists.
    """
    if video_ids == None:
        videos = {v.id: v for v in Video.objects.all()}
    else:
        videos = {v.id: v for v in Video.objects.filter(id__in=video_ids).all()}

    def convert_time(k, t):
        return int(t * videos[k].fps)

    segments_by_video = {}
    flattened = [
        (v.id, convert_time(v.id, l.start), convert_time(v.id, l.end))
        for v in topic_search_result.documents if v.id in videos
        for l in v.locations
    ]

    for video_id, t1, t2 in flattened:
        if video_id in segments_by_video:
            segments_by_video[video_id].append((t1, t2, payload))
        else:
            segments_by_video[video_id] = [(t1, t2, payload)]

    for video in segments_by_video:
        segments_by_video[video] = IntervalList(segments_by_video[video])

    return segments_by_video

def caption_scan_to_intrvllists(scan_result, search_terms, video_ids=None,
        dilation=0, payload=0):
    """
    Converts an ngram scan result from esper.captions to IntervalLists.

    @scan_result is an array of pairs of (video_id, video_result). video_result
    is in turn an array whose i-th item is an array of results for
    search_terms[i]. Each array of results is an array of (start, end) tuples.

    This is just the result returned by
    scan_for_ngrams_in_parallel(search_terms, video_ids).

    Returns an array of dicts. The ith member of this array is a dict mapping
    from video IDs to intervals for search_terms[i].
    """
    search_terms_intrvllists = [{} for term in search_terms]
    if video_ids == None:
        videos = {v.id: v for v in Video.objects.all()}
    else:
        videos = {v.id: v for v in Video.objects.filter(id__in=video_ids).all()}

    def convert_time(k, t):
        return int(t * videos[k].fps)

    for video_id, result in scan_result:
        if result == []:
            continue
        for i, term in enumerate(search_terms):
            term_result = result[i]
            interval_list = IntervalList([
                (convert_time(video_id, start - dilation),
                    convert_time(video_id, end + dilation),
                    payload)
                for start, end in term_result
            ])

            if interval_list.size() > 0:
                search_terms_intrvllists[i][video_id] = interval_list

    return search_terms_intrvllists

def intrvllists_to_result(intrvllists, color="red", video_order=None):
    """
    Gets a result for the esper widget from a dict that maps video IDs to temporal
    rangelists. Assumes that the Temporal Ranges store start and end in terms of
    frames.

    video_order is an optional list of video IDs to order the videos.
    """
    materialized_results = {}
    keys = []
    full_count = 0
    for video in intrvllists:
        intrvllist = intrvllists[video].get_intervals()
        if len(intrvllist) == 0:
            continue
        materialized_results[video] = [
            {'track': intrvl.get_payload(), 'min_frame': intrvl.get_start(),
                'max_frame': intrvl.get_end(), 'video': video}
            for intrvl in intrvllist]
        keys.append(video)
        full_count += 1
    videos = collect(Video.objects.filter(id__in=intrvllists.keys()).all(),
            attrgetter('id'))
    if video_order is not None:
        keys = video_order
    else:
        keys = sorted(materialized_results.keys())

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
    } for video in keys]

    return {'result': groups, 'count': full_count, 'type': 'Video'}

def intrvllists_to_result_bbox(intrvllists):
    """ Gets a result for intrvllists, assuming that the objects are bounding boxes.
    """
    materialized_results = []
    for video in intrvllists:
        intrvllist = intrvllists[video].get_intervals()
        if len(intrvllist) == 0:
            continue
        for intrvl in intrvllist:
            materialized_results.append({
                'video': video,
                'min_frame': (intrvl.get_start() + intrvl.get_end()) / 2,
                'objects': [{
                        'id': video,
                        'type': 'bbox',
                        'bbox_x1': bbox['x1'],
                        'bbox_x2': bbox['x2'],
                        'bbox_y1': bbox['y1'],
                        'bbox_y2': bbox['y2'],
                    } for bbox in intrvl.get_payload()['objects']]
                })

    groups = [{'type': 'flat', 'label': '', 'elements': [r]}
            for r in materialized_results]

    return {'result': groups, 'count': len(list(intrvllists.keys())), 'type': 'Video'}

def add_intrvllists_to_result(result, intrvllists, color="red"):
    """ Add intrvllists to result as another set of segments to display. Modifies result.
    """
    # Get a base group to copy for new videos
    base_group = result['result'][0]

    # Put intrvllists into a good format
    materialized_results = {}
    full_count = 0
    for video in intrvllists:
        intrvllist = intrvllists[video].get_intervals()
        if len(intrvllist) == 0:
            continue
        materialized_results[video] = [
            {'track': intrvl.get_payload(), 'min_frame': intrvl.get_start(),
                'max_frame': intrvl.get_end(), 'video': video}
            for intrvl in intrvllist]
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
    # intrvllists
    for group in result['result']:
        if group['label'] not in videos.keys():
            group['elements'].append({
                'video': group['label'],
                'segments': [],
                'color': color
            })

    return

