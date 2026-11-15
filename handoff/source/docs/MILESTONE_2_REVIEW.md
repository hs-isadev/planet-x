# Milestone 2 review — 2026-11-09

Implemented and tested before starting subsequent milestones. Scope incorporates arbitrary sky positions and a browsable released archive; presets are shortcuts.

- PASS: production build; 34 offline tests (one live TAP test deselected).
- PASS: genuine QR3 cloud listing and native FITS cutouts. Two actual D1 exposures on 2026-07-20, MJD 61241.004784375 and 61241.006276632, registered at RA 232.663579354°, Dec −10.7213238583°.
- PASS: real-data browser tests at 1440, 1024, 768, 390 and 320 pixels, no horizontal overflow or JS errors. Screenshots in screenshots/milestone-2-*.png.
- PASS: detector/wavelength filtering, split comparison, signed difference, addition, inverse-variance stacking in a configurable wavelength bin, native-pixel aperture spectrum, quality chips and FOV slider.
- PASS: manual motion fit tested numerically, with RA wrap and correct arcsec/year units. The actual two-exposure demonstration spans only minutes; the app refuses to claim a motion rate from this insufficient baseline.
- FIXED: no images on the initial screen. It now opens a real released field via the documented public S3 mirror, with the actual coordinate/date metadata, rather than labeling it as WISE 0855.
- FIXED: masked center pixels no longer erase the geometric center-wavelength metadata.
- LIMIT: TAP and SIMBAD still time out, so complete coordinate discovery and named-preset live sequences remain unverified. Cloud browsing is explicitly a manually selected set, not complete sky coverage.
- LIMIT: spectrum is labeled quicklook: approximate per-pixel WCS-WAVE wavelengths, no PSF/aperture correction, no calibration or confusion uncertainty. Masked/clipped apertures are missing, not filled or rescaled.
- LIMIT: stacks retain resampling covariance/systematic caveats; difference images do not apply PSF or photometric matching and are not detections.

Data source: official nasa-irsa-spherex public bucket, exact file keys recorded in live-analysis-results.json. Source photometry at an arbitrary valid aperture returned 39.82 ± 118.53 μJy in one observation: this is not a significant source detection.

Universal 3D requirement retained: catalog distances over arbitrary fields and an all-sky nearby-star mode; no depth inferred from image pixels. Later milestone work is authorized by the user's “continue with the next steps” instruction.
