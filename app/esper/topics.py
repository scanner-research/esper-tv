from esper.prelude import *
from esper.stdlib import *
from esper.major_canonical_shows import *
from esper.captions import *
from esper.plot_util import *
from query.models import *

import calendar
from datetime import datetime, timedelta
from matplotlib import pyplot as plt
from collections import defaultdict
from pandas import DataFrame


def show_segments(segments):
    return esper_widget({
        'result': [{
            'type': 'flat',
            'elements': [{
                'video': video_id,
                'min_time': start,
                'max_time': end
            }]
        } for video_id, path, (start, end), count, _ in segments]
    })


def get_total_segment_length(segments):
    """Sum up the segment lengths"""
    total_segment_len = 0.
    for _, _, (start, end), _, _ in segments:
        assert end >= start
        total_segment_len += end - start
    return timedelta(seconds=total_segment_len)


def check_for_double_counting(segments):
    video_id_to_path = {}
    for video_id, path, _, _, _ in segments:
        if video_id in video_id_to_path and video_id_to_path[video_id] != path:
            raise Exception('Video {} has more than one transcript ({}, {})'.format(
                            video_id, video_id_to_path[video_id], path))
            

def plot_total_segment_length_vs_window_size(lexicon, window_sizes, threshold=50):
    """Parameter searching code"""
    window_sizes.sort()
    total_segment_lengths = []
    for window_size in window_sizes:
        segments = find_segments(lexicon, window_size=window_size, threshold=threshold, merge_overlaps=True)
        total_segment_lengths.append(get_total_segment_length(segments).total_seconds() / 60 / 60)
        
    plt.scatter(window_sizes, total_segment_lengths, color='Blue')
    plt.title('Total segment length for "{}" vs window size (threshold: {})'.format(topic, threshold))
    plt.xlabel('Window size in tokens')
    plt.ylabel('Coverage in hours')
    plt.show()
    
    
def plot_total_segment_length_vs_threshold(lexicon, thresholds, window_size=100):
    """Parameter searching code"""
    thresholds.sort()
    total_segment_lengths = []
    for threshold in thresholds:
        segments = find_segments(lexicon, window_size=window_size, threshold=threshold, merge_overlaps=True)
        total_segment_lengths.append(get_total_segment_length(segments).total_seconds() / 60 / 60)
        
    plt.scatter(thresholds, total_segment_lengths, color='Blue')
    plt.title('Total segment length for "{}" vs threshold (window size: {})'.format(topic, window_size))
    plt.xlabel('Threshold')
    plt.ylabel('Coverage in hours')
    plt.show()
    
    
def get_overlap_between_topics(topic_to_segments):
    
    def get_video_id_to_segments(segs):
        video_id_to_segments = defaultdict(list)
        for video_id, _, interval, _, _ in segs:
            video_id_to_segments[video_id].append(interval)
        for v in video_id_to_segments.values():
            v.sort()
        return video_id_to_segments
    
    def compute_overlap(segs1, segs2):
        video_ids_to_intervals1 = get_video_id_to_segments(segs1)
        video_ids_to_intervals2 = get_video_id_to_segments(segs2)
        
        overlap_seconds = 0.
        for video_id in video_ids_to_intervals1:
            intervals1 = video_ids_to_intervals1[video_id]
            intervals2 = video_ids_to_intervals2[video_id]
            
            while True:
                if len(intervals1) == 0 or len(intervals2) == 0:
                    break
                
                i1_start, i1_end = intervals1[0]
                i2_start, i2_end = intervals2[0]
                if i1_start < i2_start:
                    if i1_end < i2_start:
                        del intervals1[0]
                    else:
                        if i1_end < i2_end:
                            overlap_seconds += i1_end - i2_start
                            del intervals1[0]
                        else:
                            overlap_seconds += i2_end - i2_start
                            del intervals2[0]
                else:
                    if i2_end < i1_start:
                        del intervals2[0]
                    else:
                        if i2_end < i1_end:
                            overlap_seconds += i2_end - i1_start
                            del intervals2[0]
                        else:
                            overlap_seconds += i1_end - i1_start
                            del intervals1[0]
                    
        return timedelta(seconds=overlap_seconds)
    
    results = []
    for t1 in topic_to_segments:
        for t2 in topic_to_segments:
            if t1 <= t2:
                continue
                
            t1_secs = get_total_segment_length(topic_to_segments[t1]).total_seconds()
            t2_secs = get_total_segment_length(topic_to_segments[t2]).total_seconds()
            t1_and_t2_secs = compute_overlap(topic_to_segments[t1], topic_to_segments[t2]).total_seconds()
            
            seconds_in_hour = 60 * 60
            results.append((
                t1, 
                t2, 
                t1_secs / seconds_in_hour,
                t2_secs / seconds_in_hour,
                t1_and_t2_secs / seconds_in_hour, 
                t1_and_t2_secs / (t1_secs + 1e-9), 
                t1_and_t2_secs / (t2_secs + 1e-9)
            ))
            
    return DataFrame(results, columns=[
        'Topic 1', 'Topic 2', 'T1 (hrs)', 'T2 (hrs)', 'Overlap (hrs)', '(T1&T2)|T1', '(T1&T2)|T2'
    ])


