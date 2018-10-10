from esper.temporal_predicates import *
from esper.temporal_rangelist import TemporalRange
import unittest

class TestTemporalPredicates(unittest.TestCase):
    def test_true_pred(self):
        tr1 = TemporalRange(1, 2, 1)
        tr2 = TemporalRange(5, 6, 1)
        self.assertTrue(TruePred().compute(tr1, tr2))

    def test_false_pred(self):
        tr1 = TemporalRange(1, 2, 1)
        tr2 = TemporalRange(5, 6, 1)
        self.assertFalse(FalsePred().compute(tr1, tr2))

    def test_before(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertTrue(Before().compute(tr1, tr2))
        self.assertFalse(Before().compute(tr2, tr1))

        tr3 = TemporalRange(2., 4., 1)
        self.assertTrue(Before().compute(tr1, tr3))

    def test_before_range(self):
        pred = Before(10., 20.)
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(12., 15., 1)
        tr4 = TemporalRange(22.5, 25., 1)
        self.assertTrue(pred.compute(tr1, tr3))
        self.assertFalse(pred.compute(tr1, tr4))
        self.assertTrue(pred.compute(tr2, tr4))

    def test_after(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(After().compute(tr1, tr2))
        self.assertTrue(After().compute(tr2, tr1))

        tr3 = TemporalRange(2., 4., 1)
        self.assertTrue(After().compute(tr3, tr1))
            
    def test_after_range(self):
        pred = After(10., 20.)
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(12., 15., 1)
        tr4 = TemporalRange(22.5, 25., 1)
        self.assertTrue(pred.compute(tr3, tr1))
        self.assertFalse(pred.compute(tr4, tr1))
        self.assertTrue(pred.compute(tr4, tr2))

    def test_overlaps(self):
        pred = Overlaps()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)

        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))

        tr3 = TemporalRange(3.5, 4.5, 1)
        tr4 = TemporalRange(2.5, 3.5, 1)
        self.assertTrue(pred.compute(tr2, tr3))
        self.assertTrue(pred.compute(tr2, tr4))

        tr5 = TemporalRange(2.5, 4.5, 1)
        tr6 = TemporalRange(3.3, 3.6, 1)
        self.assertTrue(pred.compute(tr2, tr5))
        self.assertTrue(pred.compute(tr2, tr6))

        tr7 = TemporalRange(3., 3.5, 1)
        tr8 = TemporalRange(3., 4.5, 1)
        self.assertTrue(pred.compute(tr2, tr7))
        self.assertTrue(pred.compute(tr2, tr8))

        tr9 = TemporalRange(3.3, 4., 1)
        tr10 = TemporalRange(2.1, 4., 1)
        self.assertTrue(pred.compute(tr2, tr9))
        self.assertTrue(pred.compute(tr2, tr10))

        tr11 = TemporalRange(2.3, 3., 1)
        tr12 = TemporalRange(4., 4.5, 1)
        self.assertFalse(pred.compute(tr2, tr11))
        self.assertFalse(pred.compute(tr2, tr12))

        self.assertTrue(pred.compute(tr2, tr2))

    def test_overlapsbefore(self):
        pred = OverlapsBefore()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_overlapsafter(self):
        pred = OverlapsAfter()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertTrue(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_starts(self):
        pred = Starts()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertTrue(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_startsinv(self):
        pred = StartsInv()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertTrue(pred.compute(tr2, tr4))

    def test_finishes(self):
        pred = Finishes()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertTrue(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_finishesinv(self):
        pred = FinishesInv()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertTrue(pred.compute(tr2, tr4))

    def test_during(self):
        pred = During()
        tr1 = TemporalRange(3., 3.5, 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_duringinv(self):
        pred = DuringInv()
        tr1 = TemporalRange(3., 3.5, 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertTrue(pred.compute(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_meetsbefore(self):
        pred = MeetsBefore()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred.compute(tr1, tr2))
        self.assertFalse(pred.compute(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_meetsafter(self):
        pred = MeetsAfter()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred.compute(tr1, tr2))
        self.assertTrue(pred.compute(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr2, tr4))

    def test_equal(self):
        pred = Equal()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        tr3 = TemporalRange(2., 4., 5)
        self.assertTrue(pred.compute(tr1, tr1))
        self.assertTrue(pred.compute(tr2, tr2))
        self.assertTrue(pred.compute(tr3, tr3))
        self.assertTrue(pred.compute(tr2, tr3))
        self.assertFalse(pred.compute(tr1, tr2))

    def test_and(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1., 2., 3)
        self.assertTrue(And(Equal(), Overlaps()).compute(tr1, tr2))
        self.assertFalse(And(Equal(), OverlapsBefore()).compute(tr1, tr2))
        self.assertFalse(And(OverlapsBefore(), Equal()).compute(tr1, tr2))
        self.assertFalse(And(OverlapsBefore(), OverlapsAfter()).compute(tr1, tr2))

    def test_or(self):
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)

        self.assertTrue(Or(Before(), OverlapsBefore()).compute(tr1, tr2))
        self.assertFalse(Or(Before(), FalsePred()).compute(tr1, tr2))
        self.assertTrue(Or(OverlapsBefore(), Overlaps()).compute(tr1, tr2))
        self.assertTrue(Or(OverlapsBefore(), Before()).compute(tr1, tr2))
