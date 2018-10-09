import abc
from temporal_rangelist_common import Constants

'''
Binary Predicates on Temporal Ranges.
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
        return ((tr1.start < tr2.start and tr1.end > tr2.start) or
            (tr1.start < tr2.end and tr1.end > tr2.end) or
            (tr1.start == tr2.start and tr1.end == tr2.end))

class OverlapsBefore(Predicate):
    def compute(self, tr1, tr2):
        return (tr1.end > tr2.start and tr1.end < tr2.end and tr1.start <
                tr2.start)

class OverlapsAfter(Predicate):
    def compute(self, tr1, tr2):
        return (tr1.start > tr2.start and tr1.start < tr2.end and tr1.end >
                tr2.end)

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

class Equal(Predicate):
    def compute(self, tr1, tr2):
        return tr1.start == tr2.start and tr1.end == tr2.end

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
