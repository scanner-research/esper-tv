from esper.temporal_predicates import *
from esper.temporal_rangelist import TemporalRange
import unittest

class TestTemporalPredicates(unittest.TestCase):
    def test_true_pred(self):
        tr1 = TemporalRange(1, 2, 1)
        tr2 = TemporalRange(5, 6, 1)
        self.assertTrue(true_pred()(tr1, tr2))

    def test_false_pred(self):
        tr1 = TemporalRange(1, 2, 1)
        tr2 = TemporalRange(5, 6, 1)
        self.assertFalse(false_pred()(tr1, tr2))

    def test_before(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertTrue(before()(tr1, tr2))
        self.assertFalse(before()(tr2, tr1))

        tr3 = TemporalRange(2., 4., 1)
        self.assertTrue(before()(tr1, tr3))

    def test_before_range(self):
        pred = before(10., 20.)
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(12., 15., 1)
        tr4 = TemporalRange(22.5, 25., 1)
        self.assertTrue(pred(tr1, tr3))
        self.assertFalse(pred(tr1, tr4))
        self.assertTrue(pred(tr2, tr4))

    def test_after(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(after()(tr1, tr2))
        self.assertTrue(after()(tr2, tr1))

        tr3 = TemporalRange(2., 4., 1)
        self.assertTrue(after()(tr3, tr1))
            
    def test_after_range(self):
        pred = after(10., 20.)
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(12., 15., 1)
        tr4 = TemporalRange(22.5, 25., 1)
        self.assertTrue(pred(tr3, tr1))
        self.assertFalse(pred(tr4, tr1))
        self.assertTrue(pred(tr4, tr2))

    def test_overlaps(self):
        pred = overlaps()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(3., 4., 1)

        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))

        tr3 = TemporalRange(3.5, 4.5, 1)
        tr4 = TemporalRange(2.5, 3.5, 1)
        self.assertTrue(pred(tr2, tr3))
        self.assertTrue(pred(tr2, tr4))

        tr5 = TemporalRange(2.5, 4.5, 1)
        tr6 = TemporalRange(3.3, 3.6, 1)
        self.assertTrue(pred(tr2, tr5))
        self.assertTrue(pred(tr2, tr6))

        tr7 = TemporalRange(3., 3.5, 1)
        tr8 = TemporalRange(3., 4.5, 1)
        self.assertTrue(pred(tr2, tr7))
        self.assertTrue(pred(tr2, tr8))

        tr9 = TemporalRange(3.3, 4., 1)
        tr10 = TemporalRange(2.1, 4., 1)
        self.assertTrue(pred(tr2, tr9))
        self.assertTrue(pred(tr2, tr10))

        tr11 = TemporalRange(2.3, 3., 1)
        tr12 = TemporalRange(4., 4.5, 1)
        self.assertFalse(pred(tr2, tr11))
        self.assertFalse(pred(tr2, tr12))

        self.assertTrue(pred(tr2, tr2))

    def test_overlapsbefore(self):
        pred = overlaps_before()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_overlapsafter(self):
        pred = overlaps_after()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertTrue(pred(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_starts(self):
        pred = starts()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertTrue(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_startsinv(self):
        pred = starts_inv()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(2., 5., 1)
        tr4 = TemporalRange(2., 3., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertTrue(pred(tr2, tr4))

    def test_finishes(self):
        pred = finishes()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertTrue(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_finishesinv(self):
        pred = finishes_inv()
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))
        
        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertTrue(pred(tr2, tr4))

    def test_during(self):
        pred = during()
        tr1 = TemporalRange(3., 3.5, 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_duringinv(self):
        pred = during_inv()
        tr1 = TemporalRange(3., 3.5, 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertTrue(pred(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_meetsbefore(self):
        pred = meets_before()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertTrue(pred(tr1, tr2))
        self.assertFalse(pred(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_meetsafter(self):
        pred = meets_after()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        self.assertFalse(pred(tr1, tr2))
        self.assertTrue(pred(tr2, tr1))

        tr3 = TemporalRange(1., 4., 1)
        tr4 = TemporalRange(2.5, 4., 1)
        self.assertFalse(pred(tr2, tr3))
        self.assertFalse(pred(tr2, tr4))

    def test_equal(self):
        pred = equal()
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(2., 4., 1)
        tr3 = TemporalRange(2., 4., 5)
        self.assertTrue(pred(tr1, tr1))
        self.assertTrue(pred(tr2, tr2))
        self.assertTrue(pred(tr3, tr3))
        self.assertTrue(pred(tr2, tr3))
        self.assertFalse(pred(tr1, tr2))

    def test_and(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1., 2., 3)
        self.assertTrue(and_pred(equal(), overlaps())(tr1, tr2))
        self.assertFalse(and_pred(equal(), overlaps_before())(tr1, tr2))
        self.assertFalse(and_pred(overlaps_before(), equal())(tr1, tr2))
        self.assertFalse(and_pred(overlaps_before(), overlaps_after())(tr1, tr2))

    def test_or(self):
        tr1 = TemporalRange(1., 3., 1)
        tr2 = TemporalRange(2., 4., 1)

        self.assertTrue(or_pred(before(), overlaps_before())(tr1, tr2))
        self.assertFalse(or_pred(before(), false_pred())(tr1, tr2))
        self.assertTrue(or_pred(overlaps_before(), overlaps())(tr1, tr2))
        self.assertTrue(or_pred(overlaps_before(), before())(tr1, tr2))
