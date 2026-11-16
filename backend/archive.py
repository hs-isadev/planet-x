"""Documented IRSA TAP join + IBE cutouts; no invented image service."""
import hashlib
import json
import os
import re
import threading
import uuid
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse
import numpy as np
import pyvo
from .saved_archive import CUTOUTS, STORAGE_ROOT, saved_original, local_rows, restore_cutout, preserve_cutout
import requests
from filelock import FileLock, Timeout
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from scipy.ndimage import map_coordinates

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "backend/config.json").read_text())
CACHE = STORAGE_ROOT / CONFIG["cache_directory"]
CACHE.mkdir(parents=True, exist_ok=True)
LOW_MEMORY = os.environ.get('SPHEREX_LOW_MEMORY') == '1'
if LOW_MEMORY:
    CONFIG.update(concurrent_downloads=1, max_active_jobs=1)
_lock = threading.Lock()
_last_request = 0.0
_ibe_busy_until = 0.0


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
    try:
        for attempt in range(7):
            try:
                temporary.replace(file)
                break
            except PermissionError:
                if attempt == 6:
                    raise
                # Windows readers/scanners can briefly prevent atomic replacement.
                time.sleep(.025 * 2**attempt)
    finally:
        temporary.unlink(missing_ok=True)


def key_for(value):
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def same_calibration_release(first, second):
    # DR1 and QR3 are a uniformly processed set. Older QR2 products use a different calibration.
    return bool(first and second and (first == second or {first, second} == {"dr1", "qr3"}))


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


class DiscoveryRows(list):
    def __init__(self, rows, source, complete, detail=None):
        super().__init__(rows)
        self.source = source
        self.complete = complete
        self.detail = detail


def normalized_discovery(records):
    rows = []
    for raw_uri, raw_mjd, raw_band in records:
        uri = str(raw_uri)
        if not uri.endswith(".fits"):
            continue
        url = urljoin(CONFIG["origin"], uri)
        if urlparse(url).hostname != "irsa.ipac.caltech.edu" or not urlparse(url).path.startswith("/ibe/data/spherex/"):
            continue
        try:
            mjd = float(raw_mjd)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(mjd):
            continue
        detector_match = re.search(r"D([1-6])", str(raw_band))
        detector = int(detector_match.group(1)) if detector_match else None
        release = urlparse(url).path.removeprefix("/ibe/data/spherex/").split("/", 1)[0]
        if release not in CONFIG["releases"]:
            continue
        obs = re.search(r"level2_(.*?)_spx", url)
        rows.append(dict(id=key_for(url), url=url, mjd=mjd,
                         date=Time(mjd, format="mjd").isot + "Z",
                         band=str(raw_band), detector=detector,
                         release=release, observation=obs.group(1) if obs else url))
    return unique_observations(rows)


def unique_observations(rows):
    # Prefer the configured current release for duplicate versions of the same exposure and detector.
    unique = {}
    for row in rows:
        obs = row["observation"]
        old = unique.get(obs)
        if old is None or CONFIG["releases"].index(row["release"]) < CONFIG["releases"].index(old["release"]):
            unique[obs] = row
    rows = sorted(unique.values(), key=lambda r: (r["mjd"], r["band"], r["id"]))
    return rows



def discover_tap(query):
    with requests.Session() as session:
        original = session.request

        def bounded(*args, **kwargs):
            kwargs.setdefault("timeout", (6, CONFIG.get("tap_discovery_read_timeout", 18)))
            return original(*args, **kwargs)

        session.request = bounded
        verify_service_schema(session)
        throttle()
        table = pyvo.dal.TAPService(CONFIG["tap_endpoint"], session=session).search(
            query, maxrec=CONFIG["tap_max_records"]).to_table()
    if len(table) >= CONFIG["tap_max_records"]:
        raise RuntimeError("IRSA TAP reached the result limit.")
    return normalized_discovery((r["uri"], r["time_bounds_lower"], r["energy_bandpassname"]) for r in table)


