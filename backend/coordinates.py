"""Bare RA numbers mean degrees; sexagesimal RA means hours. ICRS only."""
import math
import re
import astropy.units as u
from astropy.coordinates import Angle, SkyCoord


def parse_coordinates(ra: str, dec: str) -> SkyCoord:
    ra, dec = str(ra).strip(), str(dec).strip()
    try:
        if not ra or not dec:
            raise ValueError("Both coordinates are required.")
        numeric = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
        unit = u.deg if re.fullmatch(numeric, ra) or "deg" in ra.lower() or "d" in ra.lower() else u.hourangle
        r = Angle(ra, unit=unit).degree
        d = Angle(dec, unit=u.deg).degree
        if not math.isfinite(r) or not math.isfinite(d) or not 0 <= r < 360 or not -90 <= d <= 90:
            raise ValueError("RA must be 0 ≤ RA < 360°; Dec −90° to +90°.")
        return SkyCoord(r * u.deg, d * u.deg, frame="icrs")
    except (ValueError, TypeError, u.UnitsError) as exc:
        raise ValueError("Use degrees or sexagesimal, e.g. 08:55:10.831 and -07:14:42.53. " + str(exc)) from exc
