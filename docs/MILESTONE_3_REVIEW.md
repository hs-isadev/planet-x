# Milestone 3 review — 2026-11-09

Completed the milestone implementation and checks before starting 3D work.

- PASS: production build; 37 offline tests; real-data Chromium checks.
- PASS: Gaia DR3 and AllWISE catalog markers over the real SPHEREx field. Gaia angular proper motion is applied to the image date where available, without a modeled parallax displacement. Catalogs and projected/propagated positions are labeled separately from observed pixels.
- PASS: cloud-backed URL reproduction with ra, dec, fov, frame and explicit archive object keys. A restarted session can reconstruct the selected exposures instead of relying on an in-memory job ID.
- PASS: current image PNG export with source/date and guides; observed-frame GIF export. Catalog/manual overlays are not included in PNG and that limit is stated in the export notice. GIF uses fixed image contrast and date/band labels.
- PASS: Aladin Lite landing globe initialized; screenshots captured. Its DSS2 optical context and computed grid are explicitly separate from SPHEREx. External tiles can be slow/unavailable even when navigation initializes.
- PASS: guided tour completes all five stops under deterministic unavailable-data browser tests. Real five-preset playback remains unverified because SIMBAD and IRSA TAP access are unreliable. Missing stops are acknowledged and skipped; no data are fabricated.
- PASS: responsive overflow checks through 320px. Browser reported zero JavaScript errors.

Known limits: not all AllWISE apparent-motion estimates are proper motion. The app retains stationary-solution AllWISE coordinates and displays that limitation instead of applying an unjustified 16-year extrapolation. Catalog rows are capped and truncation is explicitly recorded. Large catalog responses may take tens of seconds; the science image remains available. Embeddable layout uses embed=1 and a same-origin iframe; public hosting remains outstanding.

Aladin Lite 3.8.2 is bundled as an independent lazy-loaded module; its LGPL/GPL license files are retained under third_party/aladin-lite and its logo/link remain in the map. Gaia source attribution is ESA/DPAC, with the served endpoint retained per row. AllWISE is from the documented IRSA cloud Parquet dataset.
