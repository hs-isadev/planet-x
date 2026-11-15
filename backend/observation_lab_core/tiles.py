"""Fixed sky tiles for following a target that moves across the sky.

The sky around a target is cut into square tiles (10′ by default) on a tangent plane. A target sitting well
inside one tile needs only that tile. When it comes within `margin` of an edge, the neighbouring tile is added;
near a corner that makes four. As the target keeps moving, the box of tiles grows (1 → 2 → 4 → 6 …) until it
reaches `max_grid` tiles on a side, and then a new scene starts around the target's current position.

Used by scripts/fetch_track.py (which downloads one cutout per tile per exposure) and motion_study.py (which
joins the tiles of each exposure into one fixed-sky mosaic).
"""
import math


def to_plane(ra, dec, ra0, dec0):
    """Gnomonic projection: (xi, eta) in arcmin, xi towards east, eta towards north."""
    a, d, a0, d0 = map(math.radians, (ra, dec, ra0, dec0))
    c = math.sin(d0) * math.sin(d) + math.cos(d0) * math.cos(d) * math.cos(a - a0)
    xi = math.cos(d) * math.sin(a - a0) / c
    eta = (math.cos(d0) * math.sin(d) - math.sin(d0) * math.cos(d) * math.cos(a - a0)) / c
    return math.degrees(xi) * 60, math.degrees(eta) * 60


def from_plane(xi, eta, ra0, dec0):
    x, y = math.radians(xi / 60), math.radians(eta / 60)
    a0, d0 = math.radians(ra0), math.radians(dec0)
    rho = math.hypot(x, y)
    if rho == 0:
        return ra0 % 360, dec0
    c = math.atan(rho)
    dec = math.asin(math.cos(c) * math.sin(d0) + y * math.sin(c) * math.cos(d0) / rho)
    ra = a0 + math.atan2(x * math.sin(c), rho * math.cos(d0) * math.cos(c) - y * math.sin(d0) * math.sin(c))
    return math.degrees(ra) % 360, math.degrees(dec)


def separation_arcmin(ra1, dec1, ra2, dec2):
    a1, d1, a2, d2 = map(math.radians, (ra1, dec1, ra2, dec2))
    s = math.sin((d2 - d1) / 2) ** 2 + math.cos(d1) * math.cos(d2) * math.sin((a2 - a1) / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(s)))) * 60


def lattice_centre(ra, dec, size_arcmin):
    """Snap a position to a fixed all-sky lattice (rows of constant Dec), so re-runs pick the same anchors."""
    t = size_arcmin / 60
    row = math.floor(dec / t + .5)
    dc = max(-90 + t / 2, min(90 - t / 2, row * t))
    n = max(1, int(360 * math.cos(math.radians(dc)) / t))
    step = 360 / n
    return round((math.floor((ra % 360) / step + .5) % n) * step, 6), round(dc, 6)


def _r(v):
    return math.floor(v + .5)


class Tiling:
    def __init__(self, ra0, dec0, size_arcmin=10.0, margin_arcmin=1.5):
        self.ra0, self.dec0 = ra0, dec0
        self.size, self.margin = float(size_arcmin), float(margin_arcmin)

    def ij(self, ra, dec):
        xi, eta = to_plane(ra, dec, self.ra0, self.dec0)
        return _r(xi / self.size), _r(eta / self.size)

    def near(self, ra, dec):
        """The tile holding the point, plus any neighbour whose edge is within `margin` (up to 4 tiles)."""
        xi, eta = to_plane(ra, dec, self.ra0, self.dec0)
        m, t = self.margin, self.size
        return {(_r((xi + dx) / t), _r((eta + dy) / t)) for dx in (-m, 0, m) for dy in (-m, 0, m)}

    def centre(self, i, j):
        return from_plane(i * self.size, j * self.size, self.ra0, self.dec0)

    def corners(self, i, j):
        return [from_plane((i + sx) * self.size, (j + sy) * self.size, self.ra0, self.dec0)
                for sx, sy in ((-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5))]


def tile_key(i, j):
    return f'{i}_{j}'


def box_dims(box):
    return box[1] - box[0] + 1, box[3] - box[2] + 1


def box_tiles(box):
    return [(i, j) for j in range(box[2], box[3] + 1) for i in range(box[0], box[1] + 1)]


def grow(box, tiles):
    i = [t[0] for t in tiles]
    j = [t[1] for t in tiles]
    if box is None:
        return [min(i), max(i), min(j), max(j)]
    return [min(box[0], *i), max(box[1], *i), min(box[2], *j), max(box[3], *j)]


def build_scenes(points, size_arcmin=10.0, margin_arcmin=1.5, max_grid=3, gap_days=None, anchor=None):
    """Split a time-ordered track into scenes, each one fixed box of tiles that the target stays inside.

    points: [{'mjd', 'ra', 'dec'}] sorted by time. anchor: fixed (ra, dec) tiling centre (a star's field), or
    None to snap each new scene to the all-sky lattice (moving bodies). A new scene starts after a gap longer
    than gap_days, or when the box would grow beyond max_grid tiles on a side.
    Returns [{'anchor': (ra, dec), 'box': [imin, imax, jmin, jmax], 'members': [point index, …]}].
    """
    scenes, cur, last = [], None, None

    def start(p):
        a = anchor or lattice_centre(p['ra'], p['dec'], size_arcmin)
        return dict(anchor=a, tiling=Tiling(a[0], a[1], size_arcmin, margin_arcmin), box=None, members=[])

    for idx, p in enumerate(points):
        if cur is None or (gap_days is not None and p['mjd'] - last > gap_days):
            cur = start(p)
            scenes.append(cur)
        near = cur['tiling'].near(p['ra'], p['dec'])
        box = grow(cur['box'], near)
        if cur['members'] and max(box_dims(box)) > max_grid:
            cur = start(p)
            scenes.append(cur)
            near = cur['tiling'].near(p['ra'], p['dec'])
            box = grow(None, near)
        cur['box'] = box
        cur['members'].append(idx)
        last = p['mjd']
    for s in scenes:
        s.pop('tiling')
    return scenes
