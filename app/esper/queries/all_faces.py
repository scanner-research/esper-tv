from esper.prelude import *
from .queries import query

@query("All faces")
def all_faces():
    from query.models import Face
    from esper.widget import qs_to_result
    return qs_to_result(Face.objects.all(), stride=1000)


@query("All clothing")
def all_clothing():
    from query.models import Clothing
    from esper.widget import qs_to_result
    return qs_to_result(Clothing.objects.all(), stride=1000)


@query("All haircolor")
def all_haircolor():
    from query.models import HairColor
    from esper.widget import qs_to_result
    return qs_to_result(HairColor.objects.all(), stride=1000)


@query("All hairlength")
def all_hairlength():
    from query.models import HairLength
    from esper.widget import qs_to_result
    return qs_to_result(HairLength.objects.all(), stride=1000)