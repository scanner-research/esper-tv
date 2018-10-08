import abc

'''
Constants used throughout this module.
'''
class Constants:
    INFTY = "infty"

'''
Predicates (applied per pair of rows during a join between two
TemporalRangeLists.
'''
class Predicate(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def compute(self, tr1, tr2):
        raise NotImplementedError('Must define compute!');

class TruePred(Predicate):
    def compute(self, tr1, tr2):
        return True

class FalsePred(Predicate):
    def compute(self, tr1, tr2):
        return False

class Before(Predicate):
    def __init__(min_dist=0, max_dist=Constants.INFTY):
        self.min_dist = min_dist
        self.max_dist = max_dist

    def compute(self, tr1, tr2):
        time_diff = tr2.start - tr1.end
        return (time_diff >= self.min_dist and
            (self.max_dist == Constants.INFTY or time_diff <= self.max_dist))

class After(Predicate):
    def __init__(min_dist=0, max_dist=Constants.INFTY):
        self.min_dist = min_dist
        self.max_dist = max_dist

    def compute(self, tr1, tr2):
        time_diff = tr1.start - tr2.end
        return (time_diff >= self.min_dist
            and (self.max_dist == Constants.INFTY or time_diff <= self.max_dist))

class Overlaps(Predicate):
    def compute(self, tr1, tr2):
        return ((tr1.start <= tr2.start and tr1.end >= tr2.start) or
            (tr1.start <= tr2.end and tr1.end >= tr2.end))

class Starts(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return (abs(tr1.start - tr2.start) <= self.epsilon
            and tr1.end < tr2.end)

class StartsInv(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return (abs(tr1.start - tr2.start) <= self.epsilon
            and tr2.end < tr1.end)

class Finishes(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return (abs(tr1.end - tr2.end) <= self.epsilon
            and tr1.start > tr2.start)

class FinishesInv(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return (abs(tr1.end - tr2.end) <= self.epsilon
            and tr2.start > tr1.start)

class During(Predicate):
    def compute(self, tr1, tr2):
        return tr1.start > tr2.start and tr1.end < tr2.end

class DuringInv(Predicate):
    def compute(self, tr1, tr2):
        return tr2.start > tr1.start and tr2.end < tr1.end

class MeetsBef(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return abs(tr1.end-tr2.start) <= self.epsilon

class MeetsAfter(Predicate):
    def __init__(epsilon=0):
        self.epsilon = epsilon

    def compute(self, tr1, tr2):
        return abs(tr2.end-tr1.start) <= self.epsilon

class And(Predicate):
    def __init__(pred1, pred2):
        assert(isinstance(pred1, Predicate) and isinstance(pred2, Predicate))
        self.pred1 = pred1
        self.pred2 = pred2

    def compute(self, tr1, tr2):
        return self.pred1(tr1, tr2) and self.pred2(tr1, tr2) 

class Or(Predicate):
    def __init__(pred1, pred2):
        assert(isinstance(pred1, Predicate) and isinstance(pred2, Predicate))
        self.pred1 = pred1
        self.pred2 = pred2

    def compute(self, tr1, tr2):
        return self.pred1(tr1, tr2) or self.pred2(tr1, tr2) 

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

    def __cmp__(self, other):
        if hasattr(other, 'start'):
            if self.start == other.start:
                return self.end.__cmp__(other.end)
            else:
                return self.start.__cmp__(other.start)
'''
A TemporalRangeList is a wrapper around a list of Temporal Ranges that contains
a number of useful helper functions.
'''
class TemporalRangeList:
    def __init__(self, trs):
        self.trs = [tr if isinstance(tr, TemporalRange)
                else TemporalRange(tr[0], tr[1], tr[2])].sort()

    '''
    Combine the temporal ranges in self with the temporal ranges in other.
    '''
    def set_union(self, other):
        assert(isinstance(other, TemporalRangeList))
        return TemporalRangeList(self.trs + other.trs)

    '''
    Recursively merge all overlapping or touching temporal ranges.
    '''
    def coalesce(self):
        raise NotImplementedError

    '''
    Expand every temporal range. An temporal range [start, end, i] will turn into
    [start - window, end + window, i].
    '''
    def dilate(self, window):
        raise NotImplementedError

    '''
    Filter every temporal range by fn. fn takes in an TemporalRange and returns true or
    false.
    '''
    def filter(self, fn):
        raise NotImplementedError

    '''
    Filter temporal ranges so that only temporal ranges of length between min_length and
    max_length are left.
    '''
    def filter_length(self, min_length=0, max_length=Constants.INFTY):
        raise NotImplementedError

    def _tr1_label(tr1, tr2):
        return tr1.label

    '''
    Calculate the difference between the temporal ranges in self and the temporal ranges
    in other.

    If emit_overlaps is False, the resulting TemporalRangeList will not have any
    temporal ranges that overlap with other. That is, it produces the list of
    temporal ranges such that the overlap with self is maximized while not letting
    any of the temporal ranges overlap any of the temporal ranges in other.

    If emit_overlaps is True, the resulting TemporalRangeList will emit a new
    temporal range for every pair of overlapping temporal ranges (i1, i2) where
    i1 is from self, and i2 is from other.

    Only processes pairs that overlap and that satisfy predicate.

    Labels the resulting intervals with label_producer_fn.
    '''
    def minus(self, other, emit_overlaps = False, predicate = TruePred(),
            label_producer_fn = _tr1_label):
        raise NotImplementedError

    '''
    Get the overlapping intervals between self and other.

    Only processes pairs that overlap and that satisfy predicate.

    Labels the resulting intervals with label_producer_fn.
    '''
    def overlaps(self, other, predicate = TruePred(), label_producer_fn =
            _tr1_label):
        raise NotImplementedError

    '''
    Merges pairs of intervals in self and other that satisfy label_producer_fn.

    Only processes pairs that overlap and that satisfy predicate.

    Labels the resulting intervals with label_producer_fn.
    '''
    def merge(self, other, predicate = TruePred(), label_producer_fn =
            _tr1_label):
        raise NotImplementedError

    '''
    Generates a new TemporalRangeList from the cross product of self and other;
    pairs are processed using the udf.
    '''
    def cross_udf(self, other, udf):
        raise NotImplementedError
