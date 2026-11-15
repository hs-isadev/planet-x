# Planet X continuation — acceptance report, 2026-11-10

**This is not an all-pass release.** The continuation implements the navigation, companion, animation and temporal-review changes, and preserves the observed-image-first design. Barnard's defensible measured motion and demonstrated R Draconis variability remain unresolved. Localhost/browser verification remains blocked in this executor. The connected GitHub upload is being completed in a separate delivery step below.

PASS means the stated check has evidence. For unchanged UI features, prior browser evidence is identified explicitly. It does not imply a fresh browser run. FAIL means an acceptance condition remains unmet or could not be verified; the reason is stated. Synthetic unit fixtures remain isolated under tests and are never served as observations.

## Exact commands

PowerShell, from the existing project:

```powershell
Set-Location 'C:\Users\thest\Documents\Codex\2026-11-09\new-chat-2\planet-x'
python -m pip install -r requirements.txt
python start.py
```

Open http://127.0.0.1:8000/ . The first screen is the SPHEREx viewer. No frontend build or API key is required. Use one ASGI worker. Refresh the browser after restarting so new JavaScript and new backend routes are loaded together.

If an older instance owns the port, stop that instance from its own terminal first. Do not start a second server over it.

Normal validation:

```powershell
python -m pytest tests -q
node --experimental-loader ./scripts/web-loader.mjs tests/scene_contracts.mjs
```

The Node check uses the bundled Three.js files and needs no npm installation. Optional browser QA uses `npm install` from qa/; it requires a working browser and localhost connection.

Restricted-executor validation used here:

```powershell
python scripts/check_offline.py
python scripts/validate_cached_release.py
python scripts/review_cached_sequence.py
```

The last two commands require genuine cached observations; the Laya command additionally needs the separately installed local model. Neither substitutes artificial frames. A fresh install needs real IRSA downloads, whose latency is outside this app's control.

Upload after normal GitHub connectivity is available:

```powershell
.\scripts\publish-github.ps1
```

The script uses the authenticated account and repository name planet-x. An explicit existing repository can be supplied with `-Repository owner/name`. Existing repositories receive a new source branch without a force push or automatic merge; new repositories are private. The CLI attempt in this session failed before any remote write. A later connected GitHub check authenticated hs-isadev but exposed no repositories or installations; hs-isadev/planet-x returned 404. No destination repository was available for publishing.

## P0 — core science

| Requested item | Result | Evidence and remaining limit |
|---|---|---|
| Degrees or sexagesimal RA/Dec fetch actual IRSA SPHEREx cutouts | PASS | Current parsing/WCS tests and preserved native IRSA pixels. All five cached targets rendered PNG responses with the original arrays unchanged. Fresh network fetches are blocked here; earlier live evidence is in science-acceptance.json. |
| Date-sorted flipbook: play, pause, speed, scrubber, loop and displayed date | PASS | Unchanged observed viewer; earlier actual browser playback in science-acceptance.json. Current cached sequences are chronological; each rendered frame retains its real date and archive URL in revision-validation.json. Browser playback was not rerun here. |
| All five presets use real data | PASS | Current cached rendered exposures: Barnard 55/364, Epsilon Indi B 9/449, WISE 0855 188/256, RW Aur 9/333, R Dra 8/2483. These are availability counts, not source detections. No placeholder observations are added. |
| Selectable field of view | PASS | Existing 2–20 arcmin control and validated coordinate/grid path. Barnard uses 12 arcmin; other preset defaults use 8. New uncached widths require network access. |
| WCS registration keeps sources aligned | PASS | Native headers map to the shared north-up/east-left ICRS TAN grid. Registration, masks and variance propagation passed current unit checks. PSF/calibration residuals remain possible. |
| Prevent wavelength changes from masquerading as motion | PASS | Default detector-only playback, optional 0.025 micrometer groups, fixed per-detector raw contrast and arithmetic compatibility checks remain. Temporal reviews and light curves keep detector/wavelength groups separate. Residual bandpass effects are disclosed. |
| Barnard widest-baseline difference, predicted marker and measured/catalog motion | FAIL | Current available source-wavelength-compatible span is 360.398705 days; a genuine difference and catalog predictions are produced. Catalog value: 10.39335 arcsec/year. Native masked-wing fits were attempted and rejected by coverage/fit-quality checks. No measured value is substituted. Only 55/364 exposures are currently cached; full-release proof is incomplete. See revision-validation.json and review-barnard-difference.png. |
| RW Aur and R Dra show brightness variation over time/light curves | FAIL | RW Aur now has a two-epoch same-footprint brightness curve: 31482.90 ± 401.51 and 31686.57 ± 160.77 microJy-equivalent over 188.46 days. These are common-aperture brightness indices, not reconstructed total source flux, and the difference is not significant at the quoted statistical errors. R Dra's cached subset has no repeated compatible narrow group. No intrinsic variability is claimed. |
| Loading, errors, caching and quick first frame | FAIL | Existing loading/error/pause/cache paths remain, and current cache tests pass. Earlier warm browser checks took seconds, but current startup/cold latency cannot be verified because localhost sockets are blocked. Previous cold downloads took 19–55 seconds; a seconds-fast cold sequence is not guaranteed. |

