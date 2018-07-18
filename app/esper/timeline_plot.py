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


class VideoRow(object):
    
    ShotEntry = namedtuple('Shot', [
        'start_time', 'end_time', 'in_commercial', 'display_value', 'display_label'
    ])
    
    def __init__(
        self, 
        video, # Video ORM object
        shots=None, # [Shot]
        
        # Shot -> Float (between [0, 1])
        shot_value_fn=lambda x: min(1.0, (x.max_frame - x.min_frame) / 240), # Default: shot length
        
        # Shot -> String
        shot_label_fn=lambda x: 'commercial' if x.in_commercial else 'non-commercial',
        
        interval_labels=defaultdict(list), # { Key : [(timedelta, timedelta), ...] }
        discrete_labels=defaultdict(list) # { Key : [timedelta, ...] }
    ):
        self.name = video.path.split('/')[-1].split('.')[0]
        
        fps = video.fps
        self.length = timedelta(seconds=video.num_frames / fps)
        
        self.shots = {
            s.id : VideoRow.ShotEntry(
                start_time=timedelta(seconds=s.min_frame / fps), 
                end_time=timedelta(seconds=s.max_frame / fps),
                in_commercial=s.in_commercial,
                display_value=assert_in_range(shot_value_fn(s), 0., 1.),
                display_label=shot_label_fn(s)
            ) for s in (shots if shots is not None else Shot.objects.filter(video=video))
        }
        
        self.discrete_labels = discrete_labels
        self.interval_labels = interval_labels
            
    def __str__(self):
        return self.name
    

def plot_video_timelines(
    video_rows,
    show_shot_boundaries=False,
    shot_color_map={ 
        'commercial': 'LightGray', 'non-commercial': 'LightCoral'
    },
    interval_label_color_map={},
    discrete_label_shape_map={},
    max_length=None # timedelta for video length
):
    fig = plt.figure()
    fig.set_size_inches(14, 2 * len(video_rows))
    ax = fig.add_subplot(111)
    ax.grid(color='Grey', which='major', linestyle='--', linewidth=1, axis='x')
    ax.grid(color='Grey', which='minor', linestyle='--', linewidth=1, axis='y')

    # Do not add labels more than once so they appear only once in the
    # legend
    defined_labels = set()
    
    y_labels = []
    for i, row in enumerate(sorted(video_rows, key=lambda x: x.name)):
        y_labels.append(row.name)
        
        # Plot shots
        for shot_id, shot_info in row.shots.items():
            height = (0.05 + 0.95 * shot_info.display_value) / 2.1 # Use a little less 
                                                                   # than half of the gap
            width = shot_info.end_time.total_seconds() - shot_info.start_time.total_seconds()
            rect = Rectangle(
                (
                    shot_info.start_time.total_seconds(),
                    i
                ),
                width,
                height,
                fc=shot_color_map[shot_info.display_label],
            )
            ax.add_patch(rect)
        
        # Plot shot boundaries
        if show_shot_boundaries:
            for shot_info in row.shots.values():
                shot_end = shot_info.end_time.total_seconds()
                plt.plot(
                    (shot_end, shot_end),
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
                    linewidth=4,
                    label=label if label not in defined_labels else None
                )
            defined_labels.add(label)
            vert_ofs += 0.075
            
        # Plot discrete labels
        for label, offsets in row.discrete_labels.items():
            plt.scatter(
                [td.total_seconds() for td in offsets], 
                [i - vert_ofs] * len(offsets),
                c='Black',
                marker=discrete_label_shape_map[label],
                label=label if label not in defined_labels else None
            )
            defined_labels.add(label)
            vert_ofs += 0.075
            
    ax.set_yticks([0.5 + i for i in range(len(video_rows))], minor=True)
    
    plt.yticks(range(len(video_rows)), y_labels)
    plt.ylim([-0.5, len(video_rows) - 0.5])
    
    if max_length:
        plt.xlim([0, max([x.length.total_seconds() for x in video_rows])])
    plt.xlabel('video time (s)')
    plt.legend(loc=1)
    plt.show()
    