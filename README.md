# Northville R19BB dashboard

Public dashboard: https://markroneil360.github.io/39406-Jasmine-Ongoing-Infrasound-Complaint/

Independent `AM.R19BB.00` dashboard adapted from the Detroit dashboard's dark green layout and channel-isolation approach. No Detroit measurements, case identifiers, private logs, LAN identifiers or private waveform uploads are included.

## Refresh

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/refresh.py
python scripts/validate.py
```

The daily Perplexity task is scheduled for 7:00 AM America/New_York. It runs these commands, commits only validated data updates, pushes to `main`, checks the Pages workflow, and compares public file hashes. It reports unsuccessful retrieval honestly. GitHub Actions deploys on push; there is no second GitHub daily schedule.

The refresh requests the last 24 hours ending 30 minutes before execution from https://data.raspberryshake.org/fdsnws/dataselect/1/. It accepts only R19BB HDF/EHZ at 100 Hz. Complete UTC minutes require 6,000 finite samples on a consistent grid. Conflicting overlaps reject the channel; gaps and flatlines are excluded. Previous accepted minutes are preserved, with conflicting recalculations rejected rather than silently replaced. Failed acquisition updates the attempt status but does not erase accepted history.

## Interpretation

Demean each complete minute, apply a Hann window, calculate its FFT, and select the maximum-power bin from 1–20 Hz. Count HDF minutes with that bin at 4–8 Hz inclusive. This custom classification is not a calibrated sound-pressure level, exposure threshold or source attribution. Gaps break consecutive runs. HDF and EHZ remain separate.

Recent acquisition means both channels supplied complete minutes and latest samples less than 90 minutes old at check time. It does not mean the browser has a live connection to the device. Browser snapshots over 26 hours old are marked stale. A daily run only requests 24 hours; missed runs may leave archive gaps until separately backfilled.

Historical totals from the original page are preserved in Git history, not carried forward as independently verified records. The new cumulative archive starts with successful acquisitions by this pipeline.

## Deployment and rollback

Pages uses the GitHub Actions workflow `.github/workflows/pages.yml`. It tests analysis and validates the station, archive hash and independently recounted summaries before deploying only static site files and derived data. The public source hashes identify retrieved responses; raw responses are not retained, so hashes alone cannot reproduce the upstream source after it changes.

Rollback with `git revert <commit>` and push normally. Never force-push. The prior page is preserved at commit `4b5ade8` in this repository. Do not modify `markroneil360/ongoing-unit-2709` or `markroneil360/Infrasound-39406Jasmine-Ongoing` as part of this workflow.
