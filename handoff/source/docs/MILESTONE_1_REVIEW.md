# Milestone 1 review — 9 November 2026

**Status: implementation built, acceptance blocked by real archive access.** No work on Milestones 2–4 was started.

## Verification

| Check | Result | What it establishes |
| --- | --- | --- |
| React + Vite + Tailwind production build | PASS | Production assets compile successfully |
| Python core tests | PASS: 22 | Coordinate parsing, WCS orientation, mask propagation, PNGs, job state, cache/deduplication, SIMBAD-result mapping and explicit failure behavior |
| Real WISE 0855 smoke test | FAIL | Connection reset at https://irsa.ipac.caltech.edu/TAP/sync, before receiving observations |
| Direct SIMBAD resolution through astroquery | FAIL | Capabilities endpoint connection failed for all four queried preset targets |
| Browser UI and transport checks | PASS | Chromium exercised actual UI; transport state uses test-only network fixtures |
| Responsive overflow | PASS | Widths 1440, 1024, 768, 390 and 320 CSS pixels; no horizontal page scroll |
| Dark/light themes | PASS | Screenshots captured and inspected |
| Phone controls | PASS | Mobile bottom sheet opens/closes; Escape returns to the page |
| WISE 0855 visually moving in real SPHEREx frames | UNVERIFIED | No real frames could be downloaded. No motion claim is made |
| All five presets loading real frames | UNVERIFIED | WISE input parses; four coordinate lookups and all archive downloads require live access |
| Public hosting | NOT DEPLOYED | Required Python backend cannot run on available JavaScript Worker hosting; Docker recipe included |

One nonfatal installed-library warning occurred: FastAPI/Starlette reports a future change to its httpx test-client adapter. It does not affect the passing tests or runtime server health.

## Screenshot review

- screenshots/milestone-1-desktop.png: dark blue mission-control layout; warm infrared heading and actions; left coordinates/presets, central framed science viewport, right readout/display controls, bottom filmstrip. No observation is loaded and the viewport explicitly says so. Decorative orbit and target swatches are labeled UI art rather than image data.
- screenshots/milestone-1-light.png: light theme with high-contrast text; science viewport remains dark so an image is not blended into page decoration.
- screenshots/milestone-1-mobile.png: 390-pixel single-column view; coordinate inputs side by side, target cards, viewer, filmstrip and metadata. Fixed mobile control dock opens the display sheet.
- screenshots/milestone-1-mobile-controls.png: display palette/stretch/black/white controls in a bottom sheet.
- screenshots/milestone-1-archive-error.png: real failed archive request, with an unavailable state and explicit no-substitute-image explanation.

No screenshot showing test-generated pixels is used as evidence of observed SPHEREx science. Automated transport tests intercept responses within the isolated browser test only. They do not alter the production server or create a demo-data mode.

## What works

The core software pipeline, responsive interface, player controls, rendering modes, masking, cache reuse and chronology are implemented and pass fixture-based tests. The backend is configured only from the official IRSA interfaces. API error states prevent an unreachable archive from becoming a false success. A production frontend and FastAPI application can be run from the supplied source or Docker recipe on a suitable Python host.

## What remains broken or unverified

Outbound IRSA and SIMBAD connections from the execution runtime fail with reset/service errors. This prevented genuine image retrieval and successful preset-coordinate resolution. Reading official documentation succeeded through the browsing service, but that does not give the running Python application access to the archive. The source schema/query/cutout workflow is documented, not live-validated here.

The smoke test deliberately fails at the actual remote service. It does not silently skip a failed request, substitute unrelated WISE images, or inject a moving object. Its coverage check does not prove source identity or observable motion. The WISE 0855 motion acceptance gate remains open and scientifically substantive: sensitivity and time baseline may not permit a visible source in available SPHEREx images.

The cache budget is applied on idle cleanup rather than a hard active-job quota. The server is intended for a small public demo with one process, bounded active jobs and rate limits. A larger deployment needs shared job storage and coordinated rate limiting. The Docker image itself was not built in this session.

## Required acceptance work before Milestone 2

1. Run from a host with verified access to IRSA and SIMBAD; rerun the live smoke test and resolve all catalog presets.
2. Load and play real observations for all five targets. Check source URL, time order, band, wavelength, masks, orientation and cache reuse against FITS metadata.
3. Inspect long-wavelength WISE 0855 observations at matched wavelengths and separated epochs. Establish source identity relative to stationary background objects and document real visible motion if the data support it. Record a negative sensitivity/baseline result if they do not.
4. Deploy the included app on a Python-capable host with HTTPS and a writable cache, then repeat browser checks using the public URL.

Stop at Milestone 1. Continue only after the user says “continue.”