## P1 — SPHEREx features

| Requested item | Result | Evidence and remaining limit |
|---|---|---|
| Add and subtract different times | PASS | Current signed arithmetic/compatibility tests; earlier genuine browser outputs in science-acceptance.json. Missing pixels stay unknown. No PSF-matched subtraction is claimed. |
| Six detector groups and masked/variance-weighted stacks | PASS | Current grouping and inverse-variance/mask tests, plus earlier real browser stack evidence. Unknown wavelengths are not combined as valid narrow groups. |
| Click spectrum using per-pixel wavelengths | PASS | Native-pixel WCS-WAVE and aperture tests; earlier real quicklook spectrum had 121 valid points from 256 attempted exposures in science-context-validation.json. Masked apertures are rejected. This is not precision aperture-corrected spectrophotometry. |
| Date, band, detector, quality and contamination metadata | PASS | Existing metadata/flag panel retains dates, detector/wavelength, native numeric flags and usable fractions. Current cached evidence retains these fields. Many flags are displayed numerically. |
| URL parameters reproduce the view | PASS | Existing coordinate/FOV/frame restoration; earlier exact frame-118 browser evidence in science-context-validation.json. This revision preserves the handler. Release changes or evicted frames can require fetching. |
| Gaia and WISE overlays propagated to image date | PASS | Current real cached field: 149 Gaia markers, 132 propagated; 306 AllWISE markers, 80 placed using Gaia proper motion after a unique cross-match within 1 arcsec at the documented WISE MJD 55400 position. Unmatched or blend-swapped entries retain stationary WISE positions. AllWISE apparent-motion values are deliberately not extrapolated; IRSA advises against using them to predict other epochs. See revision-validation.json. |
| Release collections and endpoints in config | PASS | backend/config.json retains archive/release/catalog adapters and now includes the WISE motion reference epoch/documentation. Schema guard tests pass. This does not claim that the cached discovery is the latest available release. |

## P2 — polish

| Requested item | Result | Evidence and remaining limit |
|---|---|---|
| Consistent observatory design; science image is the hero | PASS | Science-first HTML and initialization remain; 3D loads on request. Earlier desktop/mobile evidence is retained in science-context-validation.json and final-core-validation.json. Current responsive/visual verification is blocked. |
| Observed, catalog and computed layer labels | PASS | Preserved observed/computed image labels; catalog predictions, common-footprint curves and 3D illustrations are explicitly identified. Visible 3D text says photos are flat and depth comes from catalog distances. |
| Tour through all five presets with captions | PASS | Unchanged five-target Tour with earlier actual completion in science-context-validation.json. Current live Tour was not rerun. |
| Aladin Lite coordinate chooser | PASS | Vendored Aladin module and chooser preserved; earlier two-canvas initialization/coordinate tests in science-context-validation.json. External CDS survey tiles need network access and are not verified here. |

## P3 and first impression

