from esper.prelude import *
from esper.stdlib import *
from query.models import *

from datetime import timedelta


NUM_MAJOR_CANONICAL_SHOWS = 150

MAJOR_CANONICAL_SHOWS = [
    x['show__canonical_show__name'] for x in
    Video.objects.values(
        'show__canonical_show__name'
    ).annotate(
        total_duration=Sum(
            ExpressionWrapper(
                F('num_frames') / F('fps'),
                output_field=FloatField()))
    ).order_by(
        '-total_duration'
    ).values(
        'show__canonical_show__name'
    )[:NUM_MAJOR_CANONICAL_SHOWS]
]

# Cache this
_TOTAL_SHOT_TIME_BY_CSHOW = None


def get_total_shot_time_by_canonical_show():
    global _TOTAL_SHOT_TIME_BY_CSHOW
    if _TOTAL_SHOT_TIME_BY_CSHOW is None:
        query_results = Shot.objects.filter(
            video__show__canonical_show__name__in=MAJOR_CANONICAL_SHOWS, 
            in_commercial=False,
        ).values(
            'video__show__canonical_show__name'
        ).annotate(
            screen_time=Sum((F('max_frame') - F('min_frame')) / F('video__fps'),
                            output_field=FloatField())
        )
        _TOTAL_SHOT_TIME_BY_CSHOW = { 
            x['video__show__canonical_show__name']: 
            timedelta(seconds=x['screen_time']) for x in query_results 
        }
    return _TOTAL_SHOT_TIME_BY_CSHOW
