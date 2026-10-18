"""Daily public-feed refresh, preserving verified direct-device archive rows."""
import io
import json
import math
import urllib.request
from datetime import datetime, timezone
from engine import (DATA, decode, analyze, merge_rows, read_csv, build_products, iso)

BASE="https://data.raspberryshake.org/fdsnws/dataselect/1/query"


def main():
    now=datetime.now(timezone.utc).timestamp()
    end=math.floor((now-1800)/60)*60;start=end-86400
    path=DATA/"sources.json"
    sources=json.loads(path.read_text())["sources"] if path.exists() else []
    source_map={s["source_id"]:s for s in sources}
    rows=read_csv();attempts=[]
    for channel in ("HDF","EHZ"):
        url=f"{BASE}?net=AM&sta=R19BB&loc=00&cha={channel}&start={iso(start)}&end={iso(end)}&format=miniseed"
        result=dict(channel=channel,source_url=url,complete_minutes=0,latest_sample_utc=None)
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"R19BB-dashboard/2.0"}),timeout=150) as response:
                if response.status==204:
                    raise ValueError("No data returned (HTTP 204)")
                raw=response.read(100_000_001)
            if len(raw)>100_000_000:
                raise ValueError("Response exceeds 100 MB safety limit")
            stream,receipt=decode(io.BytesIO(raw),f"FDSN {channel} {iso(start)} to {iso(end)}","public-fdsn")
            receipt["source_url"]=url
            added,audit=analyze(stream,channel,start,end)
            rows=merge_rows(rows,added)
            source_map[receipt["source_id"]]=receipt
            result.update(complete_minutes=sum(r["quality"]=="complete" for r in added),
                          latest_sample_utc=receipt["last_sample_utc"],source_id=receipt["source_id"],
                          decode_warning_count=len(receipt["decode_warnings"]),sample_audit=audit)
        except Exception as error:
            result["error"]=str(error)[:300]
        attempts.append(result)
    status=dict(state="Public-feed refresh complete",
                note="A feed check is not live connectivity. Verified uploaded history is retained even when the public feed is unavailable.",
                request_start=iso(start),request_end=iso(end),feed_attempt_utc=iso(now),
                channels=attempts,last_ingestion_kind="public-fdsn")
    if all(a.get("error") for a in attempts):
        status["state"]="Public feed unavailable · archive retained"
    build_products(rows,list(source_map.values()),status)
    print(json.dumps(status,indent=2))


if __name__=="__main__":
    main()
