from esper.prelude import *
from .queries import query

@query('Interview with person X (rekall)')
def interview_with_person_x():
    from query.models import LabeledCommercial, FaceIdentity
    from rekall.video_interval_collection import VideoIntervalCollection
    from rekall.temporal_predicates import before, after, overlaps
    from rekall.logical_predicates import or_pred
    from esper.rekall import intrvllists_to_result

    # Get list of sandbox video IDs
    sandbox_videos = [
        row.video_id
        for row in LabeledCommercial.objects.distinct('video_id')
    ]

    TWENTY_SECONDS = 600
    FORTY_FIVE_SECONDS = 1350
    EPSILON = 10

    guest_name = "bernie sanders"

    # Load hosts and instances of guest from SQL
    identities = FaceIdentity.objects.filter(face__shot__video_id__in=sandbox_videos)
    hosts_qs = identities.filter(face__is_host=True)
    guest_qs = identities.filter(identity__name=guest_name).filter(probability__gt=0.7)

    # Put bounding boxes in SQL
    hosts = VideoIntervalCollection.from_django_qs(
        hosts_qs.annotate(video_id=F("face__shot__video_id"),
            min_frame=F("face__shot__min_frame"),
            max_frame=F("face__shot__max_frame"))
        )
    guest = VideoIntervalCollection.from_django_qs(
        guest_qs.annotate(video_id=F("face__shot__video_id"),
        min_frame=F("face__shot__min_frame"),
        max_frame=F("face__shot__max_frame"))
    )

    # Get all shots where the guest and a host are on screen together
    guest_with_host = guest.overlaps(hosts).coalesce()

    # This temporal predicate defines A overlaps with B, or A before by less than 10 frames,
    #   or A after B by less than 10 frames
    overlaps_before_or_after_pred = or_pred(
            or_pred(overlaps(), before(max_dist=EPSILON), arity=2),
            after(max_dist=EPSILON), arity=2)

    # This code finds sequences of:
    #   guest with host overlaps/before/after host OR
    #   guest with host overlaps/before/after guest
    interview_candidates = guest_with_host \
            .merge(hosts, predicate=overlaps_before_or_after_pred) \
            .set_union(guest_with_host.merge(
                guest, predicate=overlaps_before_or_after_pred)) \
            .coalesce()

    # Sequences may be interrupted by shots where the guest or host don't
    #   appear, so dilate and coalesce to merge neighboring segments
    interviews = interview_candidates \
            .dilate(TWENTY_SECONDS) \
            .coalesce() \
            .dilate(-1 * TWENTY_SECONDS) \
            .filter_length(min_length=FORTY_FIVE_SECONDS)

    # Return intervals
    return intrvllists_to_result(interviews.get_allintervals())
