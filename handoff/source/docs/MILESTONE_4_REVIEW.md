# Milestone 4 review — 2026-11-09

Scope incorporates the requested universal 3D viewer: arbitrary-coordinate fields plus an all-sky nearby catalog volume, rather than a fixed five-object scene.

- PASS: production build; 49 numerical/API tests; real-data browser checks for scene rendering, selection, focus/zoom/reset, five widths down to 320px, field queries and a source→SPHEREx→3D return with selection retained.
- PASS: a live query returned 1,000 actual Gaia DR3 catalog records via Gaia@AIP in 3.9 seconds. The 25 pc selection was capped; the UI explicitly labels the incomplete sample.
- PASS: positions computed from actual ICRS coordinates and catalog distances. Parallax inversion requires S/N ≥ 5; otherwise usable GSP-Phot model distances are clearly labeled. Unknown/poor depth stays in a separate list.
- PASS: nonlinear distance intervals, high-RUWE/model markers, optional radial uncertainty lines, parsec/light-year scale at the focus plane, symbolic markers and an explicit flat-photo/catalog-depth legend.
- PASS: direct RA/Dec inputs for 3D fields independent of the image player. Larger/smaller nearby-volume radii and catalog name/ID filtering work within the configured query cap.
- FIXED after screenshot review: the mobile image-control dock no longer overlays the 3D scene. Mobile integrity text uses full available width. Sub-milliparsec intervals retain meaningful digits in the inspector.
- LIMIT: optional SIMBAD fallback is implemented and tested with deterministic catalog records, but its live service is unavailable here. It does not insert hardcoded brown-dwarf distances.
- LIMIT: Gaia does not contain every brown dwarf/star, the sample is capped, and Gaia GSP-Phot values are model-derived. This is not a complete universe or a completeness-corrected stellar census.
- LIMIT: the SPHEREx jump reaches the correct coordinate view but full TAP retrieval remains service-dependent. No successful WISE 0855 motion measurement or five-preset live tour is claimed.

Screenshots: screenshots/milestone-4-real-3d-*.png. Real source/uncertainty samples and query notes are in live-space-results.json. No decorative stars are present in the catalog scene.
