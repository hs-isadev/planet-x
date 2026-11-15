# Parallax — Planet X / SPHEREx Observatory

A science-first viewer for real SPHEREx infrared observations. Enter RA/Dec or select Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae or R Draconis. The first screen is the science viewer; optional catalog/ephemeris 3D context is loaded separately. This is an independent project, not an official NASA service.

See [the 14-item follow-up](docs/ISSUE_STATUS.md) and [the November 11 pipeline validation](docs/PIPELINE_VALIDATION.md) for current live browser, archive and model evidence. [Earlier acceptance evidence](docs/CURRENT_STATUS.md) covers the previous release.

## SPHEREx view

Open **Satellite View** directly from the top navigation to explore the sky. **SPHEREx View** and **3D Context** share the pinned sky direction. Switching views preserves the observation session. The amber reticle marks the search coordinates. Drag or use the arrow keys to look around, and use **Center target** to reacquire the marked field. Right-click a direction to pin its ICRS coordinates and start an IRSA coordinate search. Click a marked catalog star and choose **Open in 3D Context** to focus its catalog position. The 3D reticle marks an angular direction. An arbitrary sky pin has no assigned distance. **Loaded cutout** shows the native detector pixels, while **Detector footprint** locates the cutout within the full detector when the FITS alternate pixel WCS is available.

