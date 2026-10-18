# R19BB direct-device import acceptance checks

## Data

- All 16 files decode to the authorized station, channel and 100 Hz rate.
- Source SHA-256 receipts retained; raw files excluded from Git and publication.
- Warnings retained; conflicting overlaps excluded at sample level.
- Complete, partial and unknown time are distinct. No synthetic zero amplitudes.
- Full HDF waveform classification compared against pinned Detroit native extraction and classification functions, including daily file seams.
- Independent aggregate validation recounts source identity, hash integrity, unique minute keys, window coverage and consecutive event duration.
- Narrow 4–8 and wide 1–8 durations remain distinct.
- October 17 partial fragments are present and supplementary only.

## User interface

- Entire archive, 24-hour and 7-day overview selectors update counts and band shares.
- Event band and duration filters work; empty selections explicitly say no qualifying runs.
- All-runs control expands long tables.
- Frequency histogram is distinct from dominant-band proportions.
- Hourly amplitude breaks at unavailable hours and uses raw counts.
- Daily file and coverage tables, fragment and gap disclosures, method links and downloads work.
- Desktop and 375px mobile visual checks; no page-wide horizontal overflow.
- Off-happy-path: failed data fetch and station mismatch fail visibly, without zero metrics.
- Public HTML, scripts and every manifest-listed evidence file match the committed local bytes.
