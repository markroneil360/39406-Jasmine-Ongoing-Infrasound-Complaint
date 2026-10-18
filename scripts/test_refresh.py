import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from obspy import Trace,Stream,UTCDateTime
from engine import analyze,events,merge_rows,spectral,summarize,build_products
import engine
import refresh


class AnalysisTests(unittest.TestCase):
    def trace(self,station="R19BB",start=0,seconds=60,hz=6):
        tr=Trace((1000*np.sin(2*np.pi*hz*np.arange(round(seconds*100))/100)).astype(np.int32))
        tr.stats.update(dict(network="AM",station=station,location="00",channel="HDF",
                             sampling_rate=100,starttime=UTCDateTime(start)))
        return tr

    def test_full_minute(self):
        rows,_=analyze(Stream([self.trace()]),"HDF",0,60)
        self.assertEqual(rows[0]["dominant_band"],"4-8")
        self.assertEqual(rows[0]["peak_hz"],6)

    def test_gap_is_partial_not_zero(self):
        rows,audit=analyze(Stream([self.trace(seconds=59)]),"HDF",0,60)
        self.assertEqual(rows[0]["quality"],"partial")
        self.assertEqual(rows[0]["valid_samples"],5900)
        self.assertEqual(rows[0]["rms_counts"],"")
        self.assertEqual(rows[0]["fragment_peak_hz"],6)
        self.assertEqual(audit["valid_samples"],5900)

    def test_foreign_station_rejected(self):
        with self.assertRaises(ValueError):
            analyze(Stream([self.trace(station="R6E8A")]),"HDF",0,60)

    def test_overlap_conflict_excluded_not_whole_file(self):
        a,b=self.trace(),self.trace();b.data[10]+=1
        rows,audit=analyze(Stream([a,b]),"HDF",0,60)
        self.assertEqual(rows[0]["quality"],"conflict")
        self.assertEqual(audit["conflict_samples"],1)
        self.assertEqual(audit["valid_samples"],5999)

    def test_identical_overlap_once(self):
        a=self.trace()
        rows,audit=analyze(Stream([a,a.copy()]),"HDF",0,60)
        self.assertEqual(len(rows),1)
        self.assertEqual(audit["valid_samples"],6000)

    def test_gap_breaks_runs(self):
        a,_=analyze(Stream([self.trace(seconds=600),self.trace(start=660,seconds=600)]),"HDF",0,1260)
        self.assertEqual([r["minutes"] for r in events(a,{"4-8"})],[10,10])
        self.assertEqual(summarize(a,0,1260)["narrow"]["events_ge_10"],2)

    def test_flatline_is_recorded_not_frequency(self):
        a=self.trace();a.data[:]=0
        rows,audit=analyze(Stream([a]),"HDF",0,60)
        self.assertEqual(rows[0]["quality"],"flatline")
        self.assertEqual(rows[0]["dominant_band"],"")
        self.assertEqual(audit["valid_samples"],6000)

    def test_fractional_phase(self):
        rows,_=analyze(Stream([self.trace(start=.003999)]),"HDF",0,60)
        self.assertEqual(rows[0]["quality"],"complete")

    def test_boundary_join(self):
        a=self.trace(seconds=30);b=self.trace(start=30,seconds=30)
        rows,_=analyze(Stream([a,b]),"HDF",0,60)
        self.assertEqual(rows[0]["quality"],"complete")

    def test_all_bands(self):
        for hz,band in [(2,"1-4"),(6,"4-8"),(12,"8-16"),(18,"16-20")]:
            self.assertEqual(spectral(self.trace(hz=hz).data)[0],band)

    def test_merge_duplicate_and_preserve(self):
        full,_=analyze(Stream([self.trace()]),"HDF",0,60)
        part,_=analyze(Stream([self.trace(seconds=20)]),"HDF",0,60)
        self.assertEqual(len(merge_rows(full,full)),1)
        self.assertEqual(merge_rows(full,part)[0]["quality"],"complete")

    def test_empty_window_unknown(self):
        s=summarize([],0,60)
        self.assertIsNone(s["channels"]["HDF"]["band_share_pct"]["4-8"])
        self.assertIsNone(s["narrow"]["longest"])

    def test_different_partial_cannot_replace_evidence(self):
        old,_=analyze(Stream([self.trace(seconds=20)]),"HDF",0,60)
        new,_=analyze(Stream([self.trace(start=25,seconds=30)]),"HDF",0,60)
        with self.assertRaises(ValueError):
            merge_rows(old,new)

    def test_same_partial_counts_from_new_source_need_reconciliation(self):
        old,_=analyze(Stream([self.trace(seconds=20)]),"HDF",0,60)
        new=[dict(old[0],source_ids="different-waveform")]
        with self.assertRaises(ValueError):
            merge_rows(old,new)

    def test_unavailable_feed_preserves_direct_archive(self):
        rows,_=analyze(Stream([self.trace()]),"HDF",0,60)
        sources=[dict(source_id="test",identities=["AM.R19BB.00.HDF"],
                      first_sample_utc="1970-01-01T00:00:00Z",
                      last_sample_utc="1970-01-01T00:00:59.990000Z")]
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)
            with patch.object(engine,"DATA",data),patch.object(refresh,"DATA",data):
                build_products(rows,sources,{"state":"test"})
                original=(data/"minutes.csv").read_bytes()
                with patch.object(refresh.urllib.request,"urlopen",side_effect=ValueError("No data test")):
                    refresh.main()
                self.assertEqual(original,(data/"minutes.csv").read_bytes())
                status=json.loads((data/"status.json").read_text())
                self.assertEqual(status["latest_documented_samples"]["HDF"],sources[0]["last_sample_utc"])


if __name__=="__main__":
    unittest.main()
