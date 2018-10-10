from esper.temporal_predicates import *
from esper.temporal_rangelist import TemporalRange, TemporalRangeList
import unittest

class TestTemporalRange(unittest.TestCase):
    def test_minus(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)
        
        tr1minustr2 = tr1.minus(tr2)

        self.assertEqual(len(tr1minustr2), 1)
        self.assertEqual(tr1minustr2[0].__repr__(),
                "<Temporal Range start:1.0 end:1.5 label:1>")

        tr1minustr2 = tr1.minus(tr2, label_producer_fn=lambda x, y: y.label)

        self.assertEqual(len(tr1minustr2), 1)
        self.assertEqual(tr1minustr2[0].__repr__(),
                "<Temporal Range start:1.0 end:1.5 label:2>")

        tr3 = TemporalRange(1.3, 1.6, 5)

        tr1minustr3 = tr1.minus(tr3)
        self.assertEqual(len(tr1minustr3), 2)
        self.assertEqual(tr1minustr3[0].__repr__(),
                "<Temporal Range start:1.0 end:1.3 label:1>")
        self.assertEqual(tr1minustr3[1].__repr__(),
                "<Temporal Range start:1.6 end:2.0 label:1>")

        tr4 = TemporalRange(0., 5., 1)
        self.assertEqual(tr1.minus(tr4), [])

    def test_overlap(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)
        
        self.assertEqual(tr1.overlap(tr2).__repr__(),
                "<Temporal Range start:1.5 end:2.0 label:1>")
        self.assertEqual(tr1.overlap(tr2,
            label_producer_fn=lambda x, y: y.label).__repr__(),
                "<Temporal Range start:1.5 end:2.0 label:2>")

        tr3 = TemporalRange(1.3, 1.6, 5)

        self.assertEqual(tr1.overlap(tr3).__repr__(),
                "<Temporal Range start:1.3 end:1.6 label:1>")

        tr4 = TemporalRange(0., 5., 1)

        self.assertEqual(tr1.overlap(tr4).__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")

    def test_merge(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)
        
        self.assertEqual(tr1.merge(tr2).__repr__(),
                "<Temporal Range start:1.0 end:2.5 label:1>")
        self.assertEqual(tr1.merge(tr2,
            label_producer_fn=lambda x, y: y.label).__repr__(),
                "<Temporal Range start:1.0 end:2.5 label:2>")

        tr3 = TemporalRange(5., 7., 1)
        self.assertEqual(tr1.merge(tr3).__repr__(),
                "<Temporal Range start:1.0 end:7.0 label:1>")

        tr4 = TemporalRange(0., 0.5, 1)
        self.assertEqual(tr1.merge(tr4).__repr__(),
                "<Temporal Range start:0.0 end:2.0 label:1>")

class TemporalRangeListTest(unittest.TestCase):
    def test_init(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)

        trl1 = TemporalRangeList([tr1, tr2])
        self.assertEqual(trl1.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trl1.trs[1].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

        trl1 = TemporalRangeList([tr2, tr1])
        self.assertEqual(trl1.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trl1.trs[1].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

    def test_set_union(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)

        trl1 = TemporalRangeList([tr1])
        trl2 = TemporalRangeList([tr2])

        trlu = trl1.set_union(trl2)
        self.assertEqual(trlu.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trlu.trs[1].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

        trlu = trl2.set_union(trl1)
        self.assertEqual(trlu.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trlu.trs[1].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

    def test_coalesce(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)

        trl1 = TemporalRangeList([tr1, tr2])
        trlcoalesced = trl1.coalesce()
        trlcoalesced_samelabel = trl1.coalesce(require_same_label=True)

        self.assertEqual(len(trlcoalesced.trs), 1)
        self.assertEqual(trlcoalesced.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.5 label:1>")

        self.assertEqual(len(trlcoalesced_samelabel.trs), 2)
        self.assertEqual(trlcoalesced_samelabel.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trlcoalesced_samelabel.trs[1].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

    def test_dilate(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)

        trl1 = TemporalRangeList([tr1, tr2]).dilate(0.2)
        self.assertEqual(trl1.trs[0].__repr__(),
                "<Temporal Range start:0.8 end:2.2 label:1>")
        self.assertEqual(trl1.trs[1].__repr__(),
                "<Temporal Range start:1.3 end:2.7 label:2>")

    def test_filter(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 2.5, 2)

        trl1 = TemporalRangeList([tr1, tr2])

        trl1 = trl1.filter(lambda tr: tr.start > 1.1)
        self.assertEqual(len(trl1.trs), 1)
        self.assertEqual(trl1.trs[0].__repr__(),
                "<Temporal Range start:1.5 end:2.5 label:2>")

    def test_filter_length(self):
        tr1 = TemporalRange(1., 2., 1)
        tr2 = TemporalRange(1.5, 3.5, 2)

        trl1 = TemporalRangeList([tr1, tr2])

        trl1 = trl1.filter_length(min_length=1.1)
        self.assertEqual(len(trl1.trs), 1)
        self.assertEqual(trl1.trs[0].__repr__(),
                "<Temporal Range start:1.5 end:3.5 label:2>")

        trl1 = trl1.filter_length(max_length=1.8)
        self.assertEqual(len(trl1.trs), 0)

    def test_filter_against(self):
        trlong1 = TemporalRange(1., 10., 1)
        trlong2 = TemporalRange(3., 15., 2)

        trshort1 = TemporalRange(2., 2.5, 3)
        trshort2 = TemporalRange(2., 2.7, 4)
        trshort3 = TemporalRange(2.9, 3.5, 5)

        trllong = TemporalRangeList([trlong2, trlong1])
        trlshort = TemporalRangeList([
            trshort1,
            trshort2,
            trshort3])

        trlfiltered = trllong.filter_against(trlshort, predicate=DuringInv())
        self.assertEqual(len(trlfiltered.trs), 1)
        self.assertEqual(trlfiltered.trs[0].__repr__(), trlong1.__repr__())

    def test_minus(self):
        trlong1 = TemporalRange(1., 10., 1)
        trlong2 = TemporalRange(3., 15., 2)

        trshort1 = TemporalRange(2., 2.5, 3)
        trshort2 = TemporalRange(2., 2.7, 4)
        trshort3 = TemporalRange(2.9, 3.5, 5)
        trshort4 = TemporalRange(5., 7., 6)
        trshort5 = TemporalRange(9., 12., 7)
        trshort6 = TemporalRange(14., 16., 8)

        trllong = TemporalRangeList([trlong2, trlong1])
        trlshort = TemporalRangeList([
            trshort2,
            trshort5,
            trshort3,
            trshort1,
            trshort4,
            trshort6])

        trlminusrec = trllong.minus(trlshort)
        self.assertEqual(len(trlminusrec.trs), 7)
        self.assertEqual(trlminusrec.trs[0].__repr__(),
            "<Temporal Range start:1.0 end:2.0 label:1>")
        self.assertEqual(trlminusrec.trs[1].__repr__(),
            "<Temporal Range start:2.7 end:2.9 label:1>")
        self.assertEqual(trlminusrec.trs[2].__repr__(),
            "<Temporal Range start:3.5 end:5.0 label:1>")
        self.assertEqual(trlminusrec.trs[3].__repr__(),
            "<Temporal Range start:3.5 end:5.0 label:2>")
        self.assertEqual(trlminusrec.trs[4].__repr__(),
            "<Temporal Range start:7.0 end:9.0 label:1>")
        self.assertEqual(trlminusrec.trs[5].__repr__(),
            "<Temporal Range start:7.0 end:9.0 label:2>")
        self.assertEqual(trlminusrec.trs[6].__repr__(),
            "<Temporal Range start:12.0 end:14.0 label:2>")

        trlminusnonrec = trllong.minus(trlshort, recursive_diff = False)
        self.assertEqual(len(trlminusnonrec.trs), 15)

        trlminusrec = trllong.minus(trlshort,
                label_producer_fn=lambda x, y: y.label)
        self.assertEqual(len(trlminusrec.trs), 7)
        self.assertEqual(trlminusrec.trs[0].__repr__(),
            "<Temporal Range start:1.0 end:2.0 label:3>")
        self.assertEqual(trlminusrec.trs[1].__repr__(),
            "<Temporal Range start:2.7 end:2.9 label:4>")
        self.assertEqual(trlminusrec.trs[2].__repr__(),
            "<Temporal Range start:3.5 end:5.0 label:5>")
        self.assertEqual(trlminusrec.trs[3].__repr__(),
            "<Temporal Range start:3.5 end:5.0 label:5>")
        self.assertEqual(trlminusrec.trs[4].__repr__(),
            "<Temporal Range start:7.0 end:9.0 label:6>")
        self.assertEqual(trlminusrec.trs[5].__repr__(),
            "<Temporal Range start:7.0 end:9.0 label:6>")
        self.assertEqual(trlminusrec.trs[6].__repr__(),
            "<Temporal Range start:12.0 end:14.0 label:7>")

        trlminusrec = trllong.minus(trlshort, predicate=OverlapsBefore())
        self.assertEqual(len(trlminusrec.trs), 2)
        self.assertEqual(trlminusrec.trs[0].__repr__(),
            "<Temporal Range start:1.0 end:9.0 label:1>")
        self.assertEqual(trlminusrec.trs[1].__repr__(),
            "<Temporal Range start:3.0 end:14.0 label:2>")

    def test_minus_against_nothing(self):
        trlong1 = TemporalRange(1., 10., 1)
        trlong2 = TemporalRange(3., 15., 2)
        
        trllong = TemporalRangeList([trlong2, trlong1])

        trshort1 = TemporalRange(20., 20.5, 3)
        trlshort = TemporalRangeList([trshort1])

        trlminusrec = trllong.minus(trlshort)
        self.assertEqual(len(trlminusrec.trs), 2)
        self.assertEqual(trlminusrec.trs[0].__repr__(),
            "<Temporal Range start:1.0 end:10.0 label:1>")
        self.assertEqual(trlminusrec.trs[1].__repr__(),
            "<Temporal Range start:3.0 end:15.0 label:2>")


    def test_overlaps(self):
        tra1 = TemporalRange(1., 25., 1)
        tra2 = TemporalRange(52., 55., 1)
        tra3 = TemporalRange(100., 110., 1)
        tra4 = TemporalRange(200., 210., 1)
        trb1 = TemporalRange(12., 26., 2)
        trb2 = TemporalRange(50., 53., 2)
        trb3 = TemporalRange(101., 105., 2)
        trb4 = TemporalRange(190., 220., 2)

        trla = TemporalRangeList([tra2, tra3, tra1, tra4])
        trlb = TemporalRangeList([trb2, trb3, trb1, trb4])

        trloverlap = trla.overlaps(trlb)
        self.assertEqual(len(trloverlap.trs), 4)
        self.assertEqual(trloverlap.trs[0].__repr__(),
                "<Temporal Range start:12.0 end:25.0 label:1>")
        self.assertEqual(trloverlap.trs[1].__repr__(),
                "<Temporal Range start:52.0 end:53.0 label:1>")
        self.assertEqual(trloverlap.trs[2].__repr__(),
                "<Temporal Range start:101.0 end:105.0 label:1>")
        self.assertEqual(trloverlap.trs[3].__repr__(),
                "<Temporal Range start:200.0 end:210.0 label:1>")

        trloverlap = trlb.overlaps(trla)
        self.assertEqual(len(trloverlap.trs), 4)
        self.assertEqual(trloverlap.trs[0].__repr__(),
                "<Temporal Range start:12.0 end:25.0 label:2>")
        self.assertEqual(trloverlap.trs[1].__repr__(),
                "<Temporal Range start:52.0 end:53.0 label:2>")
        self.assertEqual(trloverlap.trs[2].__repr__(),
                "<Temporal Range start:101.0 end:105.0 label:2>")
        self.assertEqual(trloverlap.trs[3].__repr__(),
                "<Temporal Range start:200.0 end:210.0 label:2>")

        trloverlap = trla.overlaps(trlb, predicate=OverlapsBefore())
        self.assertEqual(len(trloverlap.trs), 1)
        self.assertEqual(trloverlap.trs[0].__repr__(),
                "<Temporal Range start:12.0 end:25.0 label:1>")

        trloverlap = trla.overlaps(trlb, predicate=OverlapsBefore(),
                label_producer_fn=lambda x, y: y.label)
        self.assertEqual(len(trloverlap.trs), 1)
        self.assertEqual(trloverlap.trs[0].__repr__(),
                "<Temporal Range start:12.0 end:25.0 label:2>")

    def test_merge(self):
        tra1 = TemporalRange(1., 25., 1)
        tra2 = TemporalRange(52., 55., 1)
        tra3 = TemporalRange(100., 110., 1)
        tra4 = TemporalRange(200., 210., 1)
        trb1 = TemporalRange(12., 26., 2)
        trb2 = TemporalRange(50., 53., 2)
        trb3 = TemporalRange(101., 105., 2)
        trb4 = TemporalRange(190., 220., 2)

        trla = TemporalRangeList([tra2, tra3, tra1, tra4])
        trlb = TemporalRangeList([trb2, trb3, trb1, trb4])

        trlmerge = trla.merge(trlb, predicate=Overlaps())
        self.assertEqual(len(trlmerge.trs), 4)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:26.0 label:1>")
        self.assertEqual(trlmerge.trs[1].__repr__(),
                "<Temporal Range start:50.0 end:55.0 label:1>")
        self.assertEqual(trlmerge.trs[2].__repr__(),
                "<Temporal Range start:100.0 end:110.0 label:1>")
        self.assertEqual(trlmerge.trs[3].__repr__(),
                "<Temporal Range start:190.0 end:220.0 label:1>")

        trlmerge = trlb.merge(trla, predicate=Overlaps())
        self.assertEqual(len(trlmerge.trs), 4)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:26.0 label:2>")
        self.assertEqual(trlmerge.trs[1].__repr__(),
                "<Temporal Range start:50.0 end:55.0 label:2>")
        self.assertEqual(trlmerge.trs[2].__repr__(),
                "<Temporal Range start:100.0 end:110.0 label:2>")
        self.assertEqual(trlmerge.trs[3].__repr__(),
                "<Temporal Range start:190.0 end:220.0 label:2>")

        trlmerge = trla.merge(trlb, predicate=OverlapsBefore())
        self.assertEqual(len(trlmerge.trs), 1)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:26.0 label:1>")

        trlmerge = trla.merge(trlb, predicate=OverlapsBefore(),
                label_producer_fn=lambda x, y: y.label)
        self.assertEqual(len(trlmerge.trs), 1)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:26.0 label:2>")

        tra1 = TemporalRange(1., 25., 1)
        tra2 = TemporalRange(52., 55., 1)
        tra3 = TemporalRange(100., 110., 1)
        tra4 = TemporalRange(200., 210., 1)
        trb1 = TemporalRange(25., 31., 2)
        trb2 = TemporalRange(56., 90., 2)
        trb3 = TemporalRange(101., 105., 2)
        trb4 = TemporalRange(190., 220., 2)

        trla = TemporalRangeList([tra2, tra3, tra1, tra4])
        trlb = TemporalRangeList([trb2, trb3, trb1, trb4])

        trlmerge = trla.merge(trlb, predicate=MeetsBefore())
        self.assertEqual(len(trlmerge.trs), 1)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:31.0 label:1>")

        trlmerge = trla.merge(trlb, predicate=Before(0.1, 10.0))
        self.assertEqual(len(trlmerge.trs), 1)
        self.assertEqual(trlmerge.trs[0].__repr__(),
                "<Temporal Range start:52.0 end:90.0 label:1>")

    def test_cross(self):
        tra1 = TemporalRange(1., 25., 1)
        tra2 = TemporalRange(52., 55., 1)
        tra3 = TemporalRange(100., 110., 1)
        tra4 = TemporalRange(200., 210., 1)
        trb1 = TemporalRange(12., 26., 2)
        trb2 = TemporalRange(50., 53., 2)
        trb3 = TemporalRange(101., 105., 2)
        trb4 = TemporalRange(190., 220., 2)

        trla = TemporalRangeList([tra2, tra3, tra1, tra4])
        trlb = TemporalRangeList([trb2, trb3, trb1, trb4])

        def myudf(x, y):
            if x.start == 1. and y.start == 12.:
                return [TemporalRange(1., 100., 25)]
            return []

        trludf = trla.cross_udf(trlb, myudf)
        self.assertEqual(len(trludf.trs), 1)
        self.assertEqual(trludf.trs[0].__repr__(),
                "<Temporal Range start:1.0 end:100.0 label:25>")
