# SPHEREx pipeline validation · 11 November 2026

The active checkout is C:\Users\thest\Downloads\planet-x. The Documents copy was older and outside the writable workspace. The documented startup command, python start.py, served the application at [127.0.0.1:8000](http://127.0.0.1:8000/). The first shell launcher attempt failed before execution with HRESULT 0x8007000F. A separate execution path started Python and verified HTTP responses and browser behavior.

## Observation and model evidence

The original WISE 0855 job had 54 ready observations while Laya had prepared four and reported “Loading real frame 5 of 256.” The sequence worker was serially fetching the manifest before inference. Historical worker stderr also recorded a Windows pwd import failure and a float32/bfloat16 mismatch. The current local checkpoint produced actual inference results. An intermediate resume exposed a transient Windows file replacement error, addressed with bounded retries. [Diagnostic and resume evidence](pipeline-live-evidence.json)

Sequence review consumes ready frames from the archive job. Two registered observations from the same release and detector with at least one day of separation and a preliminary wavelength match can enter crop review. Tiles overlap and retain up to 64 × 64 registered samples in each 256-pixel panel. A common signed asinh stretch retains values below 2.5σ. Inference has a 240-second request limit, lock waits are bounded, and cancellation terminates the worker process tree during inference. The saved report includes crop coordinates, exposure IDs, dates, source links and coverage. A resumed review uses saved crops and counts unique exposure IDs.

| Target | Discovered | Loaded | Prepared | Laya reviewed | Preliminary compatible | Pending | Unavailable |
|---|---:|---:|---:|---:|---:|---:|---:|
| Barnard’s Star | 364 | 246 | 246 | 2 | 232 | 118 | 0 |
| Epsilon Indi B | 449 | 22 | 22 | 2 | 3 | 427 | 0 |
| WISE 0855 | 256 | 133 | 133 | 37 | 73 | 123 | 0 |
| RW Aurigae | 333 | 46 | 46 | 7 | 7 | 287 | 0 |
| R Draconis | 2483 | 214 | 214 | 2 | 176 | 2269 | 0 |

These bounded runs exercised all five presets with real IRSA products. The archive manifests may be cached. The browser included every ready exposure in chronological playback with buffering and observation dates. The validation intentionally stopped after sampling successful inference, so the counts show coverage at the time of the test. RW Aurigae initially had 19 loaded and no compatible pair. Further downloads let it reach seven reviewed. **Validated scientific motion assessments remain at zero for every target.** Preliminary compatibility counts exposures with at least one eligible crop. A reviewed exposure has every currently eligible crop reviewed. Some pixels can remain masked or unmatched. [Five-target browser run](pipeline-browser.json) · [Five-target model run](pipeline-five-laya.json)

A fresh typed sexagesimal search at RA 156.09328167°, Dec −41.64466331°, width 4 arcmin discovered 454 observations and rendered a real D6 cutout. The FITS file contained IMAGE, FLAGS, VARIANCE, ZODI, PSF and WCS-WAVE extensions. [Typed coordinate workflow](user-coordinate-workflow.json)

The final WISE browser run cancelled at 55 reviewed exposures and 119 completed crops. Resume advanced to 57 reviewed exposures and 122 crops. The receipt contained unique exposure IDs and crop keys. The two browser cancellations returned in 2.7 and 1.0 seconds. The resumed observation job had 191 ready cutouts and 65 pending. [Browser progress and cancellation](laya-browser-progress.json) · [Screenshot](laya-browser-progress.png)

## Scientific scope

- Native FITS files remain the source for brightness, flags, variance, ZODI, PSF and WCS. The disk cache can evict bulky FITS files. Original archive links remain available. The observed image and the noise suppression toggle use separate rendering paths.
- The quicklook uses conservative masks, bilinear WCS reprojection with squared interpolation weights for variance, a clipped local median background and archive variance with an empirical noise floor. Invalid or missing wavelength pixels cannot produce a red residual. Same-release and same-detector references limit cross-band artifacts. The nominal 0.025 µm tolerance is a preliminary review screen.
- IRSA documents WCS-WAVE for visualization and CWAVE/CBAND for precision science. This release has not validated filter-response overlap from those calibration products, the spatially varying ePSF, field-star registration, or calibration and resampling covariance. The ZODI model is preserved in the FITS. The quicklook estimates a local background independently and can suppress diffuse structure. Red residuals remain uncertain candidates. [IRSA data products](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-products/) · [IRSA data access](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/)
- Registration and PSF stress controls used copies of the same 12 real exposures. A 0.65-pixel registration offset produced 3,361 red pixels among 87,301 eligible pixels. Blurring by 0.8-pixel Gaussian σ produced 1,918 among 60,631. Neither manipulation moved an astrophysical source. These artificial stresses illustrate why PSF matching and registration are required for motion validation.
- Twelve unchanged real exposures produced zero red pixels in identity controls. Real cross-date comparisons produced residuals of unresolved origin. The astronomical false-positive rate remains unmeasured. [Real multi-epoch comparisons](pipeline-multi-epoch.json)
- Synthetic moving and variable sources were injected into copies of real arrays only for offline testing. The stationary injections produced 0 flags in 443 tested neighborhoods. The moving-source residual recovery was 0/111 at nominal 3σ, 6/103 at 5σ, 31/109 at 8σ and 53/110 at 12σ. Variable-source recovery was 0/109, 3/111, 29/110 and 54/108 at the same amplitudes. Recovery means at least one red pixel near the injection. The experiment repeats backgrounds and uses a simple Gaussian PSF. Motion classification and Laya accuracy remain unvalidated. [Injection results and controls](pipeline-controls.json)

## Source and spacecraft tools

The browser measured a real WISE field aperture and reported 39 usable measurements across 208 loaded exposures in the recorded run. The spectrum has uncertainty bars, available wavelength coverage, date overlays, quality warnings and original exposure links. Molecular ice features and atomic hydrogen are cited as reference windows. The windows illustrate nominal resolving power. Chemical identification requires calibration and independent spectral evidence. The fixed-aperture brightness history, frame jumps, manual motion marks, volunteer classification and evidence export support a reproducible review. The browser measured three points in a D2 brightness-index curve using the common unflagged footprint. The request used available data and reported the statistical and calibration limits. Automatic source tracking with calibrated centroids remains proposed. [Spectrum and observing workflow](observing-workflow.json) · [Screenshot](observing-workflow.png)

The observing view uses FITS offsets and celestial WCS to project the cutout footprint onto the original detector. The telescope field outline and polar orbit are illustrative. Spacecraft attitude, trajectory and full-field imagery are unavailable in this view. [NASA/JPL instrument and orbit](https://www.jpl.nasa.gov/press-kits/spherex/quick-facts/)

## 3D verification

The original backdrop contained 4,122 host-star sprites. The most crowded 12° angular cell contained 938 catalog rows. The renderer now draws at most 512 real catalog points in one batch, with two sources per cell and selectable positions. In the same headless Edge test, scene draw calls went from 99 to 9 and the 95th-percentile frame interval went from 12.2 to 6.2 ms. Laptop performance depends on the local renderer and viewport. [Before](scene-before.json) · [After](scene-after.json)

A browser click selected HD 42618 and opened its one cataloged planet. Zoom in and out retained the planet. A JavaScript conversion error had made travel opacity invalid. The revised effect was visible during flight, and Earth arrival took 14.2 seconds on the final tested route. Stay on Earth, Return to object and direct Solar System navigation passed. [3D workflow](scene-workflow.json)

## Reproduction

Run python -m pytest tests -q for backend contracts and synthetic regressions. The scripts qa_pipeline.cjs, qa_laya_progress.cjs, qa_user_coordinates.cjs and qa_observing_workflow.cjs drive the local app in Edge with the checkout’s Playwright installation. Run validate_pipeline_controls.py for offline controls and validate_multi_epoch.py for comparisons of genuine cached products from saved Laya receipts. The browser tests depend on native FITS availability and the local Laya installation. The final backend suite passed 79 tests with one skip. Frontend startup, full sequence playback, scene rendering, camera paths, journey round trip and scene asset checks passed.
