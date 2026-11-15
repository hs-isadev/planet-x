"""Released SPHEREx standard-channel geometry, independent of the measured spectrum."""
from functools import lru_cache

import astropy.units as u
from astropy_healpix import HEALPix
from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from requests import RequestException

from .calibrated_comparison import calibration_file, detector_offsets

KEY = 'dr1/spectral_channels/cal-sch-v2-2026-229/spectral_channels_spx_cal-sch-v2-2026-229.fits'
DR1_CUBE_ROOT = 'https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026'
TILES = HEALPix(nside=32,order='nested')

def mosaic_url(position):
    tile = int(TILES.lonlat_to_healpix(position.icrs.ra.to(u.deg),position.icrs.dec.to(u.deg)))
    return f'{DR1_CUBE_ROOT}/Norder5/Dir{tile//10000*10000}/Npix{tile}_cube.fits'


@lru_cache(maxsize=1)
def released_channels():
    path, url = calibration_file(KEY)
    with fits.open(path, memmap=False) as hdus:
        geometry = hdus['CHANNEL_MAP'].data.copy()
        channels = [dict(detector=int(r['DETECTOR']), subchannel=int(r['SUBCHAN']),
                         wavelength_um=round(float(r['WAVELENGTH']),5),
                         lower_um=round(float(r['WL_MIN']),5), upper_um=round(float(r['WL_MAX']),5),
                         resolving_power=float(r['R']))
                    for r in hdus['SPECTRAL_CHANNELS'].data if 1<=r['SUBCHAN']<=17]
    if geometry.shape!=(2040,2040) or len({(r['detector'],r['subchannel']) for r in channels})!=102:
        raise ValueError('Unexpected released spectral-channel calibration shape.')
    return geometry, channels, url


def channel_data():
    try:
        return released_channels()
    except (OSError, ValueError, KeyError, RequestException):
        return None, [], None


def sample_channel(header, position, geometry):
    """Classify only when the original detector coordinates are known."""
    if geometry is None:
        return None
    try:
        offset = detector_offsets(header)
        xy = np.asarray(WCS(header).celestial.world_to_pixel(position),dtype=float)
        if not np.isfinite(xy).all():
            return None
        if not np.all((xy>=-.5)&(xy<np.array([header['NAXIS1'],header['NAXIS2']])-.5)):
            return None
        x,y = np.floor(xy+offset+.5).astype(int)
        if not (0<=x<geometry.shape[1] and 0<=y<geometry.shape[0]):
            return None
        channel = int(geometry[y,x])
        return channel if 1<=channel<=17 else None
    except (ValueError, KeyError, TypeError):
        return None
