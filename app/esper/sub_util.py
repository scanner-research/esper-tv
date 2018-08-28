import os
import pysrt
from pathlib import Path

from esper.prelude import par_for
from query.models import Video


RAW_SUB_DIR = '/app/data/subs/orig'


def _get_video_name_from_sub(s):
    return Path(Path(s).stem).stem


VIDEO_NAME_TO_SUB_PATHS = {
    _get_video_name_from_sub(s) : os.path.join(RAW_SUB_DIR, s) 
    for s in os.listdir(RAW_SUB_DIR)
}


def _search_sub_file(video_path, intervals):
    try:
        subs = pysrt.open(video_path)
    except:
        try:
            subs = pysrt.open(video_path, encoding='iso-8859-1')
        except:
            return None
    
    def _time_to_int(t):
        return t.hour * 3600 + t.minute * 60 + t.second
    
    def _has_overlap(interval, sub_line):
        start = max(interval[0], _time_to_int(sub_line.start.to_time()))
        end = min(interval[1], _time_to_int(sub_line.end.to_time()))
        return end - start > 0 
    
    result = {}
    for interval in intervals:
        segments = []
        for sub_line in subs:
            if _has_overlap(interval, sub_line):
                segments.append(sub_line.text)
            else:
                if len(segments) > 0:
                    break
        result[interval] = ' '.join(segments)
    return result


def get_raw_subs(video_id_to_intervals):
    '''
    Extract raw subtitles for video intervals
    
    Args:
        video_id_to_intervals: { 
            video_id: [(start1, end1), ...], ...
        }
    
    Returns:
        { 
            video_id: { (start1, end1) : String, ... }, ...
        }
    # TODO: this is really slow at the moment
    '''
    video_ids_and_names = [
        (v.id, Path(v.path).stem) for v in 
        Video.objects.filter(id__in=list(video_id_to_intervals.keys())).order_by('path')
    ]
    
    def search_single_video(args):
        video_id, video_name = args
        if video_name in VIDEO_NAME_TO_SUB_PATHS:
            return _search_sub_file(
                VIDEO_NAME_TO_SUB_PATHS[video_name], 
                video_id_to_intervals[video_id]
            )
        else:
            return None
        
    result = {}
    for x, res in zip(
        video_ids_and_names,
        par_for(search_single_video, video_ids_and_names, progress=False)
    ):
        if res is not None:
            result[x[0]] = res
    return result
    