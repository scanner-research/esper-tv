"""
General ploting library that shhould not include esper concepts or touch the ORM
"""

import math
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict

# TODO(james): move other ploting code here


DEFAULT_COLORS = ['LightCoral', 'SkyBlue', 'SandyBrown', 'GreenYellow', 'Goldenrod', 'Violet']

def get_color(i):
    return DEFAULT_COLORS[i % len(DEFAULT_COLORS)]


MONTH_NAMES = ['Unk', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
SECONDS_TO_UNIT_FACTOR = {'s': 1, 'm' : 60 , 'h': 3600, 'd': 3600 * 24}

def plot_binary_screentime_proportion_comparison(series_names, values_by_subcategory, title, xlabel, ylabel,
                                                 secondary_series_names=None, secondary_data=None,
                                                 tertiary_series_names=None, tertiary_data=None,
                                                 show_raw_data_labels=True, raw_data_label_unit='m', 
                                                 show_ebars=True, z_score=1.96):
    """
    series_names: [String]
    values_by_subcategory: [{subcategory1: (value, variance), ...}, ...]
    
    secondary_series_names: [String]
    secondary_data: [{subcategory1: (value, variance), ...}, ...]
    """
    assert len(series_names) == 2
    assert len(values_by_subcategory) == 2
    if secondary_series_names is not None:
        assert len(secondary_series_names) == 2
        assert len(secondary_series_names) == len(secondary_data)

    def plot_bar_chart_by_show_scaled(primary_data, secondary_data, tertiary_data):
        fig, ax1 = plt.subplots()

        ind = np.arange(len(primary_data))
        width = 0.8
        
        kwargs = {}
        if show_ebars:
            kwargs['yerr'] = [z_score * math.sqrt(e1) for _, _, e1, _, _, _, _ in primary_data]
            kwargs['ecolor'] = 'Blue'
        rect1 = ax1.bar(ind - width / 2,
                        [s1 for _, s1, _,  _, _, _, _ in primary_data], 
                        width, color='LightBlue', label=series_names[0], zorder=0,
                        **kwargs)
        
        kwargs = {}
        if show_ebars:
            kwargs['yerr'] = [z_score * math.sqrt(e2) for _, _, _, _, _, e2, _ in primary_data]
            kwargs['ecolor'] = 'Red'
        rect2 = ax1.bar(ind - width / 2, 
                        [-s2 for _, _, _, _, s2, _, _ in primary_data],
                        width, color='LightSalmon', label=series_names[1], zorder=0,
                        **kwargs)
        
        plt.axhline(-0.5, color='LightGray', linestyle='--', 
                    label='Balanced (50:50)', zorder=1)
        plt.axhline(0.5, color='LightGray', linestyle='--', zorder=1)
        
        if secondary_data is not None:
            ax1.scatter(ind - width / 2, [x for x, _ in secondary_data], 
                        color='DarkBlue', marker='o', s=50,
                        label=secondary_series_names[0],
                        zorder=2)
            ax1.scatter(ind - width / 2, [-y for _, y in secondary_data], 
                        color='DarkRed', marker='s', s=50,
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
            
        if show_raw_data_labels:
            for i, x in enumerate(primary_data):
                _, _, _, s12, _, _, s22 = x
                scale = SECONDS_TO_UNIT_FACTOR[raw_data_label_unit.lower()]
                ax1.text(ind[i] - width / 2, 0.05,
                         '{}{}'.format(int(s12 / scale), raw_data_label_unit),
                         va='bottom', ha='center', rotation='vertical', color='Black',
                         zorder=4)
                ax1.text(ind[i] - width / 2, -0.05,
                         '{}{}'.format(int(s22 / scale), raw_data_label_unit),
                         va='top', ha='center', rotation='vertical', color='Black',
                         zorder=4)

        ax1.set_ylabel(ylabel)
        ax1.set_title(title)
        ax1.set_xticks(ind)
        ax1.set_xlabel(xlabel)
        ax1.set_xticklabels([x[0] for x in primary_data], rotation=45, ha='right')
        
        y_ticks = np.arange(-1., 1.01, 0.25)
        ax1.set_yticks(y_ticks)
        ax1.set_yticklabels([round(x, 2) for x in np.fabs(y_ticks)])
        ax1.set_ylim((-1.,1.))
        
        plt.axhline(0., color='Black', linestyle='-')
        
        ax1.legend()
        plt.show()

    primary_data_to_plot = []
    for subcategory in values_by_subcategory[0]:
        series1 = values_by_subcategory[0][subcategory][0].total_seconds()
        var1 = values_by_subcategory[0][subcategory][1]
        
        if subcategory in values_by_subcategory[1]:
            series2 = values_by_subcategory[1][subcategory][0].total_seconds()
            var2 = values_by_subcategory[1][subcategory][1] if show_ebars else 0.
        else:
            series2 = 0.
            var2 = 0.
                
        denom = series1 + series2
        primary_data_to_plot.append((
            subcategory, 
            series1 / denom, var1 / denom ** 2, series1, 
            series2 / denom, var2 / denom ** 2, series2
        ))
        
    # Order by primary series
    primary_data_to_plot.sort(key=lambda x: x[1] - x[4])
    
    def get_non_primary_data(selected_data):
        selected_data_to_plot = []
        
        # Use the same order as the primary series
        for x in primary_data_to_plot:
            subcategory = x[0]
            series1 = selected_data[0][subcategory][0].total_seconds() if subcategory in selected_data[0] else 0.
            series2 = selected_data[1][subcategory][0].total_seconds() if subcategory in selected_data[1] else 0.
            denom = series1 + series2
            selected_data_to_plot.append((series1 / denom, series2 / denom))
        return selected_data_to_plot
    
    if secondary_series_names is not None:
        secondary_data_to_plot = get_non_primary_data(secondary_data)
    else:
        secondary_data_to_plot = None
        
    if tertiary_series_names is not None:
        tertiary_data_to_plot = get_non_primary_data(tertiary_data)
    else:
        tertiary_data_to_plot = None
    
    plot_bar_chart_by_show_scaled(primary_data_to_plot, secondary_data_to_plot, tertiary_data_to_plot)

    
def plot_time_series_by_month(series_names, month_to_values, years, title, ylabel):
    """
    series_names: [String]
    month_to_values: [{(year, month): value, ...}, ...]
    """
    assert len(series_names) == len(month_to_values)
    
    y = defaultdict(list)    
    x_labels = []
    for year in years:
        for month in range(1, 13):
            x_labels.append('{}-{}'.format(MONTH_NAMES[month], year % 2000))
            for i, series in enumerate(series_names):
                y[series].append(month_to_values[i].get((year, month), 0.))
            
    for series in series_names:
        plt.plot(range(len(x_labels)), y[series], '-o', label=series)
            
    plt.legend()
    plt.title(title)
    plt.xticks(range(len(x_labels)), x_labels, rotation=45, ha='right')
    plt.ylabel(ylabel)
    plt.xlabel('Month-Year')
    plt.show() 
