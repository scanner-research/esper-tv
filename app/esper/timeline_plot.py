from esper.prelude import *
from esper.stdlib import *
from query.models import * 

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from datetime import timedelta
from collections import defaultdict, namedtuple


def assert_in_range(x, low, high):
    assert x >= low and x <= high, '{} is outside of the range [{}, {}]'.format(x, low, high)
    return x


# Mock ORM objects
MockVideo = namedtuple('MockVideo', ['id', 'path', 'fps', 'num_frames'])

 
VideoSegment = namedtuple('Shot', [
    'start_time',    # timedelta
    'end_time',      # timedelta
    'display_value', # float in [0,1]
    'display_label'  # key (probably String)
])


def parse_video_filename(filename):
    tokens = filename.split('_')
    channel = tokens[0][:-1]
    date = tokens[1][:4] + '-' + tokens[1][4:6] + '-' + tokens[1][6:] + ':' + tokens[2][:2]
    show = ' '.join(tokens[3:])
    return channel, date, show


class VideoRow(object):
    
    def __init__(
        self, 
        video, # Video ORM object
        segments=None, # Use shots by default
        
        # [Shot] list of ORM objects for performance reasons
        shots=None,
        # Shot -> Float (between [0, 1])
        shot_value_fn=lambda x: min(1.0, (x.max_frame - x.min_frame) / 1000), # Default: shot length
        # Shot -> String
        shot_label_fn=lambda x: 'commercial' if x.in_commercial else 'non-commercial',
        
        interval_labels=defaultdict(list), # { Key : [(timedelta, timedelta), ...] }
        discrete_labels=defaultdict(list) # { Key : [timedelta, ...] }
    ):
        self.id = video.id
        self.channel, self.date, self.show = parse_video_filename(video.path.split('/')[-1].split('.')[0])
        
        fps = video.fps
        self.length = timedelta(seconds=video.num_frames / fps)
        
        if segments:
            self.segments = segments
        else:
            # Build segments automatically from Shots
            self.segments = [
                VideoSegment(
                    start_time=timedelta(seconds=s.min_frame / fps), 
                    end_time=timedelta(seconds=s.max_frame / fps),
                    display_value=assert_in_range(shot_value_fn(s), 0., 1.),
                    display_label=shot_label_fn(s)
                ) for s in (shots if shots is not None else Shot.objects.filter(video__id=video.id))
            ]
        
        self.discrete_labels = discrete_labels
        self.interval_labels = interval_labels
            
    def __str__(self):
        return self.name
    

def plot_video_timelines(
    video_rows,
    show_segment_boundaries=False,
    segment_color_map={ 
        'commercial': 'LightGray', 'non-commercial': 'LightCoral'
    },
    interval_label_color_map={},
    discrete_label_shape_map={},
    max_length=None, # timedelta for video length
    out_file=None,   # save to a file (e.g., a pdf)
    show_legend=True,
    min_y_margin=None
):
    fig = plt.figure()
    fig.set_size_inches(14, 2 * len(video_rows))
    ax = fig.add_subplot(111)
    
    # Plot grid for x axis
    ax.grid(color='Grey', which='major', linestyle='-', linewidth=1, axis='x')
    ax.grid(color='LightGrey', which='minor', linestyle='--', linewidth=1, axis='x')
    
    # Plot grid separating the shows on the y axis
    ax.grid(color='LightGrey', which='minor', linestyle='--', linewidth=1, axis='y')

    # Do not add labels more than once so they appear only once in the
    # legend
    defined_labels = set()
    
    y_labels = []
    for i, row in enumerate(video_rows):
        y_labels.append('[{} {}]\n{}\n(id: {})'.format(row.channel, row.date, row.show, row.id))
        
        # Plot segments
        for segment_info in row.segments:
            height = (0.05 + 0.95 * segment_info.display_value) / 2.1 # Use a little less 
                                                                   # than half of the gap
            width = segment_info.end_time.total_seconds() - segment_info.start_time.total_seconds()
            rect = Rectangle(
                (
                    segment_info.start_time.total_seconds(),
                    i
                ),
                width,
                height,
                fc=segment_color_map[segment_info.display_label],
                label=segment_info.display_label if segment_info.display_label not in defined_labels else None
            )
            defined_labels.add(segment_info.display_label)
            ax.add_patch(rect)
        
        # Plot shot boundaries
        if show_segment_boundaries:
            for segment_info in row.segments.values():
                segment_end = segment_info.end_time.total_seconds()
                plt.plot(
                    (segment_end, segment_end),
                    (i, i + 0.25),
                    'Black',
                    linewidth=1
                )
            
        vert_ofs = 0.05
        
        # Plot interval labels
        for label, intervals in row.interval_labels.items():
            for interval in intervals:
                plt.plot(
                    [td.total_seconds() for td in interval], 
                    (i - vert_ofs, i- vert_ofs), 
                    interval_label_color_map[label], 
                    linewidth=2,
                    label=label if label not in defined_labels else None
                )
                defined_labels.add(label)
            vert_ofs += 0.05
            
        # Plot discrete labels
        for label, offsets in row.discrete_labels.items():
            plt.scatter(
                [td.total_seconds() for td in offsets], 
                [i - vert_ofs] * len(offsets),
                s=2,
                c='Black',
                marker=discrete_label_shape_map[label],
                label=label if label not in defined_labels else None
            )
            defined_labels.add(label)
            vert_ofs += 0.05
            
    ax.set_yticks([0.5 + i for i in range(len(video_rows))], minor=True)
    
    # TODO: this is a hack to fix the margins
    if min_y_margin is not None:
        ax.text(-min_y_margin, 0, '.')
        
    plt.yticks(range(len(video_rows)), y_labels)
    plt.ylim([-0.5, len(video_rows) - 0.5])
    
    if max_length is None:
        max_length = max([x.length.total_seconds() for x in video_rows])
    else:
        max_length = max_length.total_seconds()
    plt.xlim([0, int(max_length)])
    
    # Minor ticks every 15 min
    ax.set_xticks(range(0, int(max_length), 900), minor=True)
    
    # Major ticks every hour
    plt.xticks(range(0, int(max_length), 3600))
    
    plt.xlabel('video time (s)')
    if show_legend:
        plt.legend(loc=0, frameon=True, edgecolor='Black', facecolor='White', framealpha=0.7)
    if out_file is not None:
        plt.save_fig(out_file)
    plt.show()
    