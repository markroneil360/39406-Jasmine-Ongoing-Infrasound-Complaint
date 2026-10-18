"""R19BB Welch analysis, matching Detroit's four-band classification.

No zero filling, resampling, interpolation, or bridging of missing minutes.
Raw samples are assigned to the nearest 100 Hz clock tick (<=5 ms).
"""
import csv
import hashlib
import json
import math
import warnings
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from functools import lru_cache

import numpy as np
import scipy
from obspy import Stream, UTCDateTime, read
from scipy.signal import welch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
STATION = "AM.R19BB.00"
METHOD = "detroit-welch-8s-50pct-mean-band-v2"
BANDS = (("1-4", 1., 4.), ("4-8", 4., 8.), ("8-16", 8., 16.), ("16-20", 16., 20.))
FIELDS = ["channel", "minute_utc", "valid_samples", "conflict_samples", "quality",
          "rms_counts", "peak_hz", "dominant_band", "mean_psd_1_4",
          "mean_psd_4_8", "mean_psd_8_16", "mean_psd_16_20",
          "fragment_peak_hz", "fragment_band", "fragment_seconds", "source_ids"]


@lru_cache(maxsize=1000000)
def epoch(value):
    return float(UTCDateTime(value))


def iso(value):
    return datetime.fromtimestamp(float(value), timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    tmp.replace(path)


def write_csv(path, rows, fields=FIELDS):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields,lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def read_csv(name="observations.csv"):
    path = DATA / name
    if not path.exists():
        return []
    with path.open() as handle:
        return list(csv.DictReader(handle))


def spectral(x):
    f, p = welch(x, fs=100, window="hann", nperseg=800, noverlap=400,
                 detrend="constant", scaling="density")
    means = [float(np.mean(p[(f >= lo) & ((f <= hi) if j == 3 else (f < hi))]))
             for j, (_, lo, hi) in enumerate(BANDS)]
    scope = (f >= 1) & (f <= 20)
    if not max(means) > 0:
        return None, None, means
    return BANDS[int(np.argmax(means))][0], float(f[scope][np.argmax(p[scope])]), means


def contiguous(mask):
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def decode(raw, name, source_kind):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        stream = read(raw, format="MSEED")
    identities = sorted({t.id for t in stream})
    if not identities or any(x not in (STATION+".HDF", STATION+".EHZ") for x in identities):
        raise ValueError("Unexpected station/channel identity: "+str(identities))
    if any(t.stats.sampling_rate != 100 for t in stream):
        raise ValueError("Unexpected sample rate; expected 100 Hz")
    payload = Path(raw).read_bytes() if isinstance(raw, (str, Path)) else raw.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    for trace in stream:
        trace.stats.source_id = digest
    receipt = dict(source_id=digest, name=name, source_kind=source_kind, bytes=len(payload),
                   identities=identities, sample_rate_hz=100,
                   decoded_samples=sum(t.stats.npts for t in stream),
                   first_sample_utc=iso(min(float(t.stats.starttime) for t in stream)),
                   last_sample_utc=iso(max(float(t.stats.endtime) for t in stream)),
                   traces=len(stream), decode_warnings=sorted(set(str(w.message) for w in caught)))
    return stream, receipt


def analyze(stream, channel, start=None, end=None):
    traces = [t for t in stream if t.id == STATION+"."+channel]
    if any(t.id != STATION+"."+channel for t in stream):
        raise ValueError("Foreign station/channel in analysis stream")
    if any(t.stats.sampling_rate != 100 for t in traces):
        raise ValueError("Expected 100 Hz")
    if not traces:
        return [], dict(channel=channel, valid_samples=0, conflict_samples=0, identical_overlap_samples=0)
    start = math.floor(min(float(t.stats.starttime) for t in traces)/60)*60 if start is None else start
    end = math.ceil((max(float(t.stats.endtime) for t in traces)+.01)/60)*60 if end is None else end
    rows = []
    totals = dict(channel=channel, valid_samples=0, conflict_samples=0, identical_overlap_samples=0,
                  max_tick_assignment_shift_ms=0.0, unavailable_intervals=[])
    for chunk in range(int(start), int(end), 86400):
        stop = min(chunk+86400, end)
        size = int(round((stop-chunk)*100))
        x = np.full(size, np.nan)
        conflict = np.zeros(size, dtype=bool)
        source_spans = []
        for trace in traces:
            offset_float = (float(trace.stats.starttime)-chunk)*100
            offset = round(offset_float)
            a, b = max(0, offset), min(size, offset+len(trace.data))
            if b <= a:
                continue
            totals["max_tick_assignment_shift_ms"] = max(
                totals["max_tick_assignment_shift_ms"], abs(offset-offset_float)*10)
            values = np.asarray(np.ma.filled(trace.data.astype(float), np.nan))[a-offset:b-offset]
            old = x[a:b]
            both = np.isfinite(old) & np.isfinite(values)
            disagree = both & (old != values)
            totals["identical_overlap_samples"] += int(np.count_nonzero(both & ~disagree))
            conflict[a:b] |= disagree
            valid = np.isfinite(values) & ~np.isfinite(old)
            old[valid] = values[valid]
            source_spans.append((a,b,getattr(trace.stats,"source_id","test")))
        x[conflict] = np.nan
        totals["conflict_samples"] += int(conflict.sum())
        totals["valid_samples"] += int(np.isfinite(x).sum())
        for a,b in contiguous(~np.isfinite(x)):
            gap=dict(start_utc=iso(chunk+a/100),end_exclusive_utc=iso(chunk+b/100),
                     seconds=round((b-a)/100,2))
            previous=totals["unavailable_intervals"][-1] if totals["unavailable_intervals"] else None
            if previous and previous["end_exclusive_utc"]==gap["start_utc"]:
                previous["end_exclusive_utc"]=gap["end_exclusive_utc"]
                previous["seconds"]=round(previous["seconds"]+gap["seconds"],2)
            else:
                totals["unavailable_intervals"].append(gap)
        for offset in range(0,size,6000):
            y = x[offset:offset+6000]
            valid = np.isfinite(y)
            n = int(valid.sum())
            conflicts = int(conflict[offset:offset+6000].sum())
            if n == 0 and conflicts == 0:
                continue  # Unobserved minutes are ABSENT, never zero-valued rows.
            row = dict.fromkeys(FIELDS, "")
            row.update(channel=channel, minute_utc=iso(chunk+offset/100), valid_samples=n,
                       conflict_samples=conflicts, quality="partial",
                       source_ids=";".join(sorted({s for a,b,s in source_spans if a<offset+6000 and b>offset})))
            if n == 6000:
                band, peak, means = spectral(y)
                row.update(quality="complete" if band else "flatline",
                           rms_counts=round(float(np.std(y)),6), dominant_band=band or "",
                           peak_hz=peak if peak is not None else "")
                for key,value in zip(FIELDS[8:12],means):
                    row[key]=round(value,9)
            elif n:
                # Supplementary only: longest contiguous observed fragment, never an event minute.
                a,b=max(contiguous(valid),key=lambda pair:pair[1]-pair[0])
                row["fragment_seconds"]=round((b-a)/100,2)
                if b-a>=800:
                    band,peak,_=spectral(y[a:b])
                    row.update(fragment_band=band or "",fragment_peak_hz=peak if peak is not None else "")
            if conflicts:
                row["quality"]="conflict"
            rows.append(row)
    totals["max_tick_assignment_shift_ms"]=round(totals["max_tick_assignment_shift_ms"],6)
    return rows,totals


def merge_rows(old, new):
    records={(r["channel"],r["minute_utc"]):r for r in old}
    for r in new:
        key=(r["channel"],r["minute_utc"])
        previous=records.get(key)
        if previous and previous["quality"] in ("complete","flatline") and r["quality"] in ("complete","flatline"):
            for field in FIELDS[4:12]:
                if str(previous[field]) != str(r[field]):
                    raise ValueError(f"Conflicting accepted minute {key}: {field}")
            r["source_ids"]=";".join(sorted(set(previous["source_ids"].split(";")+r["source_ids"].split(";"))))
        elif previous and previous["quality"] in ("partial","conflict") and r["quality"] in ("partial","conflict"):
            # Counts alone cannot prove subset/overlap identity for partials.
            if (set(previous["source_ids"].split(";")) != set(r["source_ids"].split(";"))
                    or any(str(previous[k]) != str(r[k]) for k in FIELDS[2:16])):
                raise ValueError(f"Partial minute {key} needs original-waveform reconciliation; previous evidence retained")
            r["source_ids"]=";".join(sorted(set(previous["source_ids"].split(";")+r["source_ids"].split(";"))))
        elif previous and int(previous["valid_samples"]) >= int(r["valid_samples"]):
            continue  # A complete minute already accounts for all sample ticks.
        records[key]=r
    return sorted(records.values(),key=lambda r:(r["minute_utc"],r["channel"]))


def events(rows, bands):
    chosen=sorted((r for r in rows if r["channel"]=="HDF" and r["quality"]=="complete"),key=lambda r:r["minute_utc"])
    runs=[]; current=[]
    def finish():
        if current:
            times=[epoch(r["minute_utc"]) for r in current]
            peaks=[float(r["peak_hz"]) for r in current]
            runs.append(dict(start_utc=iso(times[0]),end_exclusive_utc=iso(times[-1]+60),
                             minutes=len(current),peak_min_hz=min(peaks),peak_max_hz=max(peaks),
                             peak_median_hz=float(np.median(peaks)),
                             dominant_bands=dict(Counter(r["dominant_band"] for r in current))))
    for r in chosen:
        if r["dominant_band"] in bands:
            if current and epoch(r["minute_utc"])-epoch(current[-1]["minute_utc"])!=60:
                finish();current=[]
            current.append(r)
        else:
            finish();current=[]
    finish()
    return runs


def summarize(rows,start,end):
    selected=[r for r in rows if start<=epoch(r["minute_utc"])<end]
    channels={}
    for channel in ("HDF","EHZ"):
        all_rows=[r for r in selected if r["channel"]==channel]
        complete=[r for r in all_rows if r["quality"]=="complete"]
        counts={name:sum(r["dominant_band"]==name for r in complete) for name,_,_ in BANDS}
        valid=sum(int(r["valid_samples"]) for r in all_rows)
        seconds=valid/100
        channels[channel]=dict(documented_seconds=round(seconds,2),classified_minutes=len(complete),
                               partial_minutes=sum(r["quality"] in ("partial","conflict") for r in all_rows),
                               flatline_minutes=sum(r["quality"]=="flatline" for r in all_rows),
                               missing_seconds=round(max(0,end-start-seconds),2),
                               classified_share_pct=round(100*len(complete)*60/seconds,4) if seconds else None,
                               sample_coverage_pct=round(100*seconds/(end-start),4) if end>start else None,
                               band_counts=counts,
                               band_share_pct={k:round(100*v/len(complete),4) if complete else None for k,v in counts.items()})
    runs=events(selected,{"4-8"});wide=events(selected,{"1-4","4-8"})
    return dict(start=iso(start),end=iso(end),channels=channels,
                narrow=dict(events_ge_10=sum(r["minutes"]>=10 for r in runs),
                            minutes_ge_10=sum(r["minutes"] for r in runs if r["minutes"]>=10),
                            longest=max(runs,key=lambda r:r["minutes"],default=None)),
                wide=dict(events_ge_10=sum(r["minutes"]>=10 for r in wide),
                          longest=max(wide,key=lambda r:r["minutes"],default=None)))


def build_products(rows,sources,status,ingestion_audit=None):
    DATA.mkdir(exist_ok=True)
    now=datetime.now(timezone.utc).timestamp()
    first=min([epoch(r["minute_utc"]) for r in rows],default=math.floor(now/60)*60)
    last=max([epoch(r["minute_utc"])+60 for r in rows],default=first)
    current_end=math.floor(now/60)*60
    complete=[r for r in rows if r["quality"]=="complete"]
    write_csv(DATA/"observations.csv",rows)
    write_csv(DATA/"minutes.csv",complete)
    windows={"all":summarize(rows,first,last),"24h":summarize(rows,current_end-86400,current_end),
             "7d":summarize(rows,current_end-7*86400,current_end)}
    days=[]
    for day in range(int(first//86400*86400),int(math.ceil(last/86400)*86400),86400):
        days.append(summarize(rows,day,day+86400))
    hourly=[]
    for hour in range(int(first//3600*3600),int(math.ceil(last/3600)*3600),3600):
        samples=[r for r in rows if hour<=epoch(r["minute_utc"])<hour+3600]
        item={"start":iso(hour),"channels":{}}
        for channel in ("HDF","EHZ"):
            cr=[r for r in samples if r["channel"]==channel]
            values=[float(r["rms_counts"]) for r in cr if r["quality"]=="complete"]
            item["channels"][channel]=dict(documented_seconds=round(sum(int(r["valid_samples"]) for r in cr)/100,2),
                                          rms_median_counts=float(np.median(values)) if values else None,
                                          complete_minutes=len(values))
        hourly.append(item)
    eventdoc=dict(station=STATION,method=METHOD,
                  narrow=events(rows,{"4-8"}),wide=events(rows,{"1-4","4-8"}))
    eventdoc["bands"]={name:events(rows,{name}) for name,_,_ in BANDS}
    write_json(DATA/"events.json",eventdoc)
    fields=["kind","start_utc","end_exclusive_utc","minutes","peak_min_hz","peak_max_hz","peak_median_hz"]
    write_csv(DATA/"events.csv",[{k:v for k,v in dict(kind=kind,**event).items() if k in fields}
                                for kind in ("narrow","wide") for event in eventdoc[kind]],fields)
    spectrum_rows=[r for r in complete if r["channel"]=="HDF"]
    summary=dict(station=STATION,method=METHOD,generated_utc=iso(now),windows=windows,days=days,hours=hourly,
                 peak_frequency_counts=dict(sorted(Counter(float(r["peak_hz"]) for r in spectrum_rows).items())),
                 method_description="Complete clock minutes; Welch Hann 8 s / 50% overlap; highest mean PSD band; primary 4–8 Hz events >=10 consecutive minutes.")
    write_json(DATA/"summary.json",summary)
    write_json(DATA/"sources.json",dict(station=STATION,method=METHOD,sources=sources))
    status.update(station=STATION,method=METHOD,generated_utc=iso(now),
                  archive_start_utc=iso(first),archive_end_exclusive_utc=iso(last),
                  latest_documented_samples={c:max([s["last_sample_utc"] for s in sources if STATION+"."+c in s["identities"]],default=None) for c in ("HDF","EHZ")},
                  archive_sha256=hashlib.sha256((DATA/"minutes.csv").read_bytes()).hexdigest(),
                  observations_sha256=hashlib.sha256((DATA/"observations.csv").read_bytes()).hexdigest())
    write_json(DATA/"status.json",status)
    if ingestion_audit is not None:
        write_json(DATA/"ingestion-audit.json",ingestion_audit)
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(DATA.iterdir()) if p.suffix in (".csv",".json") and p.name!="manifest.json"}
    write_json(DATA/"manifest.json",dict(station=STATION,method=METHOD,generated_utc=iso(now),
                                       numpy_version=np.__version__,scipy_version=scipy.__version__,files=hashes))
    return summary
