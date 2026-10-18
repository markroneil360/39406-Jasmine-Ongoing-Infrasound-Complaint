# Northville R19BB dashboard

Canonical public dashboard: https://markroneil360.github.io/39406-Jasmine-Ongoing-Infrasound-Complaint/

Independent `AM.R19BB.00` best-efforts documented-time archive, using Detroit's complete-minute Welch method. The user authorized publication of derived results from the 16 direct-device files supplied in this conversation. Original raw files remain private and unchanged. Other private logs, precise location, local IP addresses, historical unsupported totals and Detroit measurements remain excluded.

## Locked analysis rules

- Missing data is **missing**, never an amplitude of zero, quiet time, interpolated values or event-free time.
- Every valid sample is counted as documented time, including incomplete clock minutes. Only complete UTC clock minutes enter primary band shares and sustained-event calculations.
- HDF pressure/infrasound is primary. EHZ ground motion is separate context, never pressure.
- 100 Hz sampling; 6,000 finite uncontested samples per complete minute. Native timestamps are assigned to the nearest 100 Hz clock tick, within 5 milliseconds. Sample values are never resampled or interpolated.
- Welch PSD: Hann window, 8-second segments, 50% overlap, constant detrending, density scaling. The dominant band has the greatest **mean PSD** in 1–4, 4–8, 8–16 or 16–20 Hz; upper edges excluded except 20 Hz.
- Primary event: at least 10 consecutive complete **4–8 Hz-dominant** minutes. Missing, partial, conflicted, flatline or nonmatching minutes break runs. No gap bridging.
- Keep **1–8 Hz** wide-band runs separate from 4–8 Hz runs. Wide-band runs join consecutive complete minutes classified as 1–4 or 4–8.
- Peak-bin frequency within 1–20 Hz is supplementary and is not the dominant-band criterion. For incomplete minutes only, the longest contiguous observed fragment of at least 8 seconds receives a supplementary frequency estimate; never count it as a complete minute.
- Decoding warnings are public provenance, not a reason to silently discard all readable data. Unreadable portions remain unavailable; conflicting sample positions are excluded. Identical overlaps count once.
- Entire-archive and rolling calendar-window coverage include missing time in the coverage denominator; **frequency shares include only classified complete minutes**.
- No calibrated pascals, SPL, hazard threshold, source attribution, legal conclusions or MITM findings are inferred from raw counts.

Pinned Detroit implementation: https://github.com/markroneil360/ongoing-unit-2709/blob/51ddb7d10925da9ad245595ae104f3bfcb419232/tools/refresh_4_8_10min_current.py

The initial R19BB placeholder used a full-minute FFT-peak rule. It had accepted no measurements. This revision corrects the method before admitting the uploaded waveforms. It does not silently combine old and new methods.

## Local commands

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s scripts -p 'test_*.py'
python scripts/ingest.py /path/to/explicitly-authorized/AM.R19BB.00.*.D.*
python scripts/validate.py
```

Public-feed daily refresh:

```sh
python scripts/refresh.py
python scripts/validate.py
```

The daily Perplexity task runs at **07:00 America/New_York**, attempts the last 24 hours ending 30 minutes before the check, and preserves the authorized direct-upload archive. Missed runs can leave gaps until backfilled. The task commits only validated derived files under `data/`, pushes `main`, waits for Pages success, and verifies served hashes. A failed feed request updates status and retains recorded history. Direct uploads do not imply live connectivity.

## Evidence files

- `observations.csv`: one row per documented channel-minute, including partial and conflicted time. Completely unobserved minutes are absent, not zero records.
- `minutes.csv`: only complete classified minutes, with raw-count RMS, peak bin, mean PSD by band and source hashes.
- `sources.json`: each source's SHA-256, decoded sample counts, native timestamps, channel identity and warnings. Per-file decoded sample time is not a deduplicated archive total.
- `ingestion-audit.json`: latest direct import's deduplicated sample counts, overlap exclusions and missing intervals. Later feed records may fill some of these original import gaps.
- `reference-audit.json`: all accepted HDF minutes from the uploaded dataset checked using independent native trace extraction and the exact Detroit complete/classify functions. It is dataset-bound, not a claim of independent auditing of future feed additions.
- `summary.json`: all-archive, trailing 24-hour and 7-day summaries, UTC-day coverage, hourly amplitude and peak-frequency distribution.
- `events.json` / `events.csv`: consecutive run registers; intervals are start-inclusive/end-exclusive.
- `manifest.json`: SHA-256 values for the public evidence files.

Partial rows are not combined from summaries. Differing partial observations require reconciliation from the original waveforms; they cannot silently replace one another based on sample count. A newer complete waveform-derived minute can replace a partial observation. Duplicate complete minutes must agree; otherwise the update stops rather than overwriting accepted evidence.

## Deploy and rollback

GitHub Pages deploys from `.github/workflows/pages.yml` on pushes to `main`, after tests and validation. Only static site assets and derived `data/` files are deployed. Raw uploads are not committed.

Rollback with `git revert <commit>` and a normal push. Do not force-push. The first placeholder is preserved at commit `a7a03b4` and the prior page at `4b5ade8`. Never modify `markroneil360/ongoing-unit-2709` or `markroneil360/Infrasound-39406Jasmine-Ongoing` in this workflow.
