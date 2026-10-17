"""Fail closed on station mismatch, summary errors, or archive hash mismatch."""
import csv
import hashlib
import json
from refresh import DATA, STATION, summarize
from obspy import UTCDateTime

status=json.loads((DATA/"status.json").read_text())
summary=json.loads((DATA/"summary.json").read_text())
assert status["station"]==summary["station"]==STATION
assert hashlib.sha256((DATA/"minutes.csv").read_bytes()).hexdigest()==status["archive_sha256"]
rows=list(csv.DictReader((DATA/"minutes.csv").open()))
assert len(rows)==len({(r["channel"],r["minute_utc"]) for r in rows})
assert all(r["channel"] in ("HDF","EHZ") for r in rows)
for value in summary["windows"].values():
    assert value==summarize(rows,float(UTCDateTime(value["start"])),float(UTCDateTime(value["end"])))
print("PASS: R19BB identity, archive hash, unique minutes, and window recounts")
