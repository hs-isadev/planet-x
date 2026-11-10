"""Documented IRSA TAP join + IBE cutouts; no invented image service."""
import hashlib
import json
import re
import threading
import uuid
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
import numpy as np
import pyvo
import requests
from filelock import FileLock, Timeout
import astropy.units as u
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "backend/config.json").read_text())
CACHE = ROOT / CONFIG["cache_directory"]
CACHE.mkdir(exist_ok=True)
_lock = threading.Lock()
_last_request = 0.0


def throttle():
    global _last_request
    with _lock:
        wait = CONFIG["min_request_interval_seconds"] - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def atomic_json(file, value):
    temporary = file.with_name(file.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    temporary.replace(file)


def key_for(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def discovery_query(ra, dec):
    # Schema and geometric predicate are taken from IRSA's cutouts tutorial.
    releases = " OR ".join("a.uri LIKE '%/" + r + "/%'" for r in CONFIG["releases"])
    return f"""SELECT a.uri, p.time_bounds_lower, p.energy_bandpassname
    FROM {CONFIG['artifact_table']} a
    JOIN {CONFIG['plane_table']} p ON a.planeid = p.planeid
    WHERE 1 = CONTAINS(POINT('ICRS', {float(ra)}, {float(dec)}), p.poly)
    AND ({releases}) ORDER BY p.time_bounds_lower"""


def verify_service_schema(session):
    cache=CACHE/'verified-spherex-schema.json'
    if cache.exists() and time.time()-cache.stat().st_mtime<604800:
        schema=json.loads(cache.read_text())
    else:
        throttle()
        service=pyvo.dal.TAPService(CONFIG['tap_endpoint'],session=session)
        tables=','.join("'"+CONFIG[k]+"'" for k in ('artifact_table','plane_table'))
        result=service.search('SELECT table_name,column_name,datatype FROM TAP_SCHEMA.columns WHERE table_name IN ('+tables+')',maxrec=2000).to_table()
        schema=[{k:str(r[k]) for k in result.colnames} for r in result]
        atomic_json(cache,schema)
    for table,required in [(CONFIG['artifact_table'],{'uri','planeid'}),(CONFIG['plane_table'],{'planeid','poly','time_bounds_lower','energy_bandpassname'})]:
        got={r['column_name'] for r in schema if r['table_name']==table}
        if not required<=got:raise ValueError('Live archive schema is incompatible with configured tables. No columns are guessed.')


def discover(ra, dec):
    query = discovery_query(ra, dec)
    cache = CACHE / ("query-" + key_for(query) + ".json")
    if cache.exists() and time.time() - cache.stat().st_mtime < CONFIG["query_ttl_seconds"]:
        return json.loads(cache.read_text())
    session = requests.Session()
    # pyvo uses this requests session for TAP. Bound every network operation.
    original = session.request
    def bounded(*args, **kwargs):
        kwargs.setdefault("timeout", CONFIG["timeout_seconds"])
        return original(*args, **kwargs)
    session.request = bounded
    verify_service_schema(session)
    throttle()
    table = pyvo.dal.TAPService(CONFIG["tap_endpoint"], session=session).search(
        query, maxrec=CONFIG["tap_max_records"]).to_table()
    if len(table) >= CONFIG["tap_max_records"]:
        raise RuntimeError("Archive result limit reached. No incomplete sequence will be presented; raise tap_max_records in config.")
    rows = []
    for row in table:
        uri = str(row["uri"])
        if not uri.endswith(".fits"):
            continue
        url = urljoin(CONFIG["origin"], uri)
        if urlparse(url).hostname != "irsa.ipac.caltech.edu" or not urlparse(url).path.startswith("/ibe/data/spherex/"):
            continue
        mjd = float(row["time_bounds_lower"])
        if not np.isfinite(mjd):
            continue
        detector_match = re.search(r"D([1-6])", str(row["energy_bandpassname"]))
        detector = int(detector_match.group(1)) if detector_match else None
        release = next((r for r in CONFIG["releases"] if f"/{r}/" in url), "unknown")
        obs = re.search(r"level2_(.*?)_spx", url)
        rows.append(dict(id=key_for(url), url=url, mjd=mjd,
                         date=Time(mjd, format="mjd").isot + "Z",
                         band=str(row["energy_bandpassname"]), detector=detector,
                         release=release, observation=obs.group(1) if obs else url))
    # Prefer newest release for each actual exposure; never duplicate epochs with QR2/QR3 reprocessing.
    unique = {}
    for row in rows:
        obs = row["observation"]
        old = unique.get(obs)
        if old is None or CONFIG["releases"].index(row["release"]) < CONFIG["releases"].index(old["release"]):
            unique[obs] = row
    rows = sorted(unique.values(), key=lambda r: (r["mjd"], r["band"], r["id"]))
    atomic_json(cache, rows)
    return rows


def output_grid(ra, dec, fov):
    n = max(16, int(np.ceil(fov * 60 / CONFIG["pixel_scale_arcsec"])))
    scale = fov * 60 / n
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.cdelt = [-scale / 3600, scale / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs, n, scale


def align_cutout(hdus, ra, dec, fov):
    image = hdus["IMAGE"]
    data = image.data.astype(np.float64)
    flags = hdus["FLAGS"].data.astype(np.uint32)
    good = np.isfinite(data) & np.isin(flags, CONFIG["accepted_pixel_flags"])
    if "VARIANCE" in hdus:
        variance = hdus["VARIANCE"].data
        good &= np.isfinite(variance) & (variance > 0)
    target, n, scale = output_grid(ra, dec, fov)
    yy, xx = np.mgrid[:n, :n]
    lon, lat = target.pixel_to_world_values(xx, yy)
    source = WCS(image.header).celestial
    sx, sy = source.world_to_pixel_values(lon, lat)
    coords = np.array([sy, sx])
    valid = map_coordinates(good.astype(float), coords, order=1, mode="constant", cval=0, prefilter=False)
    values = map_coordinates(np.where(good, data, 0), coords, order=1, mode="constant", cval=0, prefilter=False)
    values[valid < 0.999] = np.nan  # reject any interpolation using flagged or missing pixels
    wavelength = None
    try:
        x, y = source.world_to_pixel_values(ra, dec)
        swcs = WCS(image.header, fobj=hdus, key="W")
        swcs.sip = None
        wave, _ = swcs.pixel_to_world(x, y)
        wavelength = float(wave.to(u.um).value)
        if not np.isfinite(wavelength):
            wavelength = None
    except (ValueError, KeyError, TypeError, AttributeError):
        pass
    return values.astype(np.float32), dict(
        wavelength_um=wavelength, unit=image.header.get("BUNIT", "MJy/sr"),
        processing_version=str(hdus[0].header.get("VERSION", "unknown")),
        valid_fraction=float(np.isfinite(values).mean()), scale_arcsec=scale,
        width=n, height=n, alignment="ICRS TAN; north up, east left; bilinear display resampling",
        flags_policy="Conservative display mask: FLAGS 0 or 2097152 only; finite positive variance.",
        source_flag_values=[int(v) for v in np.unique(flags)],
        provenance="observed", transform="computed WCS registration; no source motion added")


def _fetch_frame(row, ra, dec, fov):
    identity = key_for(f"{row['url']}|{ra}|{dec}|{fov}|native-analysis-v2")
    array_file = CACHE / (identity + ".npy")
    meta_file = CACHE / (identity + ".json")
    if array_file.exists() and meta_file.exists() and (CACHE / (identity + ".npz")).exists() and (CACHE / (identity + ".fits")).exists():
        return identity, json.loads(meta_file.read_text())
    fits_file = CACHE / (identity + ".fits")
    url = row["url"] + "?" + urlencode({"center": f"{ra},{dec}d", "size": f"{fov / 60 * 1.5:.8f}"})
    if not fits_file.exists():
        for attempt in range(3):
            try:
                throttle()
                response = requests.get(url, timeout=CONFIG["timeout_seconds"])
                response.raise_for_status()
                if len(response.content) > 25_000_000:
                    raise RuntimeError("Cutout unexpectedly large; download refused.")
                temp = fits_file.with_suffix(".part")
                temp.write_bytes(response.content)
                with fits.open(temp) as hdus:
                    hdus.verify("exception")
                temp.replace(fits_file)
                break
            except (requests.RequestException, OSError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * 2 ** attempt)
    with fits.open(fits_file, memmap=False) as hdus:
        values, metadata = align_cutout(hdus, ra, dec, fov)
        from .analysis import aligned_products
        np.savez_compressed(CACHE / (identity + ".npz"), **aligned_products(hdus, ra, dec, fov))
    if not np.isfinite(values).any():
        raise ValueError("This cutout contains no usable pixels under the conservative quality mask.")
    np.save(array_file, values, allow_pickle=False)
    metadata["cutout_url"] = url
    atomic_json(meta_file, metadata)
    return identity, metadata


_cache_writes=0

def fetch_frame(row,ra,dec,fov):
    ra,dec,fov=float(ra),float(dec),float(fov)
    global _cache_writes
    identity=key_for(f"{row['url']}|{ra}|{dec}|{fov}|native-analysis-v2")
    with FileLock(str(CACHE/(identity+'.lock')),timeout=180):
        result=_fetch_frame(row,ra,dec,fov)
        now=time.time()
        for ext in ('.fits','.npy','.npz','.json'):
            p=CACHE/(identity+ext)
            if p.exists():
                try:__import__('os').utime(p,(now,now))
                except OSError:pass
    _cache_writes+=1
    if _cache_writes%24==0:prune_cache(protected={identity})
    return result


def ensure_frame_files(frame,job=None,native=False,analysis=False):
    identity=frame['cache_id']
    extensions=['.npy']+(['.npz'] if analysis else [])+(['.fits'] if native else [])
    if all((CACHE/(identity+ext)).exists() for ext in extensions):return
    source=job or frame
    if frame.get('source_key'):
        from .cloud import cloud_cutout
        _,meta=cloud_cutout(frame['source_key'],source['fov'],center=(source['ra'],source['dec']))
        index=frame.get('index');frame.update(meta)
        if index is not None:frame['index']=index
    else:
        identity,meta=fetch_frame(frame,source['ra'],source['dec'],source['fov'])
        frame.update(meta,cache_id=identity)


def prune_cache(protected=None):
    """Evict complete exposure groups by LRU, including while large jobs prefetch.

    Manifests retain metadata; evicted observations are fetched again on demand.
    A cross-process lock prevents concurrent pruners. Locked/incomplete files
    are left alone, so the budget can briefly be exceeded by active downloads.
    """
    protected=protected or set()
    try:
        with FileLock(str(CACHE/'cache-prune.lock'),timeout=0):
            groups={};total=0
            for p in CACHE.iterdir():
                if not p.is_file() or p.suffix in ('.lock','.part','.tmp'):continue
                try:stat=p.stat()
                except OSError:continue
                total+=stat.st_size
                key=p.stem if re.fullmatch(r'[a-f0-9]{24}',p.stem) else p.name
                group=groups.setdefault(key,dict(files=[],size=0,mtime=0))
                group['files'].append(p);group['size']+=stat.st_size;group['mtime']=max(group['mtime'],stat.st_mtime)
            cutoff=time.time()-CONFIG['cache_max_age_days']*86400
            # Keep small discovery/catalog metadata ahead of much larger exposure groups.
            # The global byte budget still applies if metadata itself grows large.
            for key,group in sorted(groups.items(),key=lambda pair:(not bool(re.fullmatch(r'[a-f0-9]{24}',pair[0])),pair[1]['mtime'])):
                if key in protected:continue
                if total<=CONFIG['cache_max_bytes'] and group['mtime']>=cutoff:continue
                try:
                    with FileLock(str(CACHE/(key+'.lock')),timeout=0):
                        for p in group['files']:
                            try:
                                size=p.stat().st_size;p.unlink(missing_ok=True);total-=size
                            except OSError:pass
                except Timeout:continue
    except Timeout:return
