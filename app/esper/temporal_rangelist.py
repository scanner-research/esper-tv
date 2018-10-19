import itertools
from esper.temporal_rangelist_common import Constants
from esper.temporal_predicates import *

'''
A helper function that, given two objects, returns the label field of the first
one.
'''
def tr1_label(tr1, tr2):
    return tr1.label

'''
A helper function that, given two objects, returns the label field of the first
one.
'''
def tr2_label(tr1, tr2):
    return tr2.label

'''
A TemporalRange has a start time, end time, and label.
'''
class TemporalRange:
    '''
    Construct an temporal range from a start time, end time, and integer label.
    '''
    def __init__(self, start, end, label):
        self.start = start
        self.end = end
        self.label = label

    def sort_key(tr):
        return (tr.start, tr.end, tr.label)

    def __repr__(self):
        return "<Temporal Range start:{} end:{} label:{}>".format(self.start,
                self.end, self.label)

    def copy(self):
        return TemporalRange(self.start, self.end, self.label)

    '''
    Computes the interval difference between self and other and returns results
    in an array.
    If there is no overlap between self and other, [self.copy()] is returned.
    If self is completely contained by other, [] is returned.
    Otherwise, returns a list l of intervals such that the members of l
    maximally cover self without overlapping other.
    The labels of the members of l are determined by
    label_producer_fn(self, other).
    '''
    def minus(self, other, label_producer_fn=tr1_label):
        if overlaps()(self, other):
            label = label_producer_fn(self, other)
            if during()(self, other) or equal()(self, other):
                return []
            if overlaps_before()(self, other):
                return [TemporalRange(self.start, other.start, label)]
            if overlaps_after()(self, other):
                return [TemporalRange(other.end, self.end, label)]
            if during()(other, self):
                return [TemporalRange(self.start, other.start, label),
                        TemporalRange(other.end, self.end, label)]
            error_string = "Reached unreachable point in minus with {} and {}"
            error_string = error_string.format(self, other)
            assert False, error_string
        else:
            return [self.copy()]

    '''
    Computes the interval overlap between self and other.
    If there is no overlap between self and other, returns None.
    Otherwise, it returns an interval that maximally overlaps both self and
    other, with label produced by lable_producer_fn(self, other).
    '''
    def overlap(self, other, label_producer_fn=tr1_label):
        if overlaps()(self, other):
            label = label_producer_fn(self, other)
            if during()(self, other) or equal()(self, other):
                return TemporalRange(self.start, self.end, label)
            if overlaps_before()(self, other):
                return TemporalRange(other.start, self.end, label)
            if overlaps_after()(self, other):
                return TemporalRange(self.start, other.end, label)
            if during()(other, self):
                return TemporalRange(other.start, other.end, label)
            error_string = "Reached unreachable point in minus with {} and {}"
            error_string = error_string.format(self, other)
            assert False, error_string
        else:
            return None

    '''
    Computes the minimum interval that contains both self and other.
    '''
    def merge(self, other, label_producer_fn=tr1_label):
        label = label_producer_fn(self, other)
        return TemporalRange(min(self.start, other.start),
                max(self.end, other.end), label)

    '''
    Getters.
    '''
    def get_start(self):
        return self.start
    def get_end(self):
        return self.end
    def get_label(self):
        return self.label


