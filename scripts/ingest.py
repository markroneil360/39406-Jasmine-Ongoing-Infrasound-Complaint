"""Import explicitly authorized direct-device MiniSEED files, derived outputs only."""
import argparse
import json
from pathlib import Path
from obspy import Stream
from engine import (DATA, STATION, METHOD, decode, analyze, merge_rows, read_csv,
                    build_products, iso)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("files",nargs="+")
    args=parser.parse_args()
    streams={"HDF":Stream(),"EHZ":Stream()}
    path=DATA/"sources.json"
    previous=json.loads(path.read_text())["sources"] if path.exists() else []
    sources={s["source_id"]:s for s in previous}
    new_sources=[]
    for name in args.files:
        p=Path(name).expanduser()
        stream,receipt=decode(str(p),p.name,"direct-device-upload")
        sources[receipt["source_id"]]=receipt
        new_sources.append(receipt)
        for channel in streams:
            streams[channel]+=stream.select(channel=channel)
        print(p.name,receipt["decoded_samples"],"decoded samples;",len(receipt["decode_warnings"]),"warnings",flush=True)
    observations=[];audits=[]
    for channel,stream in streams.items():
        rows,audit=analyze(stream,channel)
        observations+=rows;audits.append(audit)
        print(channel,len(rows),"documented minute slots;",audit,flush=True)
    old=read_csv()
    rows=merge_rows(old,observations)
    status=json.loads((DATA/"status.json").read_text()) if (DATA/"status.json").exists() else {}
    status.update(state="Direct-device archive analyzed",
                  note="Uploaded recordings are analyzed independently of public-feed availability. Partial fragments remain documented; missing time is unknown.",
                  last_ingestion_kind="direct-device-upload")
    audit=dict(station=STATION,method=METHOD,files_received=len(args.files),
               distinct_file_hashes=len({s["source_id"] for s in new_sources}),
               source_ids=[s["source_id"] for s in new_sources],channels=audits,
               original_files_unchanged=True,raw_files_published=False,
               old_observation_rows=len(old),new_observation_rows=len(rows),
               note="Sub-sample timestamps assigned to nearest tick, at most half a 100 Hz sample; values never interpolated. Conflicting overlaps excluded.")
    summary=build_products(rows,list(sources.values()),status,audit)
    print(json.dumps(summary["windows"]["all"],indent=2))


if __name__=="__main__":
    main()