def discover_sia(ra, dec):
    from io import BytesIO
    from astropy.io.votable import parse
    params = [("COLLECTION", collection) for collection in CONFIG["collections"]]
    params.extend([("POS", f"CIRCLE {float(ra)} {float(dec)} 0"), ("MAXREC", CONFIG["tap_max_records"])])
    throttle()
    response = requests.get(CONFIG["sia_endpoint"], params=params, timeout=(6, 20))
    response.raise_for_status()
    votable = parse(BytesIO(response.content))
    statuses = [str(info.value).upper() for res in votable.resources for info in res.infos
                if info.name == "QUERY_STATUS"]
    if not statuses or any(status != "OK" for status in statuses):
        raise ValueError("IRSA SIA returned an error, an incomplete result, or no query status.")
    table = votable.get_first_table().to_table(use_names_over_ids=True)
    if len(table) >= CONFIG["tap_max_records"]:
        raise RuntimeError("IRSA SIA reached the result limit.")
    return normalized_discovery((r["access_url"], r["t_min"], r["energy_bandpassname"]) for r in table)


def saved_manifest(name):
    paths = (CACHE / name, CUTOUTS / name) if CACHE == STORAGE_ROOT / CONFIG["cache_directory"] else (CACHE / name,)
    for path in paths:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(rows, list) and all(isinstance(row, dict) and "url" in row for row in rows):
                return rows, path.stat().st_mtime
        except (OSError, ValueError):
            continue
    return None, 0


def discover(ra, dec):
    query = discovery_query(ra, dec)
    name = "query-" + key_for(query) + ".json"
    saved, modified = saved_manifest(name)
    if saved is not None and time.time() - modified < CONFIG["query_ttl_seconds"]:
        return DiscoveryRows(saved, "Saved IRSA TAP manifest", True)
    try:
        rows = discover_tap(query)
        atomic_json(CACHE / name, rows)
        preserve_cutout(CACHE / name)
        return DiscoveryRows(rows, "IRSA TAP", True)
    except Exception as tap_error:
        if saved:
            return DiscoveryRows(saved, "Saved IRSA TAP manifest", False,
                "Live IRSA TAP failed. Showing a previously saved field; newer releases may be missing.")
        errors = [f"TAP: {type(tap_error).__name__}"]
    try:
        rows = discover_sia(ra, dec)
        if rows:
            directory = CUTOUTS if CACHE == STORAGE_ROOT / CONFIG["cache_directory"] and CUTOUTS.is_dir() else CACHE
            atomic_json(directory / ("sia-" + name), rows)
            return DiscoveryRows(rows, "IRSA SIA", False,
                "IRSA SIA fallback. The latest weekly ingestion may be missing.")
        errors.append("SIA: no exposures returned")
    except Exception as sia_error:
        errors.append(f"SIA: {type(sia_error).__name__}")
    saved_sia, _ = saved_manifest("sia-" + name)
    local = local_rows(ra, dec)
    rows = unique_observations([*(saved_sia or []), *local])
    if rows:
        return DiscoveryRows(rows, "Saved IRSA observations", False,
            "Live IRSA discovery is unavailable for this search. Showing the locally saved subset.")
    raise RuntimeError("Live IRSA discovery did not return coverage and no saved exposure covers this position. "
        + "; ".join(errors) + ".")


def output_grid(ra, dec, fov):
    n = max(16, int(np.ceil(fov * 60 / CONFIG["pixel_scale_arcsec"])))
    scale = fov * 60 / n
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    wcs.wcs.crval = [ra, dec]
    wcs.wcs.cdelt = [-scale / 3600, scale / 3600]
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs, n, scale