The catalog sky is the celestial [NASA/Goddard Scientific Visualization Studio Deep Star Maps](https://svs.gsfc.nasa.gov/3895/) 4K image, based on the Bright Star, Tycho-2 and UCAC3 catalogs. It provides visible-light context. The archived infrared detector cutout is separate. The spacecraft position comes from the selected FITS header when present. Free look is an illustrative rotation at that viewpoint. The reticle marks the selected coordinates. The sky map is fetched on first use and cached locally. A coordinate grid remains available if the texture or WebGL fails.

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

- Search by RA/Dec in degrees or sexagesimal. Choose a 2–20 arcmin field or one of five named presets. A link with `?ra=&dec=&fov=&exposure=` identifies a specific archive product and prioritizes its download. Older `frame=` links still open by index.
- Discovery searches IRSA’s current DR1 and QR3 spectral-image releases. Duplicate processing versions collapse to one exposure per detector. The manual archive browser lets you browse either current release. If the IRSA cutout endpoint is busy, a bounded cloud-mirror range read retrieves native IMAGE, FLAGS, VARIANCE and ZODI pixels and samples the exposure’s WCS-WAVE. See the [IRSA archive guide](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/).
- Genuine IRSA native FITS, WCS registration, original quality masks, chronological playback, speed, loop, scrubber, date and metadata. Missing pixels remain unknown.
- Default playback includes every available detector in chronological order, with pending/unavailable exposures marked in the full timeline. The viewer buffers up to 24 upcoming cutouts as soon as a frame opens, with four background image requests at a time. The backend prepares up to four archive cutouts in parallel after the first frame, with archive request pacing applied across jobs. Open **Date and wavelength coverage** to jump to a real exposure or find earlier and later dates in the selected detector within 0.025 µm at field center. Select a matching date and choose **Blink selected pair** to alternate the two registered exposures on the main canvas. **Measure pair at field center** requests a calibrated displacement check with mask, band overlap, PSF, and nearby field-star checks. It reports when a measurement is unsupported. Download a CSV of the complete field manifest or the selected wavelength matches, with dates, exposure IDs, status and original FITS URLs. Detector and wavelength filters are optional. Narrow 0.025 micrometer groups, fixed per-detector contrast, six-array stacking and compatible-frame add/subtract reduce cross-band confusion. They do not remove PSF/calibration systematics.
- Click a source with Aperture spectrum selected to inspect flux, uncertainty, date groups and optional cited feature windows. Choose an aperture radius and export measurements with flux uncertainty, calibration, and the original exposure URLs. Use the evidence card to save coordinates, original observations and a volunteer classification. The fixed aperture uses cached native FITS and approximate WCS-WAVE wavelengths.
- Barnard comparison samples the wavelength map at the predicted source position, selects a compatible time baseline, shows a real difference and predicted markers, and attempts a free native PSF-wing fit. Masked or poor fits remain unavailable; the catalog's roughly 10.4 arcsec/year is not called a measured shift.
- Light curves search compatible loaded groups. If native apertures fail, a fixed common footprint of valid registered pixels can supply a brightness index. Masked cores are excluded in every epoch, not reconstructed. Statistical errors omit resampling correlations, PSF and calibration systematics. A plotted change alone does not establish intrinsic variability.
- Gaia overlays apply available angular proper motion. WISE date-dependent markers use Gaia astrometry only for unique associations at the documented MJD 55400 AllWISE motion-fit position, within 1 arcsec. Unmatched/blend-swapped sources retain stationary WISE positions. AllWISE apparent motions are **not** extrapolated: IRSA advises that they cannot predict positions at other epochs. Annual parallax is omitted from these overlays.
- SPHEREx observing perspective uses the native FITS footprint and recorded spacecraft position endpoints when available. The dashed orbit is illustrative. Tour captions, optional Aladin Lite coordinate selection, exports and provenance labels remain. Aladin survey tiles require CDS network access.

Observed, catalog and computed layers are distinct. A loaded field or red residual is not a source identification, a motion detection, or evidence for Planet X. Red highlighting and noise suppression are computed quicklooks; they never alter preserved observed arrays. Wavelength changes, confusion and artifacts can mimic change.

Keyboard: Space play/pause, arrows step, brackets change speed, slash opens search, Escape closes. Mobile Search expands coordinates and auxiliary tools.

## Optional 3D context

**Photos are flat. Stellar depth comes from catalog distances; Solar System positions are computed.** Images returns directly to the SPHEREx viewer. This context does not replace the observations.

Bottom navigation and direct body clicks share a smooth focus action. Approach changes distance deliberately. Camera zooms interpolate distance geometrically with quintic easing. Journeys accelerate and decelerate while keeping the camera facing forward. Return journeys turn toward the source before moving; they no longer turn back toward Earth during departure. Explicit transitions distinguish parsec, AU and normalized stellar-illustration scales; they are not physical spacecraft trajectories.

A persistent Solar System button, a stellar-strip home entry and a target-menu entry return to the Sun and planets. Earth journeys offer Stay on Earth as well as Return to object. The Sun returns to its planetary scene rather than a star-only closeup. Known catalog exoplanets appear in automatically framed system overviews, with named planet buttons and a separate stellar-surface closeup. Planets remain visible through deliberate display enlargement; systems with no installed orbit are labelled explicitly. NASA Exoplanet Archive periods/orbital scales are used; circular planes, phases, radii/display enlargement and appearances remain illustrative. No orbit is invented for an unmatched system.

Ten selected major moons are present: Moon, Phobos, Deimos, Io, Europa, Ganymede, Callisto, Titan, Titania and Triton. JPL mean orbital scales/periods and radii are attributed in web/assets/moons.json. Display radii and separations are enlarged independently. Circular layouts/phases are illustrative, not satellite ephemerides or a complete moon census.

The catalog backdrop includes exoplanet host stars and 240 additional HYG 4.1 records with Hipparcos, Yale Bright Star Catalog or Gliese identifiers. Search names or filter sources in Satellite View. The HYG subset is attributed and licensed CC BY-SA 4.0 in the assets directory. It is an incomplete sample; point sizes are adapted for visibility, not measured brightness. Plasma, faster sunspots, a faint white coronal illustration, magnetic loops, dust and travel streaks are computed illustrations, not observed events or measured surface maps. Planet rotation is independently accelerated for visibility rather than tied to orbital playback. The Solar System loading cover waits for requested appearance maps and models to settle. The surrounding catalog backdrop is rendered in one batch and its displayed stars can be selected. Closeups with unknown temperature carry a persistent warning that appearance may be inaccurate. Unknown temperature does not supply an invented temperature or reliable distance.

## Laya analysis report and Groq guide

After Laya completes a crop comparison, open **Experimental AI review → Analysis report** in SPHEREx View. The report shows coverage, possible shifts, brightening or fading, artifacts or missing data, and uncertain comparisons. Download the JSON for exact exposure IDs, dates, detectors, and crop bounds. Counts are for overlapping comparisons. Use **Date and wavelength coverage → Measure pair at field center** for a calibrated displacement check, or **Target light curve** for same-band aperture photometry.

**Explain report with AI guide** opens a question and attaches the report when you choose **Send**. Groq receives the counts, coverage, and up to eight representative comparisons. FITS files and image pixels stay local. Set `GROQ_API_KEY` in the PowerShell environment before running `python start.py` to enable the optional guide. Its instructions are in [GROQ_SYSTEM_PROMPT.md](docs/GROQ_SYSTEM_PROMPT.md).

## Local Laya review

The optional image-capable Laya Vision fork runs locally: https://github.com/r33drichards/laya-vision . It is separate from the unrelated desktop notification app. No API key or paid inference service is used; review images are not sent to an external inference service.

Install after the main requirements:

```powershell
python scripts/setup_laya.py
python start.py
```

Git and an initial network connection are required. Runtime weights and the isolated virtual environment are not included in the source archive. The core app runs without Laya. Configuration is in backend/laya_config.json; the existing installer pins source commit `9e1e2419d855ad3e1a2af4d4bd1ef6be5418842c` and checkpoint revision `f2fe3c12cb6d04c59d8a190250bf3fb40fc828dc` of `thaitea/laya-vision`.

Sequence review consumes the same ready frames as playback and starts with available compatible crops. It saves exposure IDs, dates, assigned references and completed crops in local receipts. Cancel stops active inference and keeps completed crops. Review / resume continues the same field using the saved receipt. The browser reports preparation, model and inference stages, preliminary compatibility, unique reviewed exposures and last progress.

Laya produces visual suggestions. A counted exposure has every eligible crop reviewed. Masked or unmatched pixels and exposures without a suitable reference remain unassessed. See the validation report for measured false flags, missed injections and calibration limits.

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

In the image viewer, use +, −, Fit image, or scroll over the cutout. Drag to pan when zoomed. Wider sky field fetches a larger archive cutout at the same coordinates.

Sun sky keeps the camera at a fixed radius around the Sun. Drag to look outward, then right-click any sky position to search IRSA. Load images at center offers the same action for the central reticle.


### Saving SPHEREx data locally beyond the preset targets

Field search uses IRSA TAP. On a TAP timeout it can reuse the exact field's saved manifest or query IRSA SIA. If both live options fail, the viewer can use saved manifests and verified originals with WCS coverage at the requested coordinates. The UI flags fallback coverage as potentially incomplete. Searches prepare cutouts in chronological order and reuse saved originals when available.

The bulk prefetch uses IRSA's public S3 mirror and enumerates all released DR1 and QR3 Level 2 spectral image files, independently of the app's target list. It saves native FITS files and SHA-256 receipts outside the disposable playback cache. The SQLite inventory records progress and errors. Raising the budget does not increase transfer concurrency.

```powershell
python scripts/prefetch_archive.py --status
python scripts/prefetch_archive.py --budget-gib 70 --keep-free-gib 40
```

Resume with the same command. Add `--retry-failed` to retry failed files after connectivity returns. The budget is the maximum total size of saved originals, and the free-space reserve can stop the run first. The complete archive spans many terabytes. Inspect **Saved archive originals** in the SPHEREx view for the number of files indexed and the number actually saved. The `saved-spherex` folder is excluded from Git. Back it up or move it separately if you migrate the app.


### Cross-mission evidence

Open **Cross-mission evidence** beside the SPHEREx frames. The panel can show Gaia DR3 reference stars, pass the same ICRS coordinates and field size to WiseView for an older infrared blink, or query public NEOSSat footprints at CADC. It distinguishes a service timeout from a successful query with no overlapping products. Export a JSON receipt with the original SPHEREx exposure, Gaia settings, linked WISE field, and NEOSSat metadata if queried. Gaia's catalog reference epoch is J2016.0. Each survey has its own observing times, bands, and angular resolution. See the linked SPHEREx and CSA notebooks for reproducing independent checks.

For the public web service, see [Deploying on Render](docs/RENDER_DEPLOYMENT.md).


### Observation lab tools

Open **Track a moving source** in SPHEREx and choose **Load archived Vesta example** for two D3 IRSA observations from 4–5 August 2025. **Measure track** compares native centroids against JPL Horizons, using exposure midpoints when provided by FITS. The observer is identified in the result. A geocentric fallback lacks the spacecraft parallax. For an unnamed source, use **Mark motion** on one frame for a fixed search position or two frames for a straight between-epoch search guide. Fits can be rejected when a source is masked, blends with another, or falls outside the field. Speed is projected on the sky and measured between successful fits.

**Inspect native pixel** reads the original cutout brightness, uncertainty, wavelength, and flags. **Detector flag overlay** shows pixels excluded by the display mask. **Identify clicked source** checks SIMBAD and IMCCE SkyBoT in parallel at the exposure time. A positional match is a lead to verify.

**Forced ePSF** uses released wavelength, solid-angle and ePSF calibration products for fixed-position spectra. It evaluates up to 64 evenly spaced loaded exposures, retains negative measurements, and marks poor fits for review. The spectrum panel can separate releases and shift reference windows by a user-specified redshift. Click a spectrum or light-curve point to see its underlying exposure.

In **3D Context → Scale / orbit → Physical atlas**, browse catalog distances from Gaia DR3 or DESI DR1. Use the Gaia year slider to project cataloged 3D velocities, and click a point to inspect its parameters, radial uncertainty, or SPHEREx sky field. The atlas uses incomplete catalog samples. [Data sources and credits](web/assets/atlas-credits.txt).
