# Planet X follow-up · 11 November 2026

The previous server log shows successful startup and expired session IDs. Job IDs belong to the running process. Search the same coordinates after a restart and use Review / resume to restore saved Laya crop receipts.

The active checkout is C:\Users\thest\Downloads\planet-x. The UI updates are served directly from the checkout. Refresh [port 8000](http://127.0.0.1:8000/) to load the new image and star controls. The new Python comparison and spacecraft routes were verified on [port 8001](http://127.0.0.1:8001/) so the active archive job on port 8000 could keep downloading. A fresh python start.py process includes the new routes.

| Original item | Evidence and remaining scope |
|---|---|
| 1. Diagnose 0 reviewed | Archive, preparation, model and inference stages have separate counts and errors. Archive completion and pause now report the matching stage. |
| 2. Incremental Laya | Real WISE inference proceeded before archive completion. Browser cancellation and resume preserved unique receipts. The original test sampled coverage, rather than reviewing every eligible crop of all five presets. |
| 3. Faint detail | Overlapping native-sampling crops preserve faint values and record coverage. Model suggestions stay separate from measured changes. |
| 4. Scientific comparison | The optional source-pair check uses released CWAVE/CBAND, local ePSF cross-convolution, ZODI subtraction, conservative masks and propagated error bounds. A translation estimated on reference stars is checked on independent stars before a result can be measured. General flipbook red residuals are still quicklooks. |
| 5. Controls and sensitivity | The previous real identity, multi-epoch and synthetic injection controls are recorded. Four new controlled tests cover source displacement, brightness change, PSF/band mismatch and interpolation masks/error bounds. The real astronomical false-positive rate remains unmeasured. |
| 6. Five targets | All five previously played real observations and completed some Laya reviews. WISE reached 256 of 256 loaded exposures in the follow-up. Validated astrophysical motion across the five targets remains open. |
| 7. Playback | Real ready frames play chronologically with buffering, dates and loading gaps. New zoom and pan preserve coordinates. Wider sky field requests new data for the same position. |
| 8. Actual browser workflow | Real WISE cancellation/resume, noise toggle and playback were recorded in the initial run. The follow-up verified the calibrated comparison, evidence export, spacecraft positions, zoom and star rendering through the browser. |
| 9. Spectrum | Native aperture measurements show uncertainties, quality, dates and links. Cached released wavelength products now supply CWAVE/CBAND where available. Approximate values are labeled separately. The browser exported 95 usable points with released wavelength calibration. |
| 10. Candidate review | Fixed-aperture spectrum and brightness history, manual marks, source-pair comparison, classification and reproducible export are available. Automatic association of one source across every suitable epoch remains open. |
| 11. Spacecraft observing view | Real FITS positions at the start and end of the selected exposure are displayed with the real detector footprint. The dashed full orbit guide is illustrative. Live attitude and continuous trajectory remain unavailable. |
| 12. Earth travel | The tested route reached Earth in 14.2 seconds with visible streaks, Stay on Earth, and Return to object. |
| 13. Star field | The capped catalog stays selectable in one batch. Round profiles with soft halos replaced square dots. The new Edge run still recorded 512 catalog points, one batch, 9 draw calls and 6.2 ms 95th-percentile frame interval. |
| 14. Integrated verification | Earlier five-target evidence and the latest browser records are linked below. Scientific limitations are surfaced as unassessed results. |

Sun sky was verified in Edge with a fixed 1 AU camera radius and hidden planetary geometry. A right-click off center sent RA 133.92861526°, Dec −8.93599459° to the archive. IRSA returned 258 exposure records and the browser rendered a real cutout. Returning to Sun sky restored the pointing direction. The backend suite passed 83 tests with one skip.

The science check requires the same detector and release on different dates, at least 80% overlap of the published wavelength intervals across contributing pixels, five reference stars, a held-out registration residual at most 0.35 pixel, and a held-out PSF width difference at most 20%. Published bandwidths are treated as intervals. This approximates passband overlap, and the local PSF model and error estimates do not cover all systematics. On the 18 sampled pairs at preset field centers and 74 nearby-source checks, no pair cleared every gate. The browser WISE example had 1,689 overlapping usable pixels and one usable reference star. The app kept that source unassessed.

- [Prior five-target, Laya, control and performance evidence](PIPELINE_VALIDATION.md)
- [Calibrated pair and spacecraft browser result](calibrated-browser.json)
- [Zoomed source click, 12-arcmin cutout and round-star rendering](image-and-stars-browser.json)
- [Sun sky browser result](sun-sky-browser.json)
- [IRSA science and calibration products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/)
