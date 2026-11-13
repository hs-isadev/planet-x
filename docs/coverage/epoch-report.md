# Epoch coverage report

Date: 2026-11-17

Summary: The SPHEREx bundle for the five main targets now holds 1,374 exposures, up from 1,185. R Draconis rose from 41 to 222 distinct UTC dates and now meets the 200-date goal. RW Aurigae rose from 27 to 35 dates. Barnard's Star, Epsilon Indi B and WISE 0855 gained no new SPHEREx dates, because the archive census found none beyond the saved set. Supplemental WISE (2010) and NEOWISE-R (2014 to 2024) single-exposure epochs were added for WISE 0855, Barnard's Star and Epsilon Indi B. Those epochs are a separate mission and are reported separately, not added to the SPHEREx dates. WISE 0855 W2 is detected in single exposures, but W1 is not. No cross-mission motion has been measured.

## Table A: SPHEREx per target

Counts are recomputed from `backend/data/spherex-seed/<session>/manifest.json`. Archive columns come from `docs/coverage/spherex-census.md` (DR1 and QR3 only).

| Target | Before exp / dates | After exp / dates | First to last (after) | Archive exp / dates (census) | Gap to archive dates | Gap to 200-date goal |
|---|---:|---:|---|---:|---:|---:|
| Barnard's Star | 356 / 40 | 356 / 40 | 2025-08-15 to 2026-09-22 | 358 / 39 | 0 (saved 40, one date from QR2 not in census query) | 160 |
| Epsilon Indi B | 424 / 60 | 424 / 60 | 2025-04-24 to 2026-10-02 | 461 / 60 | 0 | 140 |
| WISE 0855 | 256 / 27 | 256 / 27 | 2025-05-05 to 2026-05-14 | 258 / 27 | 0 | 173 |
| RW Aur | 72 / 27 | 80 / 35 | 2025-09-01 to 2026-09-16 | 335 / 35 | 0 | 165 |
| R Dra | 77 / 41 | 258 / 222 | 2025-04-24 to 2026-09-27 | 2,493 / 222 | 0 | met (+22) |

Total for the five targets: 1,185 exposures before, 1,374 after. The baseline's 1,372 frames is for the whole bundle, which also includes other fields.

## Table B: WISE and NEOWISE-R per target and series

Counts come from `backend/data/supplemental-epochs/<key>/series.json`. Frames are default / extra. Each series has one default frame per UTC date, so distinct dates equal the default frame count.

| Target | Series | Mission | Band | Distinct dates | First to last | Frames default / extra |
|---|---|---|---|---:|---|---:|
| WISE 0855 | wise-w1 | WISE | W1 | 4 | 2010-05-03 to 2010-11-11 | 4 / 3 |
| WISE 0855 | wise-w2 | WISE | W2 | 4 | 2010-05-03 to 2010-11-11 | 4 / 3 |
| WISE 0855 | neowise-w1 | NEOWISE-R | W1 | 52 | 2014-05-04 to 2024-04-18 | 52 / 43 |
| WISE 0855 | neowise-w2 | NEOWISE-R | W2 | 52 | 2014-05-04 to 2024-04-18 | 52 / 43 |
| Barnard's Star | wise-w1 | WISE | W1 | 4 | 2010-03-20 to 2010-09-19 | 4 / 0 |
| Barnard's Star | wise-w2 | WISE | W2 | 4 | 2010-03-20 to 2010-09-19 | 4 / 0 |
| Barnard's Star | neowise-w1 | NEOWISE-R | W1 | 52 | 2014-03-20 to 2024-03-20 | 52 / 0 |
| Barnard's Star | neowise-w2 | NEOWISE-R | W2 | 52 | 2014-03-20 to 2024-03-20 | 52 / 0 |
| Epsilon Indi B | wise-w1 | WISE | W1 | 4 | 2010-04-29 to 2010-10-29 | 4 / 4 |
| Epsilon Indi B | wise-w2 | WISE | W2 | 4 | 2010-04-29 to 2010-10-29 | 4 / 4 |
| Epsilon Indi B | neowise-w1 | NEOWISE-R | W1 | 62 | 2014-05-02 to 2024-05-02 | 62 / 48 |
| Epsilon Indi B | neowise-w2 | NEOWISE-R | W2 | 62 | 2014-05-02 to 2024-05-02 | 62 / 48 |

Each band's date set equals its mission's date set: the union across bands is 4 WISE dates and 52 (or 62) NEOWISE-R dates per target.

## Table C: SPHEREx dates vs supplemental dates, by mission

Counts stay separate per mission and are not summed. RW Aur and R Dra have no supplemental series yet.

