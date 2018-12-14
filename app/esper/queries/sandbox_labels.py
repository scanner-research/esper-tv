from esper.prelude import *
from .queries import query

@query('Hand-labeled Interviews (Sandbox)')
def handlabeled_interviews():
    from query.models import LabeledInterview
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    interviews = LabeledInterview.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(interviews))

@query('Hand-labeled Panels (Sandbox)')
def handlabeled_panels():
    from query.models import LabeledPanel
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    panels = LabeledPanel.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(panels))

@query('Hand-labeled Commercials (Sandbox)')
def handlabeled_commercials():
    from query.models import LabeledCommercial
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result

    commercials = LabeledCommercial.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    return intrvllists_to_result(qs_to_intrvllists(commercials))

@query('Multiple Timelines (Sandbox)')
def multiple_timelines():
    from query.models import LabeledInterview, LabeledPanel, LabeledCommercial
    from esper.rekall import qs_to_intrvllists, intrvllists_to_result, add_intrvllists_to_result

    interviews = LabeledInterview.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))
    panels = LabeledPanel.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))
    commercials = LabeledCommercial.objects \
            .annotate(fps=F('video__fps')) \
            .annotate(min_frame=F('fps') * F('start')) \
            .annotate(max_frame=F('fps') * F('end'))

    result = intrvllists_to_result(qs_to_intrvllists(interviews))
    add_intrvllists_to_result(result, qs_to_intrvllists(panels), color="blue")
    add_intrvllists_to_result(result, qs_to_intrvllists(commercials), color="purple")
    return result
