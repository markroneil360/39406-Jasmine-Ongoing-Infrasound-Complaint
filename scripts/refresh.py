#!/usr/bin/env python3
"""R19BB-only public acquisition. Missing samples never become measurements."""
import csv
import hashlib
import io
import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from obspy import UTCDateTime, read

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BASE = "https://data.raspberryshake.org/fdsnws/dataselect/1/query"
STATION = "AM.R19BB.00"
FIELDS = ["channel", "minute_utc", "rms_counts", "peak_hz", "band_4_8"]


def iso(t):
    return datetime.fromtimestamp(float(t), timezone.utc).isoformat().replace("+00:00", "Z")


def analyze(stream, channel, start, end):
    """Reject foreign IDs, irregular grids, and conflicting overlaps."""
    if not stream or any(tr.id != f"{STATION}.{channel}" for tr in stream):
        raise ValueError("Missing or unexpected MiniSEED channel identity")
    for tr in stream:
        if tr.stats.sampling_rate != 100:
            raise ValueError("Expected 100 Hz sampling")
    # Fill a requested half-open window; masks and gaps stay NaN.
    x = np.full(round((end-start)*100), np.nan)
    latest = None
    for tr in stream:
        offset = (float(tr.stats.starttime)-start)*100
        if abs(offset-round(offset)) > .01:
            raise ValueError("Sample timing is not aligned to the 100 Hz grid")
        offset = round(offset)
        a, b = max(0, offset), min(len(x), offset+len(tr.data))
        if b <= a:
            continue
        values = np.asarray(np.ma.filled(tr.data.astype(float), np.nan))[a-offset:b-offset]
        old = x[a:b]
        both = np.isfinite(old) & np.isfinite(values)
        if np.any(old[both] != values[both]):
            raise ValueError("Conflicting overlapping waveform samples")
        valid = np.isfinite(values)
        old[valid] = values[valid]
        if valid.any():
            latest = max(latest or 0, start+(a+np.flatnonzero(valid)[-1])/100)
    rows = []
    freq = np.fft.rfftfreq(6000, .01)
    scope = (freq >= 1) & (freq <= 20)
    for index in range(0, len(x)-5999, 6000):
        minute = x[index:index+6000]
        if not np.isfinite(minute).all():
            continue
        centered = minute-minute.mean()
        rms = float(np.sqrt(np.mean(centered**2)))
        if rms == 0:
            # Flatlining is not interpreted as a valid frequency measurement.
            continue
        power = np.abs(np.fft.rfft(centered*np.hanning(6000)))**2
        peak = float(freq[scope][np.argmax(power[scope])])
        rows.append(dict(channel=channel, minute_utc=iso(start+index/100),
                         rms_counts=round(rms, 6), peak_hz=round(peak, 6),
                         band_4_8=int(channel == "HDF" and 4 <= peak <= 8)))
    return rows, latest


def fetch(channel, start, end):
    url = f"{BASE}?net=AM&sta=R19BB&loc=00&cha={channel}&start={iso(start)}&end={iso(end)}&format=miniseed"
    result = dict(channel=channel, source_url=url, complete_minutes=0, latest_sample_utc=None)
    try:
        request = urllib.request.Request(url, headers={"User-Agent":"R19BB-dashboard/1.0"})
        with urllib.request.urlopen(request, timeout=150) as response:
            if response.status == 204:
                raise ValueError("No data returned (HTTP 204)")
            raw = response.read(100_000_001)
        if len(raw)>100_000_000:
            raise ValueError("Response exceeds 100 MB safety limit")
        result["sha256"] = hashlib.sha256(raw).hexdigest()
        result["bytes"] = len(raw)
        rows, latest = analyze(read(io.BytesIO(raw), format="MSEED"), channel, start, end)
        result.update(identity_verified=True, complete_minutes=len(rows), latest_sample_utc=iso(latest) if latest else None)
        return rows, result
    except Exception as error:
        result["error"] = str(error)[:300]
        return [], result


def summarize(rows, start, end):
    selected = [r for r in rows if start <= float(UTCDateTime(r["minute_utc"])) < end]
    out = {}
    for channel in ("HDF", "EHZ"):
        channel_rows = sorted((r for r in selected if r["channel"]==channel), key=lambda r:r["minute_utc"])
        longest = run = band = 0
        previous = None
        for r in channel_rows:
            t = float(UTCDateTime(r["minute_utc"]))
            if int(r["band_4_8"]):
                run = run+1 if previous is not None and t-previous==60 else 1
                band += 1
            else:
                run = 0
            longest = max(longest, run)
            previous = t
        expected = round((end-start)/60)
        out[channel] = dict(complete_minutes=len(channel_rows), expected_minutes=expected,
                            coverage_pct=round(100*len(channel_rows)/expected,3) if expected else None,
                            band_minutes=band, longest_run_minutes=longest)
    return dict(start=iso(start), end=iso(end), channels=out)


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


def main():
    DATA.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).timestamp()
    end = math.floor((now-1800)/60)*60
    start = end-86400
    archive = DATA/"minutes.csv"
    old = list(csv.DictReader(archive.open())) if archive.exists() else []
    records = {(r["channel"],r["minute_utc"]):r for r in old}
    attempts = []
    for channel in ("HDF","EHZ"):
        rows, result = fetch(channel, start, end)
        conflicts = [r for r in rows if (r["channel"],r["minute_utc"]) in records and
                     any(str(records[(r["channel"],r["minute_utc"])][k]) != str(r[k]) for k in FIELDS)]
        if conflicts:
            result["error"] = f"{len(conflicts)} minute conflicts; prior archive retained, channel update rejected"
            result["complete_minutes"] = 0
        else:
            records.update({(r["channel"],r["minute_utc"]):r for r in rows})
        attempts.append(result)
    rows = sorted(records.values(), key=lambda r:(r["minute_utc"],r["channel"]))
    temporary = archive.with_suffix(".tmp")
    with temporary.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS);writer.writeheader();writer.writerows(rows)
    temporary.replace(archive)
    recent = [a for a in attempts if not a.get("error") and a["latest_sample_utc"] and
              now-float(UTCDateTime(a["latest_sample_utc"])) <= 5400 and a["complete_minutes"] > 0]
    state = "Recent data received" if len(recent)==2 else "Partial acquisition" if recent else "Current acquisition unconfirmed"
    status = dict(station=STATION, generated_utc=iso(now), request_start=iso(start), request_end=iso(end),
                  state=state, note="Daily archive check, not live connectivity. Missing time is unknown. Allow 30 minutes for archive lag.",
                  channels=attempts, archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
    archive_start = min([float(UTCDateTime(r["minute_utc"])) for r in rows], default=start)
    hours = []
    hour_end = math.floor(end/3600)*3600
    for hour in range(int(hour_end-86400),int(hour_end),3600):
        s = summarize(rows,hour,hour+3600)
        hours.append(dict(start=iso(hour),channels={c:s["channels"][c]["complete_minutes"] for c in ("HDF","EHZ")}))
    summary = dict(station=STATION, generated_utc=iso(now),
                   windows={"24h":summarize(rows,start,end),"7d":summarize(rows,end-7*86400,end),
                            "all":summarize(rows,archive_start,end)}, hours=hours)
    write_json(DATA/"status.json", status)
    write_json(DATA/"summary.json", summary)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
