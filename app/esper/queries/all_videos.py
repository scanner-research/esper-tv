from esper.prelude import *
from .queries import query

@query("All videos")
def all_videos():
    from query.models import Video
    from esper.stdlib import qs_to_result
    return qs_to_result(Video.objects.all())
