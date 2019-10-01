"""
General ploting library that shhould not include esper concepts or touch the ORM
"""

import math
import matplotlib.pyplot as plt
import matplotlib.colors
import numpy as np
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta

# TODO(james): move other plotting code here


DEFAULT_COLORS = ['LightCoral', 'SkyBlue', 'SandyBrown', 'GreenYellow', 'Goldenrod', 'Violet']

def get_color(i):
    return DEFAULT_COLORS[i % len(DEFAULT_COLORS)]


MONTH_NAMES = ['Unk', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
SECONDS_TO_UNIT_FACTOR = {'s': 1, 'm' : 60 , 'h': 3600, 'd': 3600 * 24}

# Small number to avoid dividing by 0
EPSILON = 1e-12        


def _unpack_value(value):
    if value is None:
        value = 0
    elif isinstance(value, tuple) or isinstance(value, list):
        value = value[0]
    else:
        pass
    if isinstance(value, timedelta):
        value = value.total_seconds()
    return value


def _unpack_variance(value):
    return value[1]


def plot_binary_proportion_comparison(
    series_names, values_by_category, title, xlabel, ylabel,
    secondary_series_names=None, secondary_data=None,
    tertiary_series_names=None, tertiary_data=None,
    baseline_series_names=None, baseline_data=None,
    raw_data_to_label_fn=str, show_ebars=True, z_score=1.96,
    category_color_map=defaultdict(lambda: 'Black'),
    sort_order=None, figsize=(15, 7), legend_loc=0,
    series_colors=['LightBlue', 'LightSalmon'],
    error_colors=['Blue', 'Red'],
    secondary_colors=['DarkBlue', 'DarkRed'],
    baseline_colors=['DarkBlue', 'DarkRed'],
    save_path=None
):
    """
    series_names: [String]
    values_by_category: [{category1: (value, variance), ...}, ...]
    
    secondary_series_names: [String]
    secondary_data: [{category1: (value, variance), ...}, ...]
    
    baseline_series_names: [String]
    baseline_data: [float, ..]
    
    category_color_map: {category1: color, ...}
    """
    assert len(series_names) == 2
    assert len(values_by_category) == 2
    if secondary_series_names is not None:
        assert len(secondary_series_names) == 2
        assert len(secondary_series_names) == len(secondary_data)
    if tertiary_series_names is not None:
        assert len(tertiary_series_names) == 2
        assert len(tertiary_series_names) == len(tertiary_data)
    if baseline_series_names is not None:
        assert len(baseline_series_names) == 2
        assert len(baseline_series_names) == len(baseline_data)

    def plot_bar_chart_by_show_scaled(primary_data, secondary_data, tertiary_data, baseline_data):
        fig, ax1 = plt.subplots(figsize=figsize)

        ind = np.arange(len(primary_data))
        width = 0.8
        
        kwargs = {}
        if show_ebars:
            kwargs['yerr'] = [z_score * math.sqrt(e1) for _, _, e1, _, _, _, _ in primary_data]
            kwargs['ecolor'] = error_colors[0]
        rect1 = ax1.bar(ind - width / 2,
                        [s1 for _, s1, _,  _, _, _, _ in primary_data], 
                        width, color=series_colors[0],
                        label=series_names[0], zorder=0,
                        **kwargs)
        
        kwargs = {}
        if show_ebars:
            kwargs['yerr'] = [z_score * math.sqrt(e2) for _, _, _, _, _, e2, _ in primary_data]
            kwargs['ecolor'] = error_colors[1]
        rect2 = ax1.bar(ind - width / 2, 
                        [-s2 for _, _, _, _, s2, _, _ in primary_data],
                        width, color=series_colors[1],
                        label=series_names[1], zorder=0,
                        **kwargs)
        
        plt.axhline(-0.5, color='LightGray', linestyle='--', 
                    label='Balanced (50:50)', zorder=1)
        plt.axhline(0.5, color='LightGray', linestyle='--', zorder=1)
        
        if secondary_data is not None:
            ax1.scatter(ind - width / 2, [x for x, _ in secondary_data], 
                        color=secondary_colors[0], marker='o', s=50,
                        label=secondary_series_names[0],
                        zorder=2)
            ax1.scatter(ind - width / 2, [-y for _, y in secondary_data], 
                        color=secondary_colors[1], marker='s', s=50,
                        label=secondary_series_names[1],
                        zorder=2)
            
        if tertiary_data is not None:
            ax1.scatter(ind - width / 2, [x for x, _ in tertiary_data], 
                        color='Black', marker='_', s=50,
                        label=tertiary_series_names[0],
                        zorder=3)
            ax1.scatter(ind - width / 2, [-y for _, y in tertiary_data], 
                        color='Black', marker='_', s=50,
                        label=tertiary_series_names[1],
                        zorder=3)
            
        if baseline_data is not None:
            plt.axhline(baseline_data[0], color=baseline_colors[0], 
                        linestyle=':', 
                        label=baseline_series_names[0], zorder=4)
            plt.axhline(-baseline_data[1], color=baseline_colors[1], 
                        linestyle=':', 
                        label=baseline_series_names[1], zorder=4)
            
        if raw_data_to_label_fn is not None:
            for i, x in enumerate(primary_data):
                _, _, _, s12, _, _, s22 = x
                
                ax1.text(ind[i] - width / 2, 0.05, raw_data_to_label_fn(s12),
                         va='bottom', ha='center', rotation='vertical', color='Black',
                         zorder=5)
                ax1.text(ind[i] - width / 2, -0.05, raw_data_to_label_fn(s22),
                         va='top', ha='center', rotation='vertical', color='Black',
                         zorder=5)

        ax1.set_ylabel(ylabel)
        ax1.set_title(title)
        ax1.set_xticks(ind - 0.25)
        ax1.set_xlabel(xlabel)
        ax1.set_xticklabels([x[0] for x in primary_data], rotation=45, ha='right')
        
        for xtick, x in zip(ax1.get_xticklabels(), primary_data):
            xtick.set_color(category_color_map[x[0]])
        
        y_ticks = np.arange(-1., 1.01, 0.25)
        ax1.set_yticks(y_ticks)
        ax1.set_yticklabels([round(x, 2) for x in np.fabs(y_ticks)])
        ax1.set_ylim((-1.,1.))
        
        plt.axhline(0., color='Black', linestyle='-')
        
        ax1.legend(loc=legend_loc)
        if save_path is not None:
            plt.tight_layout()
            plt.savefig(save_path)
        else:
            plt.show()

    primary_data_to_plot = []
    for category in values_by_category[0]:
        series1 = _unpack_value(values_by_category[0][category])
        var1 = _unpack_variance(values_by_category[0][category]) if show_ebars else 0
        
        if category in values_by_category[1]:
            series2 = _unpack_value(values_by_category[1][category])
            var2 = _unpack_variance(values_by_category[1][category]) if show_ebars else 0.
        else:
            series2 = 0.
            var2 = 0.
                
        denom = series1 + series2 + 2 * EPSILON
        primary_data_to_plot.append((
            category, 
            (series1 + EPSILON) / denom, var1 / denom ** 2, series1, 
            (series2 + EPSILON) / denom, var2 / denom ** 2, series2
        ))
        
    if sort_order is not None:
        sort_fn = lambda x: sort_order.index(x[0])
        primary_data_to_plot = [x for x in primary_data_to_plot if x[0] in sort_order]
    else:
        # Order by primary series
        sort_fn = lambda x: x[1] - x[4]
    primary_data_to_plot.sort(key=sort_fn)
    
    def get_non_primary_data(selected_data):
        selected_data_to_plot = []
        
        # Use the same order as the primary series
        for x in primary_data_to_plot:
            category = x[0]
            series1 = (
                _unpack_value(selected_data[0][category])
                if category in selected_data[0] else 0.
            )
            series2 = (
                _unpack_value(selected_data[1][category])
                if category in selected_data[1] else 0.
            )
            denom = series1 + series2 + 2 * EPSILON
            selected_data_to_plot.append(
                ((series1 + EPSILON) / denom, (series2 + EPSILON) / denom)
            )
        return selected_data_to_plot
    
    if secondary_series_names is not None:
        secondary_data_to_plot = get_non_primary_data(secondary_data)
    else:
        secondary_data_to_plot = None
        
    if tertiary_series_names is not None:
        tertiary_data_to_plot = get_non_primary_data(tertiary_data)
    else:
        tertiary_data_to_plot = None
        
    if baseline_series_names is not None:
        denom = sum(baseline_data) + 2 * EPSILON
        baseline_data_to_plot = [
            (baseline_data[0] + EPSILON) / denom,
            (baseline_data[1] + EPSILON) / denom
        ] 
    else:
        baseline_data_to_plot = None
        
    plot_bar_chart_by_show_scaled(
        primary_data_to_plot, 
        secondary_data_to_plot, 
        tertiary_data_to_plot, 
        baseline_data_to_plot
    )
    
    
def plot_binary_screentime_proportion_comparison(*args, **kwargs):
    raw_data_label_unit = kwargs.get('raw_data_label_unit', 'm')
    if 'raw_data_label_unit' in kwargs:
        del kwargs['raw_data_label_unit']
    
    def format_raw_labels(x):
        scale = SECONDS_TO_UNIT_FACTOR[raw_data_label_unit.lower()]
        return '{}{}'.format(int(x / scale), raw_data_label_unit)
    
    kwargs['raw_data_to_label_fn'] = format_raw_labels if raw_data_label_unit is not None else None
    return plot_binary_proportion_comparison(*args, **kwargs)


    
def plot_matrix(series_names, values_by_category, 
                title, xlabel, ylabel, categories=None,
                secondary_values_by_category=None,
                value_names=None,
                category_color_map=defaultdict(lambda: 'Black'),
                primary_scale=1, secondary_scale=1., 
                marker='d', secondary_marker='o',
                figsize=(20, 15)):
    """
    series_names: [String]
    values_by_category: [{category: (timedelta, float), ...}, ...]
    
    categories: [String] # categories in prefered sort order otherwise inferred
    category_color_map: {category: color}
    
    scale: float # constant to increase/decrease marker size
    """
    assert len(series_names) == len(values_by_category)
    fig, ax = plt.subplots(figsize=figsize)
    
    if categories is None:
        categories = set()
        for x in values_by_category:
            categories.update(x.keys())
        categories = sorted(categories)
    
    x = np.arange(len(categories))
    for i, series in enumerate(series_names):
        primary_values = []
        secondary_values = [] if secondary_values_by_category else None
        for category in categories:
            value = _unpack_value(values_by_category[i].get(category, None))                
            primary_values.append(primary_scale * value)
            if secondary_values is not None:
                secondary_value = _unpack_value(
                    secondary_values_by_category[i].get(category, None))
                secondary_values.append(secondary_scale * secondary_value)
        y = np.ones(len(categories)) * i
        
        kwargs = {}
        if i == 0 and value_names is not None:
            kwargs['label'] = value_names[0]
        plt.scatter(x, y, s=primary_values, marker=marker, color='Black',
                    **kwargs)
        
        if secondary_values is not None:
            kwargs = {}
            if i == 0 and value_names is not None:
                kwargs['label'] = value_names[1]
            plt.scatter(x, y, s=secondary_values, marker=secondary_marker, 
                        color='Red', alpha=0.5, **kwargs)
    
    if value_names is not None:
        ax.legend()
    
    ax.set_title(title)
    ax.set_yticks(range(len(series_names)))
    ax.set_yticklabels(series_names)
    ax.set_ylabel(ylabel)
    ax.set_xticks(x)
    ax.set_xlabel(xlabel)
    ax.set_xticklabels(categories, rotation=45, ha='right')
    
    for xtick, x in zip(ax.get_xticklabels(), categories):
        xtick.set_color(category_color_map[x])
    
    plt.show()
    
    
def plot_time_series(series_names, series_data, title, ylabel,
                     min_time=None, max_time=None, plotstyle='-o', 
                     linewidth=1, discrete_events=None, 
                     discrete_event_marker='*',
                     discrete_event_color = 'Black',
                     figsize=(20, 7), save_path=None):
    """
    series_names: [String]
    series_data: [{datetime: value, ...}, ...]
    min_time: datetime
    max_time: datetime
    discrete_events: [(string, (datetime, value) or datetime), ...]
    """
    assert len(series_names) == len(series_data)
    
    def _truncate_to_month(dt):
        return datetime(year=dt.year, month=dt.month, day=1)
    
    def _increment_month(dt):
        init_month = dt.month
        while dt.month == init_month:
            dt += timedelta(days=1)
        return dt
    
    if min_time is None:
        for d in series_data:
            for k in d:
                if min_time is None or min_time > k:
                    min_time = k
    min_time = _truncate_to_month(min_time)
    
    if max_time is None:
        for d in series_data:
            for k in d:
                if max_time is None or max_time < k:
                    max_time = k
    max_time = _increment_month(_truncate_to_month(max_time))
    
    x_ticks = []
    x_ticklabels = []
    curr_time = min_time
    end_time = _increment_month(max_time)
    while curr_time < end_time:
        x_ticks.append(datetime(year=curr_time.year, month=curr_time.month, day=1))
        x_ticklabels.append(
            '{}-{}'.format(MONTH_NAMES[curr_time.month], curr_time.year % 2000)
        )
        curr_time = _increment_month(curr_time)
    
    fig, ax = plt.subplots(figsize=figsize)
    
    max_value = -1.
    for series, data in zip(series_names, series_data):
        x = []
        y = []
        for k, v in sorted(data.items(), key=lambda x: x[0]):
            x.append(k)
            y.append(v)
        ax.plot(x, y, plotstyle, label=series, linewidth=linewidth)
        
        # Track the max y value for the discrete event overlay later
        if len(y) > 0:
            max_value = max(max_value, max(y))
        
    def _unpack_event(x):
        if isinstance(x, datetime):
            return x, max_value # default y_value
        return x[0], x[1]
        
    if discrete_events is not None:
        x = []
        y = []
        for event, value in sorted(discrete_events, key=lambda x: _unpack_event(x[1])[0]): 
            value_x, value_y = _unpack_event(value)
            x.append(value_x)
            y.append(value_y)
            ax.text(value_x, value_y, event + ' ', color=discrete_event_color,
                    ha='right', va='center')
        ax.scatter(x, y, marker=discrete_event_marker, color=discrete_event_color)
            
    ax.legend()
    ax.set_title(title)
    ax.set_xlim([min_time, max_time])
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_ticklabels, rotation=45, ha='right')
    ax.set_ylabel(ylabel)
    ax.set_xlabel('Month-Year')
    if save_path is not None:
        plt.tight_layout()
        plt.savefig(save_path)
    else:
        plt.show()
    