| Requested item | Result | Evidence and remaining limit |
|---|---|---|
| Optional linked 3D, labeled flat photos/catalog depth, only after science passes | FAIL | Optional 3D, flat-photo/depth text and a direct Images return button are implemented. The science gate is not all passed, so this cannot be called a completed P3 release. The user's requested 3D fixes are included, with their verification limits below. |
| Opening the app and selecting Barnard produces a real sequence within seconds | FAIL | Viewer-first initialization is preserved and cached pixels render. Current browser timing could not be measured. Earlier warm timings of 0.195–2.620 seconds are historical evidence, not a new timing or cold-start guarantee. |

## Additional requested behavior

| Request | Result | Evidence and remaining limit |
|---|---|---|
| Laya reviews throughout all given frames and filters noise | PASS | A fresh actual local-model run reviewed all 188/188 available WISE exposures in 118 detector/wavelength batches, in 122.203 seconds. It yielded zero accepted tracks and zero model-supported motion candidates. Of 256 discovered exposures, 68 were unavailable to this loaded-subset run. Endpoint context, unique coverage, per-source-pixel wavelength consistency, four independent nights, 30-day span, five-sigma motion, leave-one-out checks and common-motion rejection are implemented. Missing archive exposures and singleton wavelength groups cannot establish motion. See revision-laya-loaded.json. |
| Earth landing action appears only for selected Earth | PASS | Both Earth actions now require Earth and solar mode; the initial landing button is hidden until selection initializes. Source-level verification; current browser click verification remains blocked. Location-specific terrain still needs real tile access. |
| Bottom navigation focuses the selected object immediately | PASS | Bottom buttons and direct clicks use the same focus action. Focus begins a smooth turn and then travels at the existing orbit distance, respecting the safe body radius. Scene behavior is code-checked; live UI interaction remains unverified. |
| Known planets appear around stars when approaching | PASS | The previously unused NASA Exoplanet Archive table now supplies companion orbit layouts. Barnard's four catalog planets are matched by host name; other hosts use a strict match. Local orbit geometry and the system overview action passed Node checks. Planes, phases, appearances and display sizes are illustrative. No planets are inserted for unmatched hosts. |
| Planets persist after Sun zoom-out/zoom-in | PASS | Sun entry returns to the solar scene instead of a star-only local photosphere. Solar visibility is restored after local views. Node checks confirm visibility restoration; repeated browser zoom remains unverified. |
| Moons | PASS | Ten selected major moons are rendered/selectable: Moon, Phobos, Deimos, Io, Europa, Ganymede, Callisto, Titan, Titania and Triton. JPL mean scales/periods and radii are attributed. Display radii/separations, phase and planes are illustrative, not a complete moon census or satellite ephemeris. Geometry/record checks pass; visual verification remains blocked. |
| Targets have surrounding distant context | PASS | A real catalog host-star backdrop is added in solar, catalog and local views. Directions come from catalog 3D positions relative to the viewpoint; duplicate selected hosts are hidden. It is an incomplete catalog, with point sizes adapted for visibility. No fabricated stars are used as observations. Current appearance is unverified. |
| Allow close-up without reliable temperature, with a warning | PASS | Node behavior checks approach an object with no temperature. A persistent TEMPERATURE UNKNOWN notice identifies color/activity as illustrative and potentially inaccurate. This does not invent a temperature or reliable depth. |
| Smooth Earth trace, dust and nearby star streaks | FAIL | Quintic-eased linear-distance paths, longer travel legs, reduced FOV distortion and computed travel-particle streaks are implemented. Catalog background stars are retained. Fluidity and visual quality could not be checked in a browser, so the visual acceptance remains unverified. Particles are illustrative, not observed stars. |
| Avoid logarithmic camera flights | PASS | All flight calls now use linear world-distance interpolation; the logarithmic animation branch was removed. Node checks confirm that legacy callers passing the old flag still get linear flights. Wheel zoom retains continuous inertial scaling. |
| Turn back toward the object before returning | PASS | Return explicitly waits for a smooth turn toward the source before the reverse journey starts. Camera-scale rebases remain labeled as transitions. Live visual verification is blocked. |
| Faster fiery effects and moving sunspots | FAIL | New time-dependent plasma/corona shaders, differential spot rotation and faster magnetic-loop pulses are implemented; shader/uniform state and geometry checks pass. They are accelerated illustrations, not current solar observations. The requested visual realism has not been browser-verified. |

