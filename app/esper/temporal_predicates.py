from esper.temporal_rangelist_common import Constants

'''
Binary predicates on Temporal Ranges.

Before and After:
    These s optionally take a min_dist and max_dist. They check if
    the distance between tr1 and tr2 is in the range [min_dist, max_dist] (in
    the right direction). Note that by default, this includes intervals that
    meet each other.

OverlapsBefore and OverlapsAfter:
    The strict Allen interval definition of overlapping in either direction.
    Returns true if tr1 and tr2 have the following relationship:
      
      |-----|
         |-----|
    
    OverlapsAfter requires that tr1 start after tr2 (and end after tr2).

Starts and StartsInv:
    True if tr1 has same start time as tr2 and ends before tr2 (flip tr1 and
    tr2 for the inverse).

Finishes and FinishesInv:
    True if tr1 has the same finish time as tr2 and starts before tr2 (flip
    for inverse).

During and DuringInv:
    True if tr1 starts strictly after tr2 and ends strictly before tr2 (flip
    for inverse).

MeetsBefore and MeetsAfter:
    True if tr1 starts when tr2 ends (flip for inverse).

Equal:
    True if tr1 and tr2 start and end at the same time.

Overlaps:
    Sugar for a more colloquial version of overlapping. Includes Starts/Inv,
    Finishes/Inv, During/Inv, Equal, and OverlapsBefore/After.
'''
def true_pred():
    return lambda tr1, tr2: True;

def false_pred():
    return lambda tr1, tr2: False;

def before(min_dist=0, max_dist=Constants.INFTY):
    def fn(tr1, tr2):
        time_diff = tr2.start - tr1.end
        return (time_diff >= min_dist and
            (max_dist == Constants.INFTY or time_diff <= max_dist))

    return fn

def after(min_dist=0, max_dist=Constants.INFTY):
    def fn(tr1, tr2):
        time_diff = tr1.start - tr2.end
        return (time_diff >= min_dist and
            (max_dist == Constants.INFTY or time_diff <= max_dist))

    return fn

def overlaps():
    return lambda tr1, tr2: ((tr1.start < tr2.start and tr1.end > tr2.start) or
            (tr1.start < tr2.end and tr1.end > tr2.end) or
            (tr1.start <= tr2.start and tr1.end >= tr2.end) or
            (tr1.start >= tr2.start and tr1.end <= tr2.end))

def overlaps_before():
    return lambda tr1, tr2: (tr1.end > tr2.start and tr1.end < tr2.end and
            tr1.start < tr2.start)

def overlaps_after():
    return lambda tr1, tr2: (tr1.start > tr2.start and tr1.start < tr2.end and
            tr1.end > tr2.end)

def starts(epsilon=0):
    return lambda tr1, tr2: (abs(tr1.start - tr2.start) <= epsilon
            and tr1.end < tr2.end)

def starts_inv(epsilon=0):
    return lambda tr1, tr2: (abs(tr1.start - tr2.start) <= epsilon
            and tr2.end < tr1.end)

def finishes(epsilon=0):
    return lambda tr1, tr2: (abs(tr1.end - tr2.end) <= epsilon
            and tr1.start > tr2.start)

def finishes_inv(epsilon=0):
    return lambda tr1, tr2: (abs(tr1.end - tr2.end) <= epsilon
            and tr2.start > tr1.start)

def during():
    return lambda tr1, tr2: tr1.start > tr2.start and tr1.end < tr2.end

def during_inv():
    return lambda tr1, tr2: tr2.start > tr1.start and tr2.end < tr1.end

def meets_before(epsilon=0):
    return lambda tr1, tr2: abs(tr1.end-tr2.start) <= epsilon

def meets_after(epsilon=0):
    return lambda tr1, tr2: abs(tr2.end-tr1.start) <= epsilon

def equal():
    return lambda tr1, tr2: tr1.start == tr2.start and tr1.end == tr2.end

def and_pred(pred1, pred2):
    return lambda tr1, tr2: pred1(tr1, tr2) and pred2(tr1, tr2) 

def or_pred(pred1, pred2):
    return lambda tr1, tr2: pred1(tr1, tr2) or pred2(tr1, tr2) 