def plot_heatmap_with_images(heatmap, xcategories, yimages, title,
                             heatmap_label_fn=lambda x: '{:0.2f}'.format(x),
                             save_path=None):
    """
    Plot a heatmap, but with images as the ylabels.
    
    heatmap: a 2d ndarray
    xcategories: [String] (x labels) 
    yimages: [image] (y labels - images of same aspect ratio)
    """
    yimage_aspect_ratio = math.ceil(yimages[0].shape[1] / yimages[0].shape[0])
    yimage_width_proportion = yimage_aspect_ratio / (yimage_aspect_ratio + len(xcategories))
    
    fig, ax = plt.subplots(
        figsize=(1 * (yimage_aspect_ratio + len(xcategories)), 1 * len(yimages))
    )
    
    ax.set_position([yimage_width_proportion, 0, 1 - yimage_width_proportion, 1])
    color_map = matplotlib.colors.LinearSegmentedColormap.from_list("", ["white","red"])
    cax = ax.imshow(heatmap, origin='lower', cmap=color_map)
    ax.set_xticks(range(len(xcategories)))
    ax.set_xticklabels(xcategories)
    ax.set_yticks([])
    max_val = np.max(heatmap)
    min_val = np.min(heatmap)
    for i in range(heatmap.shape[0]):
        for j in range(heatmap.shape[1]):
            text = ax.text(
                j, i, heatmap_label_fn(heatmap[i, j]), 
                ha='center', va='center', 
                color='black'  #if (heatmap[i, j] - min_val) / (max_val - min_val) < 0.6 else 'black'
            )

    def _swap_channels(im):
        im2 = im.copy()
        im2[:, :, 0] = im[:, :, 2]
        im2[:, :, 2] = im[:, :, 0]
        return im2

    for i, im in enumerate(yimages):
        ax1 = fig.add_axes(
            [
                 0,
                 i / len(yimages), 
                 yimage_width_proportion,
                 1 / len(yimages)
            ]
        )
        ax1.axison = False
        ax1.imshow(_swap_channels(im))
    plt.title(title)
    if save_path is not None:
        plt.savefig(save_path)
    else:
        plt.show()

    
