# Parallax SPHEREx coverage handoff

**Goal:** Find and add every usable SPHEREx observing date available for each target. Exhaust the released SPHEREx coverage for the five presets first: Barnard’s Star, Epsilon Indi B, WISE 0855, RW Aurigae, and R Draconis. Then apply the same search to the rest of the star catalog. Continue beyond 40, 400, or any other milestone whenever the archive has more usable dates. Real images from other observatories and wavelength bands can extend the baseline as supplemental data.

## Repository and working state

- Start from the current tip of [final-parallex-preview](https://github.com/hs-isadev/planet-x/tree/final-parallex-preview). The [epoch coverage report](docs/coverage/epoch-report.md) records the bundle baseline. Verify the live Render commit independently.
- Start locally with `python start.py`. Keep `SPHEREX_PREWARM=0` on the memory-constrained Render service and prepare bulk bundles off Render.

## Saved date baseline

| Target | SPHEREx dates | WISE dates | NEOWISE-R dates | SPHEREx date range |
|---|---:|---:|---:|---|
| Barnard’s Star | 40 | 4 | 52 | 2025-08-15 to 2026-09-22 |
| Epsilon Indi B | 60 | 4 | 62 | 2025-04-24 to 2026-10-02 |
| WISE 0855 | 27 | 4 | 52 | 2025-05-05 to 2026-05-14 |
| RW Aurigae | 35 | — | — | 2025-09-01 to 2026-09-16 |
| R Draconis | 222 | — | — | 2025-04-24 to 2026-09-27 |

The default timeline uses one usable image per UTC date. Count exposures, detector images, wavelength bands, and reprocessed copies from the same day only once toward the target’s date total. For a combined total, take the union of UTC dates across missions. Use an epoch range for a time-resolved coadd and report those ranges separately from single-day images. Label each image with its mission, band, date or range, and source.

## Why more SPHEREx dates are hard to find

1. **The telescope builds spectra over multiple pointings.** Many detector exposures can fall on the same UTC date, and the wavelength at a target changes with its position on the detector. Only a subset of dates has a good comparison in a given detector and wavelength interval. Coverage varies by field. [IRSA SPHEREx Data Explorer overview](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/overview.html)
2. **The searchable releases changed.** IRSA released DR1 in November 2026 and recommends using DR1 and QR3 as a consistent processing set. QR2 is now available by known direct URLs, with its prior coverage superseded for new searches by the current releases. A reprocessed copy of an exposure gives the same observing epoch. The DR1 all-sky cube is useful spectral context and represents combined data. [SPHEREx DR1 overview](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/overview_dr1.html) · [IRSA access and release collections](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/)
3. **Discovery and download are separate.** TAP and SIA discover exposure footprints and dates. IRSA’s public AWS mirror can supply the FITS when the object key is known. The bundled mirror index covers 1,104 indexed detector footprints, so it only finds candidates in indexed areas. The app still has to validate coverage and quality on the actual FITS. Previous runs reported TAP/SIA timeouts or errors. The [previous census](docs/coverage/spherex-census.md) reflects the releases and search geometry it queried. [IRSA cloud data access](https://irsa.ipac.caltech.edu/cloud_access/)

## Work order

1. **Search all five presets first.** Query IRSA SIA and TAP for DR1 and QR3, including deep-field collections where applicable. Compare candidates against saved UTC dates before downloading. Search along the epoch-dependent positions of high-proper-motion targets, especially WISE 0855. Verify the expected position against the FITS WCS and check that it lands on usable pixels. Try the public AWS mirror when the exposure key is known. When a candidate fails coverage or quality checks, try another exposure from that date. Record which releases, footprint searches, and fallbacks were checked, along with any archive errors or unresolved dates.
2. **Search other observatories for the same five targets.** Start with the leads below. Use observing logs and catalog rows to locate image products. Count a date as added after retrieving the science image and verifying usable coverage. Record saturation and nondetection where applicable.
3. **Expand to the other stars.** Queue the rest of the app’s star catalog, starting with nearby stars and fields with strong repeat coverage, including the SPHEREx deep fields. Prioritize by distinct dates available and time baseline. Validate coverage per target, even when two stars share a field.
4. **Bundle and verify.** Save validated FITS, provenance, observation timestamps, and previews. Verify playback in chronological order and check that each new date remains available after a restart. Report before-and-after date counts per star and mission, the deduplicated total, the first and last dates, and any gaps in retrieval or coverage. Use compatible detector and wavelength data when measuring motion.

For the motion check, find the earliest and latest usable SPHEREx observations that share a detector and similar wavelengths. Register the frames on stable field stars, then blink the aligned pair and measure the target’s displacement with uncertainty where the data support it. Report the time span and whether the shift is resolved, including subpixel shifts if measured. Keep searching for dates that extend that comparable baseline even when many dates are already loaded.

## Supplemental archive leads

| Target | Search next |
|---|---|
| Barnard’s Star | Check SPHEREx along the proper-motion track. Search ZTF science images for usable, unsaturated target pixels. The saved WISE and NEOWISE-R frames are saturated at the target. [ZTF image API](https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html) |
| Epsilon Indi B | Query the ESO archive using the VLT NACO and FORS2 programs listed by Chen et al. The study reports 56 NACO observing nights and 88 FORS2 epochs. Check the actual date overlap and retrieve the science frames. [Study](https://arxiv.org/abs/2205.08077) · [ESO archive](https://archive.eso.org/programmatic/) |
| WISE 0855 | Use published Spitzer IRAC 4.5 µm and Hubble imaging dates to locate older frames. W2 is the better starting band for single-exposure WISE and NEOWISE-R target detections. [Published observing log](https://arxiv.org/abs/1605.06655) · [Spitzer Heritage Archive](https://irsa.ipac.caltech.edu/onlinehelp/heritage/heritage/downloads.html) |
| RW Aurigae | Query public ZTF single-exposure science images by position and group by UTC date. Check WISE and NEOWISE-R for older infrared dates. [ZTF image API](https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html) |
| R Draconis | Extend the 222-date SPHEREx series with newly released coverage. Search WISE, NEOWISE-R, and ZTF for additional dates. [SPHEREx releases](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-releases/) · [ZTF image API](https://irsa.ipac.caltech.edu/docs/program_interface/ztf_api.html) |

For faint targets, check [time-resolved unWISE images](https://irsa.ipac.caltech.edu/data/WISE/unWISE/overview.html) for deeper epoch coverage. Use separate mission and band views to keep playback interpretable.

## Where to work

| Area | Files |
|---|---|
| Lab search, request processing, saved sessions and paging | `backend/observation_lab_core/server.py`, `backend/observation_lab_core/science.py` |
| IRSA TAP/SIA discovery, AWS footprints and cached indexes | `backend/observation_lab_core/archive.py`, `backend/observation_lab_core/featured_views.py`, `backend/archive.py`, `backend/cloud.py` |
| FITS and saved manifests | `backend/data/spherex-seed/`, `backend/data/preset-archive-index.json`, `backend/data/mirror-footprints.json` |
| Offline bundle preparation | `scripts/prefetch_lab.py`, `backend/observation_lab_core/warm_cache.py`, `scripts/index_spherex_mirror.py` |
| Lab timeline, counts and filtering | `web/observation-lab/app.js`, `web/observation-lab/index.html` |
| Regression and deployment | `tests/lab_frame_render.mjs`, `tests/test_parallax_recovery.py`, `docs/RENDER_DEPLOYMENT.md` |

## Verification references

- [Epoch coverage report](docs/coverage/epoch-report.md) includes bundle counts, retrieval results, reproduction commands, and the tested Barnard’s Star motion pair.
- [SPHEREx discovery census](docs/coverage/spherex-census.md) records the providers, search geometry, and release collections already checked.

## Session update (2026-11-19)

- **Downloading more dates:** run `python -m scripts.download_more_dates --check`, then `python -m scripts.download_more_dates`, on a machine that can reach IRSA. It writes into `backend/data/spherex-seed/` and prints before/after dates per field. The Claude sandbox and its PC shell were blocked from IRSA and the AWS mirror (proxy 403), so no new FITS were fetched. The last discovery listed 364 exposures on 40 UTC dates for Barnard's Star (449 and 60 for Epsilon Indi B), so more dates depend on IRSA releasing newer data or on the approved WISE/NEOWISE supplement, which is not built yet.
- **Live batch limit:** `SPHEREX_LIVE_BATCH` (default 60, was 12) and `SPHEREX_BATCH_SECONDS` (default 60). Each request returns everything fetched so far and the viewer chains the next batch itself. `SPHEREX_VIEW_FRAME_LIMIT` (default 400, was 60) caps frames for custom positions.
- **Expected-position box:** `web/observation-lab/star-lock.js` finds the star in up to 16 frames, locks the start of the span, and moves the box by catalog proper motion (or a measured drift when large). Test: `node tests/star_lock.mjs`.
- **Fixed:** the lab logo no longer loads the app inside itself; the "Planet X analysis tools" entry to the old screen is removed.


## Update: Render free-tier speed (2026-11-19)

What changed and why:
- `backend/compression.py` + `app.add_middleware(TextGZipMiddleware)`: gzip for JS/CSS/HTML/JSON only (images, GLB and FITS are skipped). The first-load text assets go from about 6.5 MB to 1.6 MB.
- `FreshStaticFiles`: `/vendor/*.js|css` cached 7 days, `assets/*.json|svg` 1 hour (images/GLB stay at 1 day), app JS/CSS/HTML still revalidate.
- `Dockerfile`: `python -m compileall` before `USER observatory`. The runtime user cannot write `__pycache__`, so before this every cold start recompiled the whole backend.
- Deferred slow imports: `aiohttp` (backend/cloud.py), `scipy.stats` (backend/analysis.py), unused `astroquery.simbad` (backend/main.py). `import backend.main` went 2.7 s to 2.3 s on a fast machine.
- `backend/observation_lab.py`: the lab archive index now loads in a background thread 3 s after startup (`SPHEREX_WARM_LAB=0` turns it off, `SPHEREX_WARM_LAB_DELAY` changes the delay), so the first SPHEREx click no longer pays for it.
- `web/partner-evidence.js`: the exported Gaia reference pointed at the wrong source entry (SOURCES[2]); fixed. WiseView added to the source list.

Not fixable in code: Render's free plan sleeps after 15 minutes without traffic and takes about a minute to wake. Keep it awake with a free uptime pinger (UptimeRobot or cron-job.org) requesting `https://<service>.onrender.com/api/health` every 5-10 minutes. One always-on free service fits inside the 750 free instance hours a month.

## Update: spectrum wording, 3D small bodies, controls, loader (2026-11-20)

- **Spectrum explanations:** `web/observation-lab/spectrum-story.js` writes a plain-language reading under the Spectrum and Flux-over-time graphs, recomputed from exactly the plotted points: overall slope (λ^α) and what it implies, where the light peaks (rough temperature), which wavelengths actually have signal, dip-check results in words, scatter between dates, a small period search for light curves, and target-specific context for the five presets and Vesta. It only reports what the backend dip checks found.
- **3D small bodies:** `web/small-bodies.js` now has ~4,500 bodies with the real belt structure (Kirkwood gaps, Hildas, Trojans at L4/L5, NEAs, Centaurs, cold classical Kuiper belt, Plutinos, scattered disk), 13 named bodies on published orbital elements (Ceres, Vesta, Pallas, Hygiea, Psyche, Eros, Bennu, Ryugu, Apophis, Arrokoth, Haumea, Makemake, Eris), rocks that keep a ~2 px minimum size but grow to true size up close, and an interplanetary dust cloud lit with a Henyey–Greenstein phase function (forward scattering toward the Sun plus a gegenschein back lobe). Positions along each orbit are illustrative.
- **Focus on any rock:** `web/asteroid-focus.js`. Click a rock, use Scale / orbit → Fly to asteroid, Random asteroid, Random Kuiper object, or Asteroid belt. The camera follows the body along its orbit; a detailed, sunlit close-up model at true size replaces it, with an info card.
- **Controls:** `web/free-controls.js` replaces OrbitControls in the 3D context. No pole lock (orbit over the top freely), right/middle/shift-drag or two fingers to pan, Q/E roll, frame-rate-independent damping. Zoom in `navigation.js` is now a constant ratio per wheel notch eased in at a fixed rate (no slow start, no runaway when leaving the Solar System).
- **Loader:** a minimal theme at the end of `web/space-loader.css` (hairline progress, one accent, fade transitions; the 3D cover now fades out instead of vanishing).

## Update: unlimited live loading and the downloaded date bundle

- **Live IRSA loading has no cap.** Every live archive request is paged (60 per request, `SPHEREX_LIVE_BATCH`), and the viewer keeps requesting the next batch until IRSA has nothing more: every date in one-per-date mode, every exposure in All exposures mode. Custom positions are no longer sampled down to 400 frames. Batches are ordered dates-first, so early batches already span the whole time range.
- **Stop / Continue:** a "Stop loading" button appears while batches chain. Stopping keeps everything loaded so far; "Continue loading" resumes from the same offset. Busy-worker and network errors are retried with backoff instead of ending the run.
- **Fixed:** live requests ignored the All exposures toggle (the server still read the old `sampling` option). It now honours `all_exposures`.
- **Bundle:** the dates downloaded with `scripts/download_more_dates.py` are included (354 new FITS cutouts plus previews). Barnard's Star 356→358 frames (40 dates, all IRSA lists), Epsilon Indi B 60→65 dates, Proxima Centauri 7→47 dates, R Dra 222→225 dates, RW Aur 80→103 frames. The previous sessions stay in the bundle; the index files point at the newer sessions, which contain every frame of the old ones.

## Update: Motion study (visit stacks, measured vs expected, verdicts, 2010–2026 time-lapse, Vesta track)

A **Motion study** panel now sits above the Spectrum section of the SPHEREx View (`web/observation-lab/motion-study.js`, `css/motion-study.css`). It reads precomputed results from `web/assets/motion-study/<field>/study.json` + PNGs, written by `backend/observation_lab_core/motion_study.py`. Render does no heavy work.

- **2010–2026 time-lapse at 4.6 µm:** WISE/NEOWISE W2 visit stacks and SPHEREx 4.6 µm visit stacks on one north-up 3″/px grid, with the measured position (blue ring), the catalog prediction (violet cross) and the catalog path drawn on each frame.
- **SPHEREx visits at one wavelength:** for 4.6, 3.4, 2.2 and 1.25 µm, only exposures whose wavelength at the field centre is in that window are median-stacked per visit, so blinking compares like with like.
- **Flipbook, Blink A/B (choose A and B) and Difference views.** The view state is shared in the URL (`?ms=field.tab.band.frame.mode`).
- **Astrometry:** the target is fitted in every exposure (saturated targets from the centroid of the saturated core). Each exposure is aligned on its own field stars, positions are averaged per visit, and straight-line + catalog-parallax fits are made for SPHEREx only, WISE/NEOWISE only and combined. Charts show measured vs expected, or residuals, with error bars.
- **Field-star null test:** the same pipeline run on field stars must show no motion (e.g. Barnard: 47/47 SPHEREx field stars static).
- **Brightness test:** ensemble differential photometry in 0.1 µm windows and 10-day bins, calibrated on the field stars. Saturated targets fall back to PSF-wing photometry with a stricter threshold.
- **Verdicts** (rule and numbers shown): Moves as predicted / Moves, but not as predicted / Expected motion too small / Expected motion not detected / Stays put / Changes in brightness, not position / Too bright for a reliable brightness test / Not measurable.

Current results: Barnard 10,407 ± 15 mas/yr (catalog 10,393), Epsilon Indi B 4,700 ± 17 (4,684), WISE 0855 8,313 ± 277 (8,152), Proxima 3,231 ± 593 (3,859, SPHEREx only): all **Moves as predicted**. RW Aur: **Changes in brightness, not position** (≈1.4 mag between dates at matching wavelengths, 34σ). R Dra: **Too bright for a reliable brightness test** (saturated almost everywhere).

Rebuild after adding data (minutes per target; `MOTION_STUDY_CACHE=<dir>` makes re-runs instant):

    python -m backend.observation_lab_core.motion_study            # all targets incl. vesta
    python -m backend.observation_lab_core.motion_study barnard

**More WISE/NEOWISE epochs** for RW Aur, R Dra and Proxima (needs IRSA access):

    python -X utf8 scripts/fetch_wise_epochs.py --field rw-aur --field r-dra --field proxima-centauri

**Vesta:** the study follows Vesta in two views: centred on it, or on a fixed patch of sky where the data window moves with it, so it keeps going after leaving the original field. Only the two bundled exposures are included so far; the first agrees with JPL Horizons to 3.7″. To add every SPHEREx exposure of Vesta, each cut out around its JPL position (needs IRSA and JPL Horizons access):

    python scripts/fetch_vesta_track.py --check
    python scripts/fetch_vesta_track.py            # whole mission, up to 240 exposures (--max to change)
    python -m backend.observation_lab_core.motion_study vesta

**Loader:** a soft spectral accent (blue → violet → amber) on the minimal loader.