| Target | SPHEREx dates (2025 to 2026) | WISE (2010) dates | NEOWISE-R (2014 to 2024) dates | Earliest date now available |
|---|---:|---:|---:|---|
| Barnard's Star | 40 | 4 | 52 | 2010-03-20 (WISE) |
| Epsilon Indi B | 60 | 4 | 62 | 2010-04-29 (WISE) |
| WISE 0855 | 27 | 4 | 52 | 2010-05-03 (WISE) |
| RW Aur | 35 | not run | not run | 2025-09-01 (SPHEREx) |
| R Dra | 222 | not run | not run | 2025-04-24 (SPHEREx) |

## Failures by stage

| Source | Stage | Count | Detail |
|---|---|---:|---|
| SPHEREx census (5 targets) | Discovery | 1 | RW Aur TAP spherex_qr3 HTTP 503; the SIA query for the same collection returned 109 rows |
| SPHEREx R Dra download | Download | 0 | 183 downloaded in first pass, 181 valid |
| SPHEREx R Dra | Coverage | 2 | 2026W03_2A_0427_3 and 2026W16_1A_0508_4 ("This exposure does not cover the selected field"), replaced by next-ranked same-date exposures |
| SPHEREx R Dra | Mask | 1 | 2026W34_1A_0020_1 excluded |
| SPHEREx RW Aur | Download and coverage | 0 | 8 of 8 valid |
| WISE 0855 | Discovery / download / coverage | 0 / 0 / 5 | 698 matched, 209 attempted and downloaded, 204 valid. First coverage reason: neowiser-16081r077-w1 predicted target at pixel (32,67) outside 121x68 cutout (frame edge) |
| Barnard's Star | Discovery / download / coverage | 0 / 0 / 9 | 712 matched, 121 attempted and downloaded, 112 valid. First coverage reason: neowiser-42565r159-w1 predicted target at pixel (77,88) outside 81x154 cutout (frame edge) |
| Epsilon Indi B | Discovery / download / coverage | 0 / 0 / 4 | 756 matched, 240 attempted and downloaded, 236 valid. First coverage reason: neowiser-97923a073-w1 predicted target at pixel (51,55) outside 51x89 cutout (frame edge) |

The SPHEREx `failures` and `excluded_frames` fields in the saved manifests are empty, so the SPHEREx R Dra and RW Aur counts above come from the download agents' reports, not from saved files. All SPHEREx downloads used the IRSA public AWS mirror.

## 5. Motion-analysis subset

- The only motion pair is the existing Barnard D6 pair in `backend/data/motion-examples.json`. It has two SPHEREx epochs on detector 6: 2025-08-15 (2025W33_2C_0321_1, 4.92 um) and 2026-05-05 (2026W19_1A_0403_1, 4.89 um). Separation is 7.569 arcsec (east 2.635, north 7.096) over a baseline of 262.2 days. Each position has 0.8 arcsec error.
- No new SPHEREx dates match a motion pair. The census shows "new dates with a matching detector: 0" for every target.
- WISE previews show predicted proper-motion markers only. No motion was measured from WISE.

## Measured vs not measured

Measured in this report: all SPHEREx and WISE/NEOWISE-R counts and date ranges (recomputed from saved manifest and series files). The WISE bundle size is 35.4 MB on disk across 1,107 files (35,413,654 bytes).

Reported by the download agents, not re-run here: the SPHEREx bundle addition of about 136 MB (1,058 new files, 3 superseded sessions removed), the R Dra and RW Aur download and coverage counts, the census numbers, and the test results below. Test results were `pytest tests -q -m "not live"` with 90 passed and 2 failed (test_analysis_api_endpoints and test_appearance_and_disappearance, both failing before this work), and `node tests/lab_frame_render.mjs` with PASS 1,561 frames.

Not verified or not achieved:
- The live Render deployment has not been done. The deployed SHA is not confirmed. SPHEREX_PREWARM must stay 0.
- The 200-date goal is met only for R Dra in SPHEREx. Barnard's Star is at 40, Epsilon Indi B at 60, WISE 0855 at 27, and RW Aur at 35.
- WISE W1 is not detected for WISE 0855 (NEOWISE-R median SNR 0.5). Only W2 is detected in single exposures (median 8.2, range 3.5 to 11.9; about 11.4 in 2010).
- Barnard's Star is saturated at the target in all WISE and NEOWISE-R frames, so no aperture SNR is meaningful.
- Epsilon Indi B is unsaturated, with aperture SNR of about 220 to 750.
- No cross-mission astrometry has been done. Reliable astrometry would need shared reference stars and uncertainties.
- The census queries only DR1 and QR3. Saved QR2 frames are not checked against it.

## How to reproduce

Run from the repo root. The first two commands use the network (IRSA and AWS). Counting in this report reads saved files only.

```
.venv/Scripts/python.exe -X utf8 scripts/spherex_census.py wise-0855 barnard epsilon-indi rw-aur r-dra
.venv/Scripts/python.exe -X utf8 -m backend.observation_lab_core.warm_cache --field <key> --bundle --daily-only --mirror-only --new-dates-only
.venv/Scripts/python.exe -X utf8 scripts/fetch_wise_epochs.py --field wise-0855 --field barnard --field epsilon-indi
```