def get_caption_mentions_by_show(phrases, show_count=False):
    result = topic_search(phrases, dilate=0)
    result = {d.id: len([l for l in d.locations]) for d in result.documents}
    show_to_mentions = defaultdict(int)
    
    if show_count:
        video_count_by_show = {
            x['show__canonical_show__name'] : x['count'] for x in
            Video.objects.filter(id__in=result.keys()).values(
                'show__canonical_show'
            ).annotate(
                count=Count('id')
            ).values('count', 'show__canonical_show__name')
        }
        for k, v in video_count_by_show.items():
            show_to_mentions[k] += v
    else:
        video_to_show = {
            x['id'] : x['show__canonical_show__name'] for x in
            Video.objects.filter(id__in=result.keys()).values(
                'id', 'show__canonical_show__name'
            )
        }
        for k, v in result.items():
            show_to_mentions[video_to_show[k]] += v
    
    return show_to_mentions


def get_topic_time_by_video(segments):
    """Get the total segment length by video id (assumes overlaps have alread been merged)"""
    result = defaultdict(float)
    for video_id, sub_path, (start, end), _, _ in segments:
        assert start <= end
        result[(video_id, sub_path)] += end - start
    return { k : timedelta(seconds=v) for k, v in result.items() }
    

def get_topic_time_by_show(segments, date_range=None):
    qs = Video.objects.filter(
        id__in={ x[0] for x in segments }
    )
    if date_range is not None:
        qs = qs.filter(time__range=date_range)
    
    video_id_to_canonical_show = {
        x['id'] : x['show__canonical_show__name']
        for x in qs.values('id', 'show__canonical_show__name')
    }
    
    topic_time_by_show = defaultdict(float)
    for video_id, _, (start, end), _, _ in segments:
        assert start <= end
        try:
            topic_time_by_show[video_id_to_canonical_show[video_id]] += end - start
        except KeyError:
            pass
    
    return { k : timedelta(seconds=topic_time_by_show[k]) for k in MAJOR_CANONICAL_SHOWS }


