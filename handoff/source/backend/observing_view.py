"""Exposure geometry from native FITS metadata, with no trajectory simulation."""
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from .archive import CACHE, output_grid


def exposure_segment(header):
    """Recorded exposure endpoints in the FITS geocentric frame."""
    if header.get("XYZ_SC_SYSTEM") != "GEOCENTER":
        return None
    try:
        xyz = np.array([[header[f"{axis}_SC_{end}"] for axis in "XYZ"] for end in ("START","END")],float)
        dates = [str(header[key]) for key in ("DATE-BEG","DATE-END")]
    except (KeyError, TypeError, ValueError):
        return None
    r = np.linalg.norm(xyz,axis=1)
    if not np.isfinite(xyz).all() or np.any(r<6378.137) or np.any(r>100000):
        return None
    # Orient this local diagram so the midpoint of the recorded segment is at top.
    center = xyz[0]/r[0] + xyz[1]/r[1]
    if np.linalg.norm(center)<1e-6:
        return None
    center /= np.linalg.norm(center)
    tangent = xyz[1]-np.dot(xyz[1],center)*center
    if np.linalg.norm(tangent)<1e-6:
        return None
    tangent /= np.linalg.norm(tangent)
    return dict(frame="GEOCENTER", xyz_km=xyz.tolist(), dates=dates,
                projection_earth_radii=(np.column_stack((xyz@tangent,-xyz@center))/6378.137).tolist(),
                height_above_reference_radius_km=(r-6378.137).tolist())


def exposure_geometry(job, frame):
    result = dict(id=frame['id'], date=frame['date'], detector=frame.get('detector'),
        exposure_url=frame.get('url') or frame.get('cutout_url'),
        center_icrs_deg=[job['ra'], job['dec']], patch_arcmin=job['fov'],
        detector_pixels=2040, patch_vertices=None, spacecraft_segment=None,
        geometry_status='Native FITS unavailable. Only the nominal instrument field is shown.',
        orbit_status='Illustrative polar terminator orbit. Spacecraft position and attitude are unavailable.')
    path = CACHE/(frame['cache_id']+'.fits')
    if not path.is_file():
        return result
    try:
        with fits.open(path, memmap=False, lazy_load_hdus=True) as hdus:
            header = hdus['IMAGE'].header
            segment = exposure_segment(header)
            if segment:
                result.update(spacecraft_segment=segment, orbit_status="Start and end positions come from this exposure’s FITS header. The line connects those positions. The dashed orbit guide is illustrative.")
            offsets = np.array([header['CRPIX1A'], header['CRPIX2A']])
            source = WCS(header).celestial
            grid, n, _ = output_grid(job['ra'], job['dec'], job['fov'])
            lon, lat = grid.pixel_to_world_values([-.5,n-.5,n-.5,-.5], [-.5,-.5,n-.5,n-.5])
            x, y = source.world_to_pixel_values(lon, lat)
            vertices = np.column_stack((x, y)) + 1 - offsets
            if not np.isfinite(vertices).all():
                raise ValueError('nonfinite projected vertices')
            result.update(patch_vertices=vertices.tolist(),
                pointing_reference_icrs_deg=source.wcs.crval.tolist(),
                geometry_status='Patch corners projected onto the original detector using the observed FITS WCS and cutout offsets. The detector outline is geometry only.')
    except (OSError, KeyError, ValueError, TypeError):
        result['geometry_status'] = 'The cached FITS does not provide usable original-detector offsets or WCS.'
    return result
