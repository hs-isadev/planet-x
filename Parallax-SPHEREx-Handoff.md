# Parallax SPHEREx coverage handoff

**Goal:** Add as many verified, distinct observing dates as the archives support. Work on the five presets first: Barnard’s Star, Epsilon Indi B, WISE 0855, RW Aurigae, and R Draconis. Then extend coverage to the other stars in the app. Aim for more than 400 dates per target where coverage supports it, and keep adding verified dates beyond that. SPHEREx is the primary source. Real images from other observatories and wavelength bands are approved supplements.

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

1. **Search all five presets first.** Query IRSA SIA and TAP for DR1 and QR3, including deep-field collections where applicable. Compare candidates against saved UTC dates before downloading. Search along the epoch-dependent positions of high-proper-motion targets, especially WISE 0855. Verify the expected position against the FITS WCS and check that it lands on usable pixels. Try the public AWS mirror when the exposure key is known.
2. **Search other observatories for the same five targets.** Start with the leads below. Use observing logs and catalog rows to locate image products. Count a date as added after retrieving the science image and verifying usable coverage. Record saturation and nondetection where applicable.
3. **Expand to the other stars.** Queue the rest of the app’s star catalog, starting with nearby stars and fields with strong repeat coverage, including the SPHEREx deep fields. Prioritize by distinct dates available and time baseline. Validate coverage per target, even when two stars share a field.
4. **Bundle and verify.** Save validated FITS, provenance, observation timestamps, and previews. Verify playback in chronological order and check that each new date remains available after a restart. Report before-and-after date counts per star and mission, the deduplicated total, the first and last dates, and any gaps in retrieval or coverage. Use compatible detector and wavelength data when measuring motion.

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