def tile_images(imgs, rows=None, cols=None, blank_value=0):
    # If neither rows/cols is specified, make a square
    if rows is None and cols is None:
        rows = int(math.sqrt(len(imgs)))

    if rows is None:
        rows = int((len(imgs) + cols - 1) / cols)
    else:
        cols = int((len(imgs) + rows - 1) / rows)

    # Pad missing frames with black
    diff = rows * cols - len(imgs)
    if diff != 0:
        imgs.extend([np.zeros(imgs[0].shape, dtype=imgs[0].dtype) + blank_value for _ in range(diff)])

    return np.vstack([np.hstack(imgs[i * cols:(i + 1) * cols]) for i in range(rows)])


def plot_bar_chart(series_names, values_by_category, title, xlabel, ylabel, 
                   series_colors=None, logy=False, show_ebars=True, sort_order=None, 
                   figsize=(14, 7), save_path=None, legend_loc=0):
    assert len(series_names) == len(values_by_category)
    
    if not sort_order:
        all_categories = set()
        for v in values_by_category:
            all_categories.update(v.keys())
        sort_order = list(all_categories)
        sort_order.sort(key=lambda x: values_by_category[0].get(_unpack_value(x), -1e12))
    all_categories = sort_order         
           
    series_to_plot = []
    for values in values_by_category:
        series = []
        for c in all_categories:
            value = _unpack_value(values.get(c, 0))
            variance = _unpack_variance(values.get(c, (None, 0))) if show_ebars else 0
            series.append((value, variance))
        series_to_plot.append(series)
    
    fig, ax1 = plt.subplots(figsize=figsize)
    ind = np.arange(len(all_categories))

    full_width = 0.6
    width = full_width / len(series_to_plot)
    for i, series in enumerate(series_to_plot):
        ys = [y for y, _ in series]
        stds = [1.96 * (z ** 0.5) for _, z in series]
        rect = ax1.bar(
            ind - ((full_width / 2) + (i * width)), ys, 
            width, 
            color=get_color(i) if series_colors is None else series_colors[i], 
            yerr=stds if show_ebars else None, 
            ecolor='black', label=series_names[i]                                                               
        )

    ax1.legend(loc=legend_loc)
    ax1.set_ylabel(ylabel)
    if logy:
        ax1.set_ylim(bottom=10)
        ax1.set_yscale('log', nonposy='clip')
    else:
        ax1.set_ylim(ymin=0.)
    ax1.set_title(title)
    ax1.set_xticks(ind - 0.25)
    ax1.set_xlabel(xlabel)
    ax1.set_xticklabels(all_categories, rotation=45, ha='right')
    if save_path is not None:
        plt.tight_layout()
        plt.savefig(save_path)
    else:
        plt.show()

def plot_stacked_bar_chart(raw_input_bar_chart, chan):
    #Color key
    color = {'CNN':'blue', 'MSNBC':'green', 'FOXNEWS':'red'}
#     for chan in channels:
    values = []
    for show in sorted(list(raw_input_bar_chart.keys())):
        if raw_input_bar_chart[show] > 1000:
           values.append(raw_input_bar_chart[show])
        else:
            del raw_input_bar_chart[show]
    df=pd.DataFrame({'Shows': sorted(list(raw_input_bar_chart.keys())), chan: values})

    # multiple line plot
    plt.plot('Shows', chan, data=df, marker='o', markerfacecolor=color[chan], markersize=15, color='skyblue', linewidth=3)
    plt.xticks(rotation=45)
    plt.xlabel('Shows')
    plt.ylabel('# of frames the person shows up in a show')
    plt.legend()

    
    