'''
A TemporalRangeList is a wrapper around a list of Temporal Ranges that contains
a number of useful helper functions.
'''
class TemporalRangeList:
    def __init__(self, trs):
        self.trs = sorted([tr if isinstance(tr, TemporalRange)
                else TemporalRange(tr[0], tr[1], tr[2]) for tr in trs],
                key = TemporalRange.sort_key)

    def __repr__(self):
        return str(self.trs)
    
    '''
    Gets number of Temporal Ranges stored by this TemporalRangeList.
    '''
    def size(self):
        return len(self.trs)

    '''
    Return an ordered list of the TemporalRanges.
    '''
    def get_temporal_ranges(self):
        return self.trs

    '''
    Combine the temporal ranges in self with the temporal ranges in other.
    '''
    def set_union(self, other):
        return TemporalRangeList(self.trs + other.trs)

    '''
    Recursively merge all overlapping or touching temporal ranges.

    If require_same_label is True, then only merge ranges that have the same
    label.
    '''
    def coalesce(self, require_same_label=False):
        if len(self.trs) == 0:
            return self
        new_trs = []
        first_by_label = {}
        for tr in self.trs:
            if require_same_label:
                label = tr.label
            else:
                label = 0
            if label in first_by_label:
                first = first_by_label[label]
                if tr.start >= first.start and tr.start <= first.end:
                    # tr overlaps with first
                    if tr.end > first.end:
                        # need to push the upper bound of first
                        first.end = tr.end
                else:
                    # tr does not overlap with first
                    new_trs.append(first_by_label[label])
                    first_by_label[label] = tr.copy()
            else:
                first_by_label[label] = tr.copy()
        for tr in first_by_label.values():
            new_trs.append(tr)

        return TemporalRangeList(new_trs)

    '''
    Expand every temporal range. An temporal range [start, end, i] will turn into
    [start - window, end + window, i].
    '''
    def dilate(self, window):
        return TemporalRangeList(
            [TemporalRange(tr.start - window, tr.end + window, tr.label) 
                for tr in self.trs])

    '''
    Filter every temporal range by fn. fn takes in an TemporalRange and returns true or
    false.
    '''
    def filter(self, fn):
        return TemporalRangeList([tr.copy() for tr in self.trs if fn(tr)])

    '''
    Filter temporal ranges so that only temporal ranges of length between min_length and
    max_length are left.
    '''
    def filter_length(self, min_length=0, max_length=Constants.INFTY):
        def filter_fn(tr):
            length = tr.end - tr.start
            return length >= min_length and (max_length == Constants.INFTY
                    or length <= max_length)

        return self.filter(filter_fn)

    '''
    Filter the ranges in self against the ranges in other, only keeping the
    ranges in self that satisfy predicate with at least one other range in
    other.
    '''
    def filter_against(self, other, predicate=true_pred()):
        def filter_fn(tr):
            for trother in other.trs:
                if predicate(tr, trother):
                    return True
            return False

        return self.filter(filter_fn)

    '''
    Calculate the difference between the temporal ranges in self and the temporal ranges
    in other.

    The difference between two intervals can produce up to two new intervals.
    If recursive_diff is True, difference operations will recursively be
    applied to the resulting intervals.
    If recursive_diff is False, the results of each difference operation
    between every valid pair of intervals in self and other will be emitted.

    For example, suppose the following interval is in self:

    |--------------------------------------------------------|

    and that the following two intervals are in other:

              |--------------|     |----------------|
    
    If recursive_diff is True, this function will produce three intervals:

    |---------|              |-----|                |--------|

    If recursive_diff is False, this function will produce four intervals, some
    of which are overlapping:

    |---------|              |-------------------------------|
    |------------------------------|                |--------|

    Only computes differences for pairs that overlap and that satisfy
    predicate.

    If an interval in self overlaps no pairs in other such that the two
    satisfy predicate, then the interval is reproduced in the output.

    Labels the resulting intervals with label_producer_fn. For recursive_diff,
    the intervals passed in to the label producer function are the original
    interval and the first interval that touches the output interval.
    '''
    def minus(self, other, recursive_diff = True, predicate = true_pred(),
            label_producer_fn = tr1_label):
        if not recursive_diff:
            output = []
            for tr1 in self.trs:
                found_overlap = False
                for tr2 in other.trs:
                    if overlaps()(tr1, tr2) and predicate(tr1, tr2):
                        found_overlap = True
                        candidates = tr1.minus(tr2)
                        if len(candidates) > 0:
                            output = output + candidates
                if not found_overlap:
                    output.append(tr1.copy())
            return TemporalRangeList(output)
        else:
            output = []
            for tr1 in self.trs:
                # For each interval in self.trs, get all the overlapping
                #   intervals from other.trs
                overlapping = []
                for tr2 in other.trs:
                    if tr1 == tr2:
                        continue
                    if before()(tr1, tr2):
                        break
                    if (overlaps()(tr1, tr2) and
                        predicate(tr1, tr2)):
                        overlapping.append(tr2)

                if len(overlapping) == 0:
                    output.append(tr1.copy())
                
                # Create a sorted list of all start to end points between
                #   tr1.start and tr1.end, inclusive
                endpoints_set = set([tr1.start, tr1.end])
                for tr in overlapping:
                    if tr.start > tr1.start:
                        endpoints_set.add(tr.start)
                    if tr.end < tr1.end:
                        endpoints_set.add(tr.end)
                endpoints_list = sorted(list(endpoints_set))

                # Calculate longest subsequence endpoint pairs
                longest_subsequences = []
                last_j = -1
                for i in range(len(endpoints_list)):
                    if i <= last_j:
                        continue
                    start = endpoints_list[i]
                    valid = True
                    for tr in overlapping:
                        if tr.start > start:
                            break
                        if tr.start < start and tr.end > start:
                            valid = False
                            break
                    if not valid:
                        continue
                    max_j = len(endpoints_list) - 1
                    for j in range(max_j, i, -1):
                        end = endpoints_list[j]
                        tr_candidate = TemporalRange(start, end, 0)
                        valid = True
                        for tr in overlapping:
                            if tr.start > end:
                                break
                            if overlaps()(tr, tr_candidate):
                                valid = False
                                break
                        if valid:
                            longest_subsequences.append((start, end))
                            last_j = j

                # Figure out which intervals from overlapping to use to
                # construct new intervals
                for subsequence in longest_subsequences:
                    start = subsequence[0]
                    end = subsequence[1]
                    for tr in overlapping:
                        if tr.end == start or tr.start == end:
                            label = label_producer_fn(tr1, tr)
                            output.append(TemporalRange(start, end, label))
                            break

            return TemporalRangeList(output)


    '''
    Get the overlapping intervals between self and other.

    Only processes pairs that overlap and that satisfy predicate.

    Labels the resulting intervals with label_producer_fn.
    '''
    def overlaps(self, other, predicate = true_pred(), label_producer_fn =
            tr1_label):
        return TemporalRangeList([tr1.overlap(tr2, label_producer_fn)
                for tr1 in self.trs for tr2 in other.trs
                if (overlaps()(tr1, tr2) and
                    predicate(tr1, tr2))])

    '''
    Merges pairs of intervals in self and other that satisfy label_producer_fn.

    Only processes pairs that satisfy predicate.

    Labels the resulting intervals with label_producer_fn.
    '''
    def merge(self, other, predicate = true_pred(), label_producer_fn =
            tr1_label):
        return TemporalRangeList([tr1.merge(tr2, label_producer_fn)
                for tr1 in self.trs for tr2 in other.trs
                if predicate(tr1, tr2)])

    '''
    Generates a new TemporalRangeList from the cross product of self and other;
    pairs are processed using the udf.
    '''
    def cross_udf(self, other, udf):
        return TemporalRangeList(list(itertools.chain.from_iterable([
                udf(tr1, tr2) for tr1 in self.trs for tr2 in other.trs
            ])))
