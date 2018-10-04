from esper.prelude import *
from esper.stdlib import *
from query.models import *

from datetime import timedelta


NUM_MAJOR_CANONICAL_SHOWS = 40

MAJOR_CANONICAL_SHOWS = [
    x['show__canonical_show__name'] for x in
    Video.objects.filter(
        show__canonical_show__is_recurring=True,
        threeyears_dataset=True # TODO: remove this check
    ).values(
        'show__canonical_show__name'
    ).annotate(
        video_count=Count('id')
    ).order_by(
        '-video_count'
    ).values(
        'show__canonical_show__name'
    )[:NUM_MAJOR_CANONICAL_SHOWS]
]

# Cache this
total_shot_time_by_show = None


def get_total_shot_time_by_show():
    global total_shot_time_by_show
    if total_shot_time_by_show is None:
        query_results = Shot.objects.filter(
            video__show__canonical_show__name__in=MAJOR_CANONICAL_SHOWS, in_commercial=False,
        ).values(
            'video__show__canonical_show__name'
        ).annotate(
            screen_time=Sum((F('max_frame') - F('min_frame')) / F('video__fps'),
                            output_field=FloatField())
        )
        total_shot_time_by_show = { 
            x['video__show__canonical_show__name'] : timedelta(seconds=x['screen_time']) for x in query_results 
        }
    return total_shot_time_by_show
