# Planet X handoff

The root of the GitHub handoff branch is the runnable app. The local handoff/source folder is the standalone source snapshot for transfer. Use Python 3.12, pip install -r requirements.txt, then python start.py --port 8037. Open http://127.0.0.1:8037/. Existing .env settings are local. See docs/RENDER_DEPLOYMENT.md for Render settings.

## Implemented and checked

- Primary SPHEREx tab embeds the teammate’s actual Observation Lab viewer, renderer, tracker and spectrum engine. Planet X still owns Satellite View and 3D Context. The original analysis workspace remains available through Planet X analysis tools.
- Both archived Vesta frames were played in the integrated Lab. The tracker measured both positions and agreed with JPL Horizons to a maximum offset of 2.21 arcseconds in the preceding run.
- All 5,000 additional Gaia DR3 stars are searchable, visible and selectable across Satellite and 3D. The verified TIC 160113658 example opens a star and a confirmed planet orbit. Its orbital radius is estimated from published mass and period.
- The spectrum sidebar explains wavelength, measured flux and error bars. Higher flux means more measured light at that wavelength; a dip can suggest absorption.
- The bar in the submitted 3D screenshot was an opaque CSS background on the stellar status strip. It is transparent in this snapshot; the object-navigation dock still has its normal background.
- The original Planet X analysis workspace uses IRSA’s DR1 spectral-channel map and links the selected position to its matching FITS cube. This is distinct from providing an interactive all-sky wavelength viewer.
- The merged Lab discovery already supported DR1. This snapshot explicitly prefers DR1 for a duplicate physical exposure, keeps QR3 observations, and enables DR1 photometry through release-specific spectral WCS, pixel area, and ePSF calibration products. All three DR1 product families were checked against IRSA’s public bucket.
- Groq has developer model fallbacks. Local Laya completed a real WISE 0855 review; model suggestions remain separate from measured motion. The standard Render image does not include Laya’s model runtime.

## Image provenance and saved coverage

The teammate’s images come from NASA/IPAC IRSA Level 2 FITS cutouts. Vesta came from IRSA’s moving-object search; the fixed fields have SIA queries and exposure URLs in backend/observation_lab_core/data/collection.json. The startup library contains 22 FITS exposures across six fields. An index of thousands of observations does not mean the image pixels are saved. On the same Vesta raw FITS, pixel values agreed where both apps displayed them. The teammate’s stretch and mask explain the visual difference.

