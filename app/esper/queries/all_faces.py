from esper.prelude import *
from .queries import query

@query("All faces")
def all_faces():
    from query.models import Face
    from esper.stdlib import qs_to_result
    return qs_to_result(Face.objects.all(), stride=1000)
