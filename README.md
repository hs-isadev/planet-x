# Parallax — Planet X / SPHEREx Observatory

A science-first viewer for real SPHEREx infrared observations. Enter RA/Dec or select Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae or R Draconis. The first screen is the science viewer; optional catalog/ephemeris 3D context is loaded separately. This is an independent project, not an official NASA service.

**The release is not all-pass.** See [the complete acceptance report](docs/CURRENT_STATUS.md) for every requested item, current evidence, unresolved science results and verification limits. No catalog motion is substituted for a failed image measurement.

## SPHEREx View and Free View

**SPHEREx View** opens the image sequence. Choose **Satellite camera** from its toolbar to start from the selected archive exposure's detector orientation. The amber reticle marks the selected field. Drag or swipe to turn and scroll or pinch to zoom. Use **Center target** to return to the marker. Right-click a direction or use **Search view center** to search IRSA.

**Free View** keeps the 3D orbit, pan, zoom, and object selection controls. On a phone, drag with one finger to orbit and pinch with two fingers to zoom. Open **Destinations** to switch between the Solar System, nearby catalog stars, and target systems. You can also zoom out from the Solar System into the stellar neighborhood.

The catalog sky is the celestial [NASA/Goddard Scientific Visualization Studio Deep Star Maps](https://svs.gsfc.nasa.gov/3895/) 4K image, based on the Bright Star, Tycho-2 and UCAC3 catalogs. It provides visible-light context. The archived infrared observations are in the SPHEREx sequence. The spacecraft position comes from the selected FITS header when present. Free look is an illustrative rotation at that viewpoint. The reticle marks the selected coordinates. The sky map is fetched on first use and cached locally. A coordinate grid remains available if the texture or WebGL fails.

**Trace back to Earth** follows one illustrative, curved flight to the sunlit side. The camera turns during the flight with gentle sideways glances. The source sky chart is optional after arrival. The flight uses a single path and rebases from parsecs to AU without a scheduled stop.

## Infrared spectrum and absorption bands

In **SPHEREx View**, load a field, open **Measure a source**, choose **Infrared spectrum**, and tap or click the object in an observed frame. The chart uses aperture measurements from cached native SPHEREx FITS at that sky position. Select a UTC observation date to inspect its samples and uncertainties, and optionally overlay a second date. **Show reference absorption bands** displays approximate methane, carbon dioxide, and carbon monoxide windows for visual comparison. The exposure list gives dates, detector IDs, flux and uncertainty or an exclusion reason, plus links to the archive.

The quicklook uses approximate pixel wavelengths and lacks PSF deblending and aperture correction. Reference windows are approximate guides based on the [AKARI brown dwarf study](https://hero.epa.gov/reference/2669638/). Different dates and wavelengths can sample variable brightness. An unresolved companion can be blended with its host. A moving Solar System body needs an ephemeris at each exposure. A visual match alone cannot establish composition. IRSA provides a [PSF-based spectrophotometry tool](https://irsa.ipac.caltech.edu/onlinehelp/spherex/spherex/sp.html) for a source with a known position.

## Run

Python 3.12 is recommended. From this project folder:

```powershell
python -m pip install -r requirements.txt
python start.py
```

Open http://127.0.0.1:8000/ . No frontend build, Node, API key or paid service is required to run the app. Refresh after restarting an older server so new backend routes and JavaScript load together. Use a single ASGI worker: session manifests and rate limits are in memory.

The active frontend is **web/** and the Python backend is **backend/**. The historical frontend/ build is not used or included in the delivery archive.

LAN/host option:

```powershell
python start.py --host 0.0.0.0 --port 8000
```

Public hosting requires a Python-capable host, HTTPS, persistent cache storage and an appropriate resource budget. No public deployment is verified. A Docker recipe is included but was not tested in this executor.

## Observations and analysis

- Degrees or sexagesimal RA/Dec, selectable 2–20 arcmin field, all five named presets and `?ra=&dec=&fov=&frame=` links.
- Genuine IRSA native FITS, WCS registration, original quality masks, chronological playback, speed, loop, scrubber, date and metadata. Missing pixels remain unknown.
- Default playback includes every available detector in chronological order, with pending/unavailable exposures marked in the full timeline. Detector and wavelength filters are optional. Narrow 0.025 micrometer groups, fixed per-detector contrast, six-array stacking and compatible-frame add/subtract reduce cross-band confusion. They do not remove PSF/calibration systematics.
- Click an aperture for a quicklook spectrum using native per-pixel wavelengths. Aperture flux is not precision aperture-corrected spectrophotometry.
- Barnard comparison samples the wavelength map at the predicted source position, selects a compatible time baseline, shows a real difference and predicted markers, and attempts a free native PSF-wing fit. Masked or poor fits remain unavailable; the catalog's roughly 10.4 arcsec/year is not called a measured shift.
- Light curves search compatible loaded groups. If native apertures fail, a fixed common footprint of valid registered pixels can supply a brightness index. Masked cores are excluded in every epoch, not reconstructed. Statistical errors omit resampling correlations, PSF and calibration systematics. A plotted change alone does not establish intrinsic variability.
- Gaia overlays apply available angular proper motion. WISE date-dependent markers use Gaia astrometry only for unique associations at the documented MJD 55400 AllWISE motion-fit position, within 1 arcsec. Unmatched/blend-swapped sources retain stationary WISE positions. AllWISE apparent motions are **not** extrapolated: IRSA advises that they cannot predict positions at other epochs. Annual parallax is omitted from these overlays.
- Tour captions, optional Aladin Lite coordinate selection, exports and provenance labels remain. Aladin survey tiles require CDS network access.

Observed, catalog and computed layers are distinct. A loaded field or red residual is not a source identification, a motion detection, or evidence for Planet X. Red highlighting and noise suppression are computed quicklooks; they never alter preserved observed arrays. Wavelength changes, confusion and artifacts can mimic change.

Keyboard: Space play/pause, arrows step, brackets change speed, slash opens search, Escape closes. Mobile Search expands coordinates and auxiliary tools.

## Optional 3D context

**Photos are flat. Stellar depth comes from catalog distances; Solar System positions are computed.** Images returns directly to the SPHEREx viewer. This context does not replace the observations.

Bottom navigation and direct body clicks share a smooth focus action. Approach changes distance deliberately. Camera zooms interpolate distance geometrically with quintic easing. Journeys accelerate and decelerate while keeping the camera facing forward. Return journeys turn toward the source before moving; they no longer turn back toward Earth during departure. Explicit transitions distinguish parsec, AU and normalized stellar-illustration scales; they are not physical spacecraft trajectories.

A persistent Solar System button, a stellar-strip home entry and a target-menu entry return to the Sun and planets. Earth journeys offer Stay on Earth as well as Return to object. The Sun returns to its planetary scene rather than a star-only closeup. Known catalog exoplanets appear in automatically framed system overviews, with named planet buttons and a separate stellar-surface closeup. Planets remain visible through deliberate display enlargement; systems with no installed orbit are labelled explicitly. NASA Exoplanet Archive periods/orbital scales are used; circular planes, phases, radii/display enlargement and appearances remain illustrative. No orbit is invented for an unmatched system.

Ten selected major moons are present: Moon, Phobos, Deimos, Io, Europa, Ganymede, Callisto, Titan, Titania and Triton. JPL mean orbital scales/periods and radii are attributed in web/assets/moons.json. Display radii and separations are enlarged independently. Circular layouts/phases are illustrative, not satellite ephemerides or a complete moon census.

A real catalog host-star backdrop supplies surrounding context. It is an incomplete sample; point sizes are adapted for visibility, not measured brightness. Plasma, faster sunspots, a faint white coronal illustration, magnetic loops, dust and travel streaks are computed illustrations, not observed events or measured surface maps. Planet rotation is independently accelerated for visibility rather than tied to orbital playback. The Solar System loading cover remains for at least five seconds and waits for all requested appearance maps and models to settle before revealing the scene. Closeups with unknown temperature carry a persistent warning that appearance may be inaccurate. Unknown temperature does not supply an invented temperature or reliable distance.

Earth landing actions appear only for selected Earth. Location-specific terrain requests compiled Mapzen elevation tiles for the clicked/visible direction. Missing elevation remains an error; a different site is not substituted. Colors, astronaut geometry, water context and lighting are illustrative. No current weather or measured local temperature is claimed. No verified terrain walker for other bodies is installed.

## Local Laya review

The optional image-capable Laya Vision fork runs locally: https://github.com/r33drichards/laya-vision . It is separate from the unrelated desktop notification app. No API key or paid inference service is used; review images are not sent to an external inference service.

Install after the main requirements:

```powershell
python scripts/setup_laya.py
python start.py
```

Git and an initial network connection are required. Runtime weights and the isolated virtual environment are not included in the source archive. The core app runs without Laya. Configuration is in backend/laya_config.json; the existing installer pins source commit `9e1e2419d855ad3e1a2af4d4bd1ef6be5418842c` and checkpoint revision `f2fe3c12cb6d04c59d8a190250bf3fb40fc828dc` of `thaitea/laya-vision`.

Full-sequence review attempts every discovered exposure and reports failed downloads explicitly. Long temporal batches retain earliest/latest context and count unique reviewed frames. Candidate tracks require compatible per-source-pixel wavelengths, at least four independent nights, a 30-day span, a five-sigma velocity, low residuals and leave-one-out stability. Coherent field-wide translations are rejected as possible registration/bulk-motion effects. Single-frame groups cannot establish change.

Laya supplies batch-level visual judgments, not validated source identifications or calibrated detection probabilities. Faint real motion can be filtered out. Zero candidates does not establish that no object moves. The latest actual loaded-cache validation reviewed 188/188 available WISE exposures from a discovered 256-frame sequence; the remaining 68 were outside that run. See docs/revision-laya-loaded.json.

Laya Vision source is Apache-2.0; the selected checkpoint declares **CC-BY-NC-SA-4.0**, a separate noncommercial license. It is derived from HuggingFaceTB/SmolVLM-256M-Instruct. Model weights are not relicensed or bundled with this application's Apache-2.0 source. See third_party/laya-vision/ and the checkpoint model card.

## Validation

```powershell
python -m pytest tests -q
node --experimental-default-type=module scripts/check_frontend.mjs
node --experimental-default-type=module --experimental-loader ./scripts/web-loader.mjs tests/frontend_startup.mjs
node --experimental-loader ./scripts/web-loader.mjs tests/scene_contracts.mjs
node --experimental-loader ./scripts/web-loader.mjs tests/scene_render_loop.mjs
node --experimental-loader ./scripts/web-loader.mjs tests/camera_paths.mjs
node --experimental-loader ./scripts/web-loader.mjs tests/journey_roundtrip.mjs
node --experimental-loader ./scripts/web-loader.mjs tests/scene_assets.mjs
```

The Node scene/geometry checks use bundled Three.js and require no npm installation. Optional UI scripts under qa/ use `npm install` from qa/ and require a working browser/localhost connection.

In a socket-restricted executor:

```powershell
python scripts/check_offline.py
python scripts/validate_cached_release.py
python scripts/review_cached_sequence.py
```

The latter two require genuine cached observations; model review also needs the installed optional model. Current evidence: 65 socket-independent Python tests passed, scene/geometry behavior checks passed, and all five presets rendered real cached PNGs without altering their source arrays. A fresh upload check on 2026-11-10 passed the same 65 socket-independent Python tests and Node scene checks. Browser, HTTP/ASGI, fresh network and localhost handoff checks remain unverified in this executor.

## GitHub and source packaging

After normal connectivity and GitHub CLI authentication are available:

```powershell
.\scripts\publish-github.ps1
```

The default is the authenticated account's planet-x repository. Use `-Repository owner/name` for an explicit destination. Existing repository history is preserved: a new branch is pushed without a force push or automatic merge. A new repository is private. The connected GitHub integration can publish to [hs-isadev/planet-x](https://github.com/hs-isadev/planet-x) despite the local Git/CLI restrictions. Source publication does not deploy the Python application. The script initializes/commits the source when run with normal repository write access.

```powershell
python package_source.py
```

This writes release/planet-x-observatory.zip, including current source and acceptance evidence while excluding runtime caches, model weights, browser screenshots and the unused historical frontend build.

## Sources and licenses

- IRSA SPHEREx endpoints, releases and adapters: backend/config.json. Native FITS and source URLs are retained; discovery caches are not a claim of the latest release.
- [IRSA AllWISE motion interpretation](https://irsa.ipac.caltech.edu/data/WISE/docs/release/AllWISE/expsup/sec2_6.html) and [column definitions](https://irsa.ipac.caltech.edu/data/WISE/docs/release/AllWISE/expsup/sec2_1a.html).
- [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/); bundled host/planet records include source metadata.
- [JPL satellite mean elements](https://ssd.jpl.nasa.gov/sats/elem/sep.html) and [mean radii](https://ssd.jpl.nasa.gov/sats/phys_par/).
- Gaia DR3, SIMBAD and NASA imagery/model credits: NOTICE and web/assets/sources.json.
- [Mapzen terrain formats and contributor attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md).

Original application code is Apache-2.0 (LICENSE). Vendored Three.js retains MIT licensing. Aladin retains its included LGPL/CDS terms. NASA imagery/models and external catalog data retain their own credits and applicable terms; they are not claimed as original application imagery. No AI-generated astronomical image or simulated source motion is used as an observed SPHEREx frame.
