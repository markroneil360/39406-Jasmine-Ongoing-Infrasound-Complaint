import unittest
import numpy as np
from obspy import Trace, Stream, UTCDateTime
from refresh import analyze, summarize


class AnalysisTests(unittest.TestCase):
    def trace(self, station="R19BB", start=0, seconds=60):
        t = Trace((1000*np.sin(2*np.pi*6*np.arange(seconds*100)/100)).astype(np.int32))
        t.stats.update(dict(network="AM",station=station,location="00",channel="HDF",
                       sampling_rate=100,starttime=UTCDateTime(start)))
        return t

    def test_full_minute(self):
        rows, _ = analyze(Stream([self.trace()]),"HDF",0,60)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["peak_hz"],6)
        self.assertEqual(rows[0]["band_4_8"],1)

    def test_gap_not_counted(self):
        rows, _ = analyze(Stream([self.trace(seconds=59)]),"HDF",0,60)
        self.assertEqual(rows,[])

    def test_foreign_station_rejected(self):
        with self.assertRaises(ValueError):
            analyze(Stream([self.trace(station="R6E8A")]),"HDF",0,60)

    def test_overlap_conflict_rejected(self):
        a,b=self.trace(),self.trace()
        b.data[10]+=1
        with self.assertRaises(ValueError):
            analyze(Stream([a,b]),"HDF",0,60)

    def test_identical_overlap_allowed(self):
        a=self.trace()
        rows,_=analyze(Stream([a,a.copy()]),"HDF",0,60)
        self.assertEqual(len(rows),1)

    def test_gap_breaks_run(self):
        a,_=analyze(Stream([self.trace()]),"HDF",0,60)
        b,_=analyze(Stream([self.trace(start=120)]),"HDF",120,180)
        result=summarize(a+b,0,180)["channels"]["HDF"]
        self.assertEqual(result["longest_run_minutes"],1)
        self.assertAlmostEqual(result["coverage_pct"],66.667)

    def test_flatline_excluded(self):
        a=self.trace();a.data[:]=0
        rows,_=analyze(Stream([a]),"HDF",0,60)
        self.assertEqual(rows,[])


if __name__=="__main__":
    unittest.main()
