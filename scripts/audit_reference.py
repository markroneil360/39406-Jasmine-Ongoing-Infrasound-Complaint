"""Compare accepted HDF minutes with Detroit reference functions on native traces.

Run locally with the reference repository and original uploads. No raw data is
published; the resulting verification receipt and source hashes are public.
"""
import argparse
import ast
import json
import math
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from obspy import Stream,UTCDateTime
from scipy.signal import welch
from engine import DATA,STATION,METHOD,BANDS,decode,read_csv,epoch,write_json

parser=argparse.ArgumentParser()
parser.add_argument("--reference",required=True)
parser.add_argument("files",nargs="+")
args=parser.parse_args()
source=Path(args.reference).read_text()
tree=ast.parse(source)
namespace=dict(np=np,math=math,UTCDateTime=UTCDateTime,welch=welch,BANDS=BANDS)
functions=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in ("complete","classify")]
exec(compile(ast.Module(body=functions,type_ignores=[]),"<Detroit reference>","exec"),namespace)
assert "complete" in namespace and "classify" in namespace
stream=Stream()
source_ids=[]
for filename in args.files:
    st,receipt=decode(filename,Path(filename).name,"audit-only")
    source_ids.append(receipt["source_id"])
    stream+=st.select(channel="HDF")
rows=[r for r in read_csv("minutes.csv") if r["channel"]=="HDF"]
matched=0;seams=[];differences=[]
for row in rows:
    t=epoch(row["minute_utc"])
    dt=datetime.fromtimestamp(t,timezone.utc)
    result=namespace["complete"](stream,dt)
    if result is None:
        # Only merge bounded native slices for file-edge seam minutes.
        part=stream.slice(UTCDateTime(t-1),UTCDateTime(t+61)).copy()
        part.merge(method=0,fill_value=None)
        result=namespace["complete"](part,dt)
        seams.append(row["minute_utc"])
    if result is None:
        differences.append(dict(minute=row["minute_utc"],reason="Reference extraction unavailable"))
        continue
    label=namespace["classify"](*result)
    if label!=row["dominant_band"]:
        differences.append(dict(minute=row["minute_utc"],reference=label,observed=row["dominant_band"]))
    else:
        matched+=1
receipt=dict(station=STATION,method=METHOD,reference_url="https://github.com/markroneil360/ongoing-unit-2709/blob/51ddb7d10925da9ad245595ae104f3bfcb419232/tools/refresh_4_8_10min_current.py",
             source_ids=source_ids,
             tested_complete_hdf_minutes=len(rows),matching_band_classifications=matched,
             bounded_native_merge_minutes=seams,differences=differences,
             all_classifications_match=matched==len(rows),
             scope="Independent native-trace extraction and exact Detroit complete/classify functions. No calibration or source attribution.")
write_json(DATA/"reference-audit.json",receipt)
print(json.dumps(receipt,indent=2))
if differences:
    raise SystemExit("Reference comparison failed")
