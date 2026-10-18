"""Recount summaries, verify all published hashes, identities and event gaps."""
import hashlib
import json
from engine import DATA, STATION, METHOD, read_csv, epoch, summarize, events


def validate():
    manifest=json.loads((DATA/"manifest.json").read_text())
    assert manifest["station"]==STATION and manifest["method"]==METHOD
    for name,digest in manifest["files"].items():
        assert hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest,name
    rows=read_csv()
    minutes=read_csv("minutes.csv")
    assert minutes==[r for r in rows if r["quality"]=="complete"]
    assert len(rows)==len({(r["channel"],r["minute_utc"]) for r in rows})
    sources=json.loads((DATA/"sources.json").read_text())["sources"]
    ids={s["source_id"] for s in sources}
    for r in rows:
        assert r["channel"] in ("HDF","EHZ")
        assert epoch(r["minute_utc"])%60==0
        assert 0<=int(r["valid_samples"])<=6000
        assert set(r["source_ids"].split(";"))<=ids
        if r["quality"]=="complete":
            assert int(r["valid_samples"])==6000 and not int(r["conflict_samples"])
            assert r["dominant_band"] in ("1-4","4-8","8-16","16-20")
        else:
            assert not r["dominant_band"] and not r["peak_hz"]
    summary=json.loads((DATA/"summary.json").read_text())
    for value in list(summary["windows"].values())+summary["days"]:
        assert value==summarize(rows,epoch(value["start"]),epoch(value["end"]))
    eventdoc=json.loads((DATA/"events.json").read_text())
    for kind,bands in [("narrow",{"4-8"}),("wide",{"1-4","4-8"})]:
        assert eventdoc[kind]==events(rows,bands)
        for event in eventdoc[kind]:
            assert epoch(event["end_exclusive_utc"])-epoch(event["start_utc"])==event["minutes"]*60
    print(f"PASS: {len(sources)} source receipts, {len(rows)} documented minute slots, {len(minutes)} complete classified minutes; hashes, uniqueness, coverage, summaries and events")


if __name__=="__main__":
    validate()
