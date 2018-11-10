import esper.rekall
from rekall.interval_list import IntervalList
from rekall.temporal_predicates import not_pred, overlaps, or_pred, equal, before, after

"""
All thresholds 
"""
TRANSCRIPT_DELAY = 6
MIN_TRANSCRIPT = 0.3

MIN_BLACKFRAME = 0.99
MIN_BLACKWINDOW = 1

MIN_BLANKWINDOW = 30
MAX_BLANKWINDOW = 270

MIN_LOWERTEXT = 0.5
MIN_LOWERWINDOW = 15
MAX_LOWERWINDOW_GAP = 60

MIN_COMMERCIAL_TIME = 10
MAX_COMMERCIAL_TIME = 270

MAX_MERGE_DURATION = 300
MAX_MERGE_GAP = 30
MIN_COMMERCIAL_GAP = 10
MAX_COMMERCIAL_GAP = 90

MIN_COMMERCIAL_TIME_FINAL = 30
MAX_ISOLATED_BLANK_TIME = 90

def fid2second(fid, fps):
    second = 1. * fid / fps
    return second

def get_blackframe_list(histogram, video_desp):
    """
    Get all black frames by checking the histogram list 
    """
    pixel_sum = video_desp['frame_w'] * video_desp['frame_h']
    thresh = MIN_BLACKFRAME * pixel_sum
    blackframe_list = []
    for fid, hist in enumerate(histogram):
        if hist[0][0] > thresh and hist[0][1] > thresh and hist[0][2] > thresh:
            blackframe_list.append(fid)
    return IntervalList([
        (fid2second(fid, video_desp['fps']),
        fid2second(fid + 1, video_desp['fps']),
        0) for fid in blackframe_list])

def get_text_intervals(word, transcript):
    return IntervalList([
        (start_sec - TRANSCRIPT_DELAY, end_sec - TRANSCRIPT_DELAY, 0)
        for text, start_sec, end_sec in transcript
        if word in text
    ]).coalesce()

def get_lowercase_intervals(transcript):
    def is_lower_text(text):
        lower = [c for c in text if c.islower()]
        alpha = [c for c in text if c.isalpha()]
        if len(alpha) == 0:
            return False
        if 1. * len(lower) / len(alpha) > MIN_LOWERTEXT:
            return True
        else:
            return False

    return IntervalList([
        (start_sec, end_sec, 0)
        for text, start_sec, end_sec in trascript
        if is_lower_text(text)]) \
            .dilate(MAX_LOWERWINDOW_GAP / 2) \
            .coalesce() \
            .dilate(-1 * MAX_LOWERWINDOW_GAP / 2) \
            .filter_length(min_length=MIN_LOWER_WINDOW)

def detect_commercial(video_desp, histogram, transcript):
    """
    API for detecting commercial blocks from TV news video
    Input:  video_desp (dict of fps, video_length, video_frames, frame_w, frame_h); 
            histogram (list of histogram 16x3 bin for each frame);  
            transcript (list of tuple(text, start_sec, end_sec));
    Return: commercial_list (list of tuple((start_fid, start_sec), (end_fid, end_sec)), None if failed)
            error_str (error message if failed, otherwise "")
    """
    blackframe_list = get_blackframe_list(histogram)
    black_windows = blackframe_list \
            .dilate(1. / video_desp['fps']) \
            .coalesce() \
            .dilate(-1. / video_desp['fps']) \
            .filter(min_length=MIN_BLACKWINDOW * 1. / video_desp.fps)

    # get all instances of >>, Announcer:, and  >> Announcer: in transcript
    arrow_text = get_text_intervals(">>", transcript)
    announcer_text = get_text_intervals("Announcer:", transcript)
    arrow_announcer_text = get_text_intervals(">> Announcer:", tarnscript)
    
    # get an interval for the whole video
    whole_video = IntervalList([(0., video_desp['video_length'], 0)])

    # whole video minus black windows to get segments in between black windows
    # then filter out anything that overlaps with ">>" as long as it's not
    #   ">> Announcer:"
    # then coalesce, as long as it doesn't get too long
    def fold_fn(stack, interval):
        if len(stack) == 0:
            stack.append(interval)
        else:
            last = stack.pop()
            if or_pred(overlaps(), after(max_dist=.1)(interval, last))(interval, last):
                if last.union(interval).length() > MAX_COMMERCIAL_TIME:
                    if last.length() > MAX_COMMERCIAL_TIME:
                        stack.append(Interval(
                            last.start, 
                            last.start + MAX_COMMERCIAL_TIME, 
                            last.payload))
                    else:
                        stack.append(last)
                    stack.append(interval)
                else:
                    stack.append(last.union(interval))
            else:
                stack.append(interval)
    commercials = whole_video \
            .minus(black_windows) \
            .filter_against(
                arrow_text.filter_against(arrow_announcer_text,
                    predicate=not_pred(overlaps())),
                predicate=not_pred(overlaps())
            ) \
            .set_union(black_windows) \
            .fold_list(fold_fn, []) \
            .filter_length(min_length = MIN_COMMERCIAL_TIME)
    
    # add in lowercase intervals
    lowercase_intervals = get_lowercase_intervals(transcript)
    commercials = commercials \
            .set_union(lowercase_intervals) \
            .dilate(MIN_COMMERCIAL_GAP / 2) \
            .coalesce() \
            .dilate(MIN_COMMERCIAL_GAP / 2)

    # get blank intervals
    blank_intervals = whole_video.minus(IntervalList([
        (start_sec, end_sec - TRANSCRIPT_DELAY, 0)
        for text, start_sec, end_sec in transcript
    ])).coalesce().filter_length(
            min_length=MIN_BLANKWINDOW, max_length=MAX_BLANKWINDOW)

    # add in blank intervals, but only if adding in the new intervals doesn't
    #   get too long
    commercials = commercials.merge(blank_intervals,
            predicate=or_pred(before(max_dist=MAX_MERGE_GAP),
                after(max_dist=MAX_MERGE_GAP))
            ) \
            .filter_length(max_length=MAX_MERGE_DURATION) \
            .set_union(commercials) \
            .dilate(MIN_COMMERCIAL_GAP / 2) \
            .coalesce() \
            .dilate(MIN_COMMERCIAL_GAP / 2)

    # post-process commercials to get rid of gaps, small commercials, and
    #   islated blocks
    small_gaps = whole_video \
            .minus(commercials) \
            .filter_length(max_length = MAX_COMMERCIAL_GAP) \
            .filter_against(
                    arrow_text.filter_against(
                        announcer_text,
                        predicate=not_pred(overlaps())
                    ), predicate=not_pred(overlaps()))

    # merge with small gaps, but only if that doesn't make things too long
    commercials = commercials \
            .set_union(small_gaps.dilate(0.1)) \
            .coalesce() \
            .filter_length(max_length=MAX_COMMERCIAL_TIME) \
            .set_union(commercials) \
            .coalesce()

    # get isolated commercials
    not_isolated_commercials = commercials.filter_against(commercials,
            predicate=or_pred(before(max_dist=MAX_COMMERCIAL_TIME),
                after(max_dist=MAX_COMMERCIAL_TIME)))
    isolated_commercials = commercials.minus(not_isolated_commercials)
    commercials_to_delete = isolated_commercials \
            .filter_length(max_length=MIN_COMMERCIAL_TIME_FINAL) \
            .set_union(isolated_commercials \
                .filter_against(blank_intervals, predicate=equals()) \
                .filter_length(max_length=MAX_ISOLATED_BLANK_TIME))

    commercials = commercials.minus(commercials_to_delete)

    return commercials