def blink_levels(*arrays):
    # Sample bounded, finite pixels so a fixed contrast can be set without retaining large stacks.
    samples = [a[np.isfinite(a)][::max(1,a.size//16000)] for a in arrays]
    finite = np.concatenate(samples)
    if not finite.size:
        raise ValueError('No usable observed pixels.')
    lo, hi = np.percentile(finite,[42,99.5])
    return float(lo), float(max(hi,lo+1e-8))


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
        from .analysis import wavelength_map
        wavelength = float(wavelength_map(hdus, np.array([x]), np.array([y]))[0])
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


def download_cutout(source_url, cutout_url, destination, ra, dec, fov, *, prefer_mirror=False):
    global _ibe_busy_until
    from .cloud import cutout_from_mirror, mirror_key

    key = mirror_key(source_url)
    temporary = destination.with_suffix(".part")
    transport = "IRSA cutout service"
    local = saved_original(key) if key else None
    try:
        with _lock:
            primary_available = time.monotonic() >= _ibe_busy_until
        if key is None or (not prefer_mirror and primary_available and local is None):
            throttle()
            try:
                deadline = time.monotonic() + 35
                with requests.get(cutout_url, timeout=(8, 18), stream=True) as response:
                    response.raise_for_status()
                    size = 0
                    with temporary.open("wb") as out:
                        for chunk in response.iter_content(256 * 1024):
                            if time.monotonic() >= deadline:
                                raise requests.Timeout("IRSA cutout transfer exceeded 35 seconds.")
                            size += len(chunk)
                            if size > 25_000_000:
                                raise ValueError("Cutout unexpectedly large; download refused.")
                            out.write(chunk)
            except requests.RequestException as error:
                response = error.response
                status = response.status_code if response is not None else None
                if key is None or (status is not None and status not in (404, 408, 429) and status < 500):
                    raise
                if status in (429, 502, 503, 504):
                    delay = response.headers.get("Retry-After", "5")
                    seconds = min(30, max(5, int(delay))) if delay.isdecimal() else 5
                    with _lock:
                        _ibe_busy_until = max(_ibe_busy_until, time.monotonic() + seconds)
                transport = "IRSA public cloud mirror"
        else:
            transport = "IRSA saved original" if local else "IRSA public cloud mirror"
        if transport != "IRSA cutout service":
            hdus, _, _ = cutout_from_mirror(key, fov, center=(ra, dec))
            with hdus:
                hdus.writeto(temporary, overwrite=True)
        with fits.open(temporary) as hdus:
            hdus.verify("exception")
        temporary.replace(destination)
        return transport
    finally:
        temporary.unlink(missing_ok=True)


def _fetch_frame(row, ra, dec, fov, native=False):
    identity = key_for(f"{row['url']}|{ra}|{dec}|{fov}|native-analysis-v2")
    array_file = CACHE / (identity + ".npy")
    meta_file = CACHE / (identity + ".json")
    if array_file.exists() and meta_file.exists() and (CACHE / (identity + ".npz")).exists() and (not native or (CACHE / (identity + ".fits")).exists()):
        return identity, json.loads(meta_file.read_text())
    fits_file = CACHE / (identity + ".fits")
    url = row["url"] + "?" + urlencode({"center": f"{ra},{dec}d", "size": f"{fov / 60 * 1.5:.8f}"})
    if not fits_file.exists():
        transport = download_cutout(row["url"], url, fits_file, ra, dec, fov)
    else:
        transport = None
    with fits.open(fits_file, memmap=False) as hdus:
        native_header = hdus[0].header
        values, metadata = align_cutout(hdus, ra, dec, fov)
        from .analysis import aligned_products
        np.savez_compressed(CACHE / (identity + ".npz"), **aligned_products(hdus, ra, dec, fov))
    if not np.isfinite(values).any():
        raise ValueError("This cutout contains no usable pixels under the conservative quality mask.")
    np.save(array_file, values, allow_pickle=False)
    metadata["cutout_url"] = url
    if transport:
        metadata["transport"] = transport
    elif "PXORIGIN" in native_header:
        metadata["transport"] = native_header["PXORIGIN"]
    atomic_json(meta_file, metadata)
    return identity, metadata


_cache_writes=0

def fetch_frame(row,ra,dec,fov,native=False):
    ra,dec,fov=float(ra),float(dec),float(fov)
    global _cache_writes
    identity=key_for(f"{row['url']}|{ra}|{dec}|{fov}|native-analysis-v2")
    with FileLock(str(CACHE/(identity+'.lock')),timeout=180):
        restore_cutout(CACHE, identity)
        result=_fetch_frame(row,ra,dec,fov,native=native)
        now=time.time()
        for ext in ('.fits','.npy','.npz','.json'):
            p=CACHE/(identity+ext)
            if p.exists():
                preserve_cutout(p)
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
        identity,meta=fetch_frame(frame,source['ra'],source['dec'],source['fov'],**({'native':True} if native else {}))
        frame.update(meta,cache_id=identity)


def prune_cache(protected=None):
    """Evict bulky native FITS first, retaining small chronological playback arrays.

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
            # A cutout FITS can be hundreds of times larger than its aligned
            # playback array. Native photometry can refetch it on demand.
            for key,group in sorted(groups.items(),key=lambda pair:pair[1]['mtime']):
                if key in protected or total<=CONFIG['cache_max_bytes']:continue
                native=[p for p in group['files'] if p.suffix=='.fits']
                if not native:continue
                try:
                    with FileLock(str(CACHE/(key+'.lock')),timeout=0):
                        for p in native:
                            try:
                                size=p.stat().st_size;p.unlink(missing_ok=True);total-=size
                                group['files'].remove(p);group['size']-=size
                            except OSError:pass
                except Timeout:continue
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