## Delivery and verification

| Item | Result | Evidence |
|---|---|---|
| Python unit checks available without sockets | PASS | 65 passed. The pytest config now limits discovery to tests/, excluding the separately installed Laya project's tests. |
| JavaScript syntax and scene/geometry behavior | PASS | All served JS modules parse. Node checks cover visibility restoration, linear flight mode, unknown-temperature approach, companion geometry, moon rendering/camera following, focus/return turn order and animated shader uniforms. |
| Full HTTP/ASGI test suite | FAIL | Five HTTP tests could not run: Windows asyncio socketpair blocks inside accept in this restricted executor. The full suite was stopped; no blocked check is counted as passed. The live IRSA test is separate and remains unrun. |
| Browser verification | FAIL | In-app preview binding failed. Native browser recovery then stopped because the tool could not confidently determine the current Windows browser URL. No further UI input was attempted. |
| Show the updated app on localhost | FAIL | The executor denies socket operations, including loopback, with WinError 10013. The owned server attempt was stopped. No running localhost server or rendered current browser view is claimed. Use the exact run command above outside this restriction. |
| Commit source locally | FAIL | Git metadata is read-only in this executor. Git initialization succeeded, but index.lock/HEAD.lock writes were denied, so there is no local commit. Source files and the release archive remain intact. The publish script can initialize/commit when run with normal repository write access. |
| Upload to GitHub | FAIL | `gh api user` and the publish script failed to connect to api.github.com before a remote write. This is a connectivity block; it is not evidence that the user's refreshed credentials are invalid. |

## Remaining broken or unverified items

1. No accepted Barnard measured motion or completed full-release widest-baseline proof. A catalog value is not an image measurement.
2. RW Aur has a usable brightness-index curve, but the tested pair does not establish variability. R Dra needs repeated compatible unmasked observations.
3. The newest Laya run covers the available 188 WISE exposures, not all 256 discovered files. Zero candidates is not evidence that the field contains no motion.
4. Cold first-frame/sequence latency, current browser appearance, fluid camera travel and repeated interactive zoom need a live run.
5. Ambiguous/unavailable WISE/Gaia associations, Gaia parallax omission, PSF differences, masked cores, resampling correlations and calibration errors limit scientific interpretation.
6. Current localhost handoff, Git commit and GitHub upload are not completed. No public deployment or Docker-host test was performed.

Core source remains under backend/ and web/. Runtime caches/model weights, browser screenshots and the historical unused frontend build are excluded from the delivery source archive. Earlier evidence is retained as earlier evidence; it is not relabeled as a new run.

## GitHub hosting follow-up

The linked GitHub account is authenticated as hs-isadev. Repository discovery returned no accessible repositories and no installed-account repository grants; hs-isadev/planet-x returned Not Found. This does not prove that all private repositories are absent. No GitHub files, branches or Pages deployment were created.

GitHub Pages serves static files and does not execute this app's Python backend. To keep arbitrary real SPHEREx queries, WCS/photometry, catalog processing and local-model review, the complete app needs Python/Docker-capable runtime hosting, with source stored on GitHub. The existing Dockerfile and start.py are prepared for that path. Publishing only web/ to Pages would break /api/ calls and is not a complete deployment. Official reference: https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site .

A destination repository with write access and a Python-capable deployment destination are still required.


## Connected GitHub delivery, 2026-11-10

The refreshed integration now exposes hs-isadev/planet-x with write access. Its existing main branch contains only the starter README at commit 6fdfe9c5906a9a2dda930702fbb0bcfceab7fe25. The source snapshot is prepared as a child of that commit, preserving repository history. The historical connectivity failures above describe earlier attempts. A fresh check passed 65 offline Python tests (34.99 seconds) and the Node scene/geometry checks. Local Git metadata and CLI network restrictions remain; this delivery uses the connected integration. Source publication does not create a running public deployment, and the science/visual limits above remain unchanged.