def plot_topic_time_by_show(topics, topic_times_by_show, normalize_by_total_runtime=True, 
                            sort_idx=0):
    if not isinstance(topics, list):
        topics = [topics]
        topic_times_by_show = [topic_times_by_show]
    assert len(topics) == len(topic_times_by_show)
    
    if not normalize_by_total_runtime:
        def plot_bar_chart_by_show_raw(data_by_topic):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(data_by_topic[0]))

            full_width = 0.8
            width = full_width / len(data_by_topic)
            for i, data in enumerate(data_by_topic):
                ys = [y for _, y in data]
                rect = ax1.bar(ind - full_width / 2 + i * width, ys, 
                               width, color=get_color(i), label=topics[i])

            ax1.legend()
            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Hours')
            ax1.set_title('Hours of non-commercial time by show for topics: {}'.format(
                          ' & '.join(topics)))
            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _ in data], rotation=45, ha='right')
            plt.show()

        show_sort_order = { 
            x[0] : i for i, x in enumerate(
                sorted(topic_times_by_show[sort_idx].items(), 
                       key=lambda x: x[1].total_seconds()))
        }

        data_to_plot = []
        for topic, topic_time_by_show in zip(topics, topic_times_by_show):
            single_show_data_to_plot = []
            for show, topic_time in sorted(topic_time_by_show.items(), 
                                           key=lambda x: show_sort_order[x[0]]):
                single_show_data_to_plot.append((
                    show, topic_time.total_seconds() / 60 / 60
                ))
            data_to_plot.append(single_show_data_to_plot)
        plot_bar_chart_by_show_raw(data_to_plot)
        
    else:
        if sort_idx != 0:
            raise NotImplementedError('Cannot set sort_idx on normalized graphs yet')
        
        def plot_bar_chart_by_show_scaled(data_by_topic):
            fig, ax1 = plt.subplots()

            ind = np.arange(len(data_by_topic[0]))
            full_width = 0.8
            width = full_width / len(data_by_topic)

            for i, data in enumerate(data_by_topic):
                rect = ax1.bar(ind - full_width / 2 + i * width, 
                               [y for _, y in data], width,
                               color=get_color(i), label=topics[i])

            ax1.set_ylim(ymin=0.)
            ax1.set_ylabel('Proportion of Show\'s Total Runtime')
            ax1.set_title('Proportion of non-commercial time by show for topics: {}'.format(
                          ' & '.join(topics)))
            ax1.legend()
            ax1.set_xticks(ind)
            ax1.set_xlabel('Show name')
            ax1.set_xticklabels([x for x, _ in data], rotation=45, ha='right')
            plt.show()

        show_sort_order = None
        data_to_plot = []
        for topic, topic_time_by_show in zip(topics, topic_times_by_show):
            single_show_data_to_plot = []
            for show, topic_time in topic_time_by_show.items():
                total_show_runtime = get_total_shot_time_by_show()[show].total_seconds()
                single_show_data_to_plot.append((
                    show, topic_time.total_seconds() / total_show_runtime
                ))
            if show_sort_order is None:
                show_sort_order = { 
                    x[0] : i for i, x in enumerate(
                        sorted(single_show_data_to_plot, key=lambda x: x[1]))
                }
            data_to_plot.append(list(sorted(
                single_show_data_to_plot, key=lambda x: show_sort_order[x[0]]
            )))
        plot_bar_chart_by_show_scaled(data_to_plot)
        

def plot_topic_by_show_over_time(topic, segments, years=range(2015, 2018), quarters=False,
                                 sort_idx=0):
    if quarters:
        for year in years:
            topic_times_by_show = []
            series_names = []

            for quarter in range(4):
                begin_month = (quarter * 3) + 1
                end_month = (quarter * 3) + 4
                if end_month > 12:
                    end_year = year + 1
                    end_month = 1
                else:
                    end_year = year
                topic_times_by_show.append(get_topic_time_by_show(
                    segments, 
                    date_range=['{}-{}-01'.format(year, begin_month), 
                                '{}-{}-01'.format(end_year, end_month)]
                ))
                series_names.append('{} ({}-{})'.format(
                    topic, calendar.month_abbr[begin_month], 
                    calendar.month_abbr[end_month]))

            print('Coverage of {} in {}'.format(topic, year))
            plot_topic_time_by_show(series_names, topic_times_by_show, 
                                    normalize_by_total_runtime=False, 
                                    sort_idx=sort_idx)
            
    else:
        topic_times_by_show = []
        series_names = []
        for year in years:
            topic_times_by_show.append(get_topic_time_by_show(
                segments, 
                date_range=['{}-01-01'.format(year), 
                            '{}-01-01'.format(year + 1)]
            ))
            series_names.append('{} ({})'.format(topic, year))
        plot_topic_time_by_show(series_names, topic_times_by_show, 
                                normalize_by_total_runtime=False,
                                sort_idx=sort_idx)


def plot_topic_over_time_by_channel(topic, segments, threshold=None, years=range(2015, 2018)):
    video_id_to_time_and_channel = { 
        v['id'] : (v['time'], v['channel__name']) 
        for v in Video.objects.all().values('id', 'time', 'channel__name')
    }
    month_to_time = defaultdict(float)
    for video_id, _, (start, end), score, _ in segments:
        if threshold is None or score >= threshold:
            airtime, channel = video_id_to_time_and_channel[video_id]
            month_to_time[(channel, airtime.year, airtime.month)] += end - start
    
    channel_names = [c.name for c in Channel.objects.all()]
    channel_values = []
    for channel in channel_names:
        month_to_min_for_channel = {}
        for (c, year, month), seconds in month_to_time.items():
            if c == channel:
                month_to_min_for_channel[datetime(year=year, month=month, day=1)] = seconds / 60
        channel_values.append(month_to_min_for_channel)
            
    plot_time_series(
        channel_names, channel_values, 
        'Topic time for "{}" over time by channel'.format(topic),
        'Time (min)')
        