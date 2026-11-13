# Parallax SPHEREx coverage handoff

**Goal:** Add more real observations from distinct dates and longer time baselines. Keep the SPHEREx experience as the core of the NASA Space Apps project. The user explicitly approved supplementing with other legitimate observation sources when SPHEREx coverage is thin or its archive is unreliable. This supersedes the previous instruction to use IRSA SPHEREx as the only image source.

## Repository and working state

- [hs-isadev/planet-x](https://github.com/hs-isadev/planet-x), branch `final-parallex-preview`.
- The last confirmed GitHub push was `934b6db`. It contains the missing detector-context fix, the Field Guide, the small-body layer and Earth meteors. Check the Render deploy SHA separately.
- Windows deploy checkout used for that push: `C:\Users\thest\AppData\Local\Temp\parallax-final-NshqrM\planet-x`. The active source folder in this session is `C:\Users\thest\Downloads\nasaSpace-render-deploy\nasaSpace-render-deploy`. Check which checkout contains the current edits before committing.
- This session started local changes for **All exposures** and **Find more dates** in the viewer and archive request path. These changes are separate from the confirmed push. They do not add FITS to the bundle. The bundled frame regression passed for all 1,372 frames, and 15 Python cache and recovery tests passed. Live archive retrieval remains unverified. Inspect the working diff before deploying.
- Local start: `python start.py`. Render service: **parallex**. Keep `SPHEREX_PREWARM=0` on the memory-constrained deployment. Prepare bulk bundles off Render. Live downloads are already bounded in low-memory mode.

## Verified saved baseline

The bundle contains **1,372 real exposure frames across 90 saved fields**. These are the five main targets. Dates are UTC and counts describe the current saved bundle.

| Target | Saved exposures | Distinct dates | First saved date | Last saved date |
|---|---:|---:|---|---|
| Barnard’s Star | 356 | 40 | 2025-08-15 | 2026-09-22 |
| Epsilon Indi B | 424 | 60 | 2025-04-24 | 2026-10-02 |
| WISE 0855 | 256 | 27 | 2025-05-05 | 2026-05-14 |
| RW Aurigae | 72 | 27 | 2025-09-01 | 2026-09-16 |
| R Draconis | 77 | 41 | 2025-04-29 | 2026-09-16 |

The default timeline keeps one frame per UTC date. The user clarified that **the issue is too few real observations on different dates**. Exposing more of the already-saved same-day frames helps inspection, but success requires finding and validating additional dates or adding real older epochs from another survey. The earlier goal of 200 dates per target remains unmet. Treat it as a target subject to released coverage.

## Why more SPHEREx dates are hard to find

1. **The telescope builds spectra over multiple pointings.** Many detector exposures can fall on the same UTC date, and the wavelength at a target changes with its position on the detector. Only a subset of dates has a good comparison in a given detector and wavelength interval. Coverage varies by field. [IRSA SPHEREx Data Explorer overview](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/overview.html)
2. **The searchable releases changed.** IRSA released DR1 in November 2026 and recommends using DR1 and QR3 as a consistent processing set. QR2 is now available by known direct URLs, with its prior coverage superseded for new searches by the current releases. A reprocessed copy of an exposure gives the same observing epoch. The DR1 all-sky cube is useful spectral context and represents combined data. [SPHEREx DR1 overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html) · [IRSA access and release collections](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
3. **Discovery and download are separate.** TAP and SIA discover exposure footprints and dates. IRSA’s public AWS mirror can supply the FITS when the object key is known. The bundled mirror index covers 1,104 indexed detector footprints, so it only finds candidates in indexed areas. The app still has to validate coverage and quality on the actual FITS. Previous runs reported TAP/SIA timeouts or errors. Fresh probes here could not resolve either IRSA or AWS, so this session cannot establish the archive-wide date count or confirm new live downloads. [IRSA cloud data access](https://irsa.ipac.caltech.edu/cloud_access/)

## Supplemental sources are approved

- **First choice for older infrared epochs:** WISE/NEOWISE Level 1b single-exposure FITS. Query W1 and W2 separately and retain their release, scan/frame identifiers, UTC time, footprints and quality. Select all overlapping exposures when repeating the IRSA Image Service search. [IRSA WISE Image Service search help](https://irsa.ipac.caltech.edu/onlinehelp/wise/help.pdf?id=103b97c)
- **Deeper epoch images:** use time-resolved unWISE W1/W2 coadds if the single exposures are too shallow. Select individual time-resolved coadds with their documented epoch bounds. Display a coadd as an epoch range and count it once. [IRSA unWISE overview](https://irsa.ipac.caltech.edu/data/WISE/unWISE/overview.html) · [AWS unWISE open data](https://registry.opendata.aws/wise-unwise/)
- **Display and analysis:** label all observations with mission, product type, band, date or epoch range, and source link. Provide a WISE/NEOWISE or unWISE series alongside SPHEREx and show each series’ own date count. Use a consistent band within a motion sequence. Cross-mission astrometry requires a shared sky grid, reference sources, compatible centroid measurements and uncertainty checks. Keep brightness and positional-change indicators separate.

## Work order for the next session

1. **Find new actual epochs first.** On a network-enabled machine, query both TAP and SIA for DR1 and QR3 for WISE 0855 and Barnard’s Star, then Epsilon Indi B, RW Aurigae, R Draconis and nearby stars. Capture provider status and result counts. Compare against the saved UTC dates before fetching. Verify the target position against the FITS WCS, accounting for source motion and the field width where needed.
2. **Get candidate pixels.** Try the public AWS mirror for known exposure keys and IRSA cutouts as the other download path. Start with widely separated missing dates. If a candidate fails coverage or mask checks, try another exposure on that date. Prefer high-quality overlapping coverage and a consistent detector and similar wavelength for the motion demo.
3. **Add supplemental epochs in parallel.** Start with WISE 0855 and Barnard’s Star. Use separate mission series and labels, then add additional targets based on detectable coverage. Measure the distinct-date gains from each source.
4. **Cache and verify offline.** Save validated FITS and provenance, regenerate aligned previews and bundled manifests, and keep the default chronological sequence one frame per date. Offer all saved exposures as a separate inspection mode. Test coordinate searches, the five presets, and playback. Verify real deployed retrieval over both the normal and fallback paths when possible.
5. **Report evidence for the handoff.** For each target and source, provide total matched exposures, valid downloaded frames, distinct UTC dates, first and last dates, and failures by discovery, download or coverage. Report the before/after number of usable dates and identify the subset suitable for motion analysis. Keep at least two tested epochs with matching detector and similar wavelength as the motion demonstration.

## Where to work

| Area | Files |
|---|---|
| Lab search, request processing, saved sessions and paging | `backend/observation_lab_core/server.py`, `backend/observation_lab_core/science.py` |
| IRSA TAP/SIA discovery, AWS footprints and cached indexes | `backend/observation_lab_core/archive.py`, `backend/observation_lab_core/featured_views.py`, `backend/archive.py`, `backend/cloud.py` |
| FITS and saved manifests | `backend/data/spherex-seed/`, `backend/data/preset-archive-index.json`, `backend/data/mirror-footprints.json` |
| Offline bundle preparation | `scripts/prefetch_lab.py`, `backend/observation_lab_core/warm_cache.py`, `scripts/index_spherex_mirror.py` |
| Lab timeline, counts and filtering | `web/observation-lab/app.js`, `web/observation-lab/index.html` |
| Regression and deployment | `tests/lab_frame_render.mjs`, `tests/test_parallax_recovery.py`, `docs/RENDER_DEPLOYMENT.md` |

## Status update 2026-11-17

- Done: SPHEREx now has 222 dates for R Draconis (was 41) and 35 for RW Aurigae (was 27); five targets total 1,374 exposures (was 1,185). Barnard, Epsilon Indi B and WISE 0855 gained no new SPHEREx dates (archive census).
- Done: WISE (2010) and NEOWISE-R (2014 to 2024) single-exposure epochs added for WISE 0855, Barnard's Star and Epsilon Indi B (about 35 MB). WISE 0855 W2 is detected; W1 is not.
- Report: docs/coverage/epoch-report.md (tables, failures by stage, measured vs not measured, reproduce commands).
- Tests as reported by the agents: pytest -m "not live" 90 passed, 2 failed (both pre-existing); lab render test PASS 1,561 frames.
- Not done: live Render deployment; no cross-mission motion measured; 200-date goal met only for R Draconis.
- Next steps, in order:
  1. Commit and push to final-parallex-preview, redeploy Render with SPHEREX_PREWARM=0, and confirm the deployed SHA.
  2. Optional: WISE series for rw-aur and r-dra.
  3. Consider cross-mission astrometry only with shared reference stars and stated uncertainties.
