"""Verified, resumable IRSA downloads. No fabricated pixels or observation limits."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
import shutil
import threading
import time
from urllib.parse import urlencode, urlparse
import uuid

import requests
from requests.adapters import HTTPAdapter
from astropy.io.votable import parse_single_table
from .science import fits_metadata

DOWNLOAD_LOCKS = tuple(threading.Lock() for _ in range(64))
_HTTP_LOCAL = threading.local()
MIRROR_FOOTPRINTS = Path(__file__).resolve().parents[1] / 'data/mirror-footprints.json'


@lru_cache(maxsize=1)
def mirror_footprints():
    if not MIRROR_FOOTPRINTS.is_file():
        return []
    return json.loads(MIRROR_FOOTPRINTS.read_bytes())


def mirror_rows(ra, dec, start=None, end=None):
    """Find candidate detector footprints without any request to IPAC."""
    ra, dec = math.radians(ra), math.radians(dec)
    candidates = []
    for key, mjd, center_ra, center_dec, radius in mirror_footprints():
        if (start is not None and mjd < start) or (end is not None and mjd >= end):
            continue
        center_dec = math.radians(center_dec)
        cosine = (math.sin(dec) * math.sin(center_dec) +
                  math.cos(dec) * math.cos(center_dec) * math.cos(ra - math.radians(center_ra)))
        if cosine < math.cos(math.radians(radius)):
            continue
        identity = re.search(r'level2_(.+)D([1-6])_spx_', key)
        if identity:
            release = key.split('/', 1)[0]
            candidates.append(dict(id=identity[1], detector=int(identity[2]), mjd=mjd,
                                   source='https://irsa.ipac.caltech.edu/ibe/data/spherex/' + key,
                                   release=release.upper(), discovery_api='AWS mirror footprint index'))
    return candidates


def _http():
    """Return a per-thread HTTP session so concurrent IRSA downloads reuse TLS connections."""
    session = getattr(_HTTP_LOCAL, 'session', None)
    if session is None:
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=12, pool_maxsize=12)
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        _HTTP_LOCAL.session = session
    return session


RETRY_STATUS = {429, 500, 502, 503, 504}


def _irsa(method, url, attempts=3, **kwargs):
    """IRSA's gateway answers brief 5xx errors under load; retry those with a short backoff."""
    for attempt in range(attempts):
        try:
            session = _http()
            caller = getattr(session, method.lower(), None)
            response = caller(url, **kwargs) if callable(caller) else session.request(method, url, **kwargs)
            if response.status_code not in RETRY_STATUS or attempt == attempts - 1:
                response.raise_for_status()
                return response
        except (requests.ConnectionError, requests.Timeout):
            if attempt == attempts - 1:
                raise
        time.sleep(1.5 * (attempt + 1))


def irsa_outage(error):
    """A short reason for an unreachable IRSA search, or None for other failures."""
    while error is not None:
        response = getattr(error, 'response', None)
        if response is not None and response.status_code in RETRY_STATUS:
            return f'IRSA returned HTTP {response.status_code}'
        if isinstance(error, (requests.ConnectionError, requests.Timeout)):
            return 'IRSA did not respond'
        error = error.__cause__ or error.__context__
    return None


def write_json(path, data):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    # Windows readers / antivirus can briefly hold the destination open.
    for attempt in range(50):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(.1)


def reduction_priority(record):
    release = str(record.get('release','')).lower().split('_',1)[0]
    return ({'dr1':3,'qr3':2,'qr2':1}.get(release,0),
            record.get('processed_mjd') or 0, record.get('file_bytes') or 0)


def query_tap(config, ra, dec, start=None, end=None):
    """Find exposures in newly ingested archive metadata."""
    where = f"1 = CONTAINS(POINT('ICRS', {float(ra)}, {float(dec)}), p.poly)"
    if start is not None:
        where += f' AND p.time_bounds_lower >= {float(start)}'
    if end is not None:
        where += f' AND p.time_bounds_lower < {float(end)}'
    adql = ("SELECT a.uri AS access_uri, p.time_bounds_lower AS observed_mjd, "
            "p.energy_bandpassname AS detector_name FROM spherex.artifact a "
            f"JOIN spherex.plane p ON a.planeid = p.planeid WHERE {where}")
    response = _irsa('GET', config.get('tap_endpoint', 'https://irsa.ipac.caltech.edu/TAP/sync'),
        params={'REQUEST':'doQuery', 'LANG':'ADQL', 'QUERY':adql, 'FORMAT':'votable', 'MAXREC':20000},
        attempts=1, timeout=(6, 20))
    if b'OVERFLOW' in response.content or b'value="ERROR"' in response.content:
        raise ValueError('TAP returned a truncated result or an error.')
    table = parse_single_table(BytesIO(response.content)).to_table(use_names_over_ids=True)
    unique = {}
    for row in table:
        uri = str(row['access_uri'])
        identity = re.search(r'level2_(.+)D([1-6])_spx_', uri)
        release = re.search(r'/spherex/((?:qr|dr)\d+)/', uri)
        version = re.search(r'l2b-v(\d+)-(\d{4})-(\d{3})', uri)
        if not identity or not release or not uri.endswith('.fits'):
            continue
        collection = 'spherex_' + release[1]
        if collection not in config['collections']:
            continue
        item = dict(id=identity[1], detector=int(identity[2]),
                    source=uri if uri.startswith('https://') else 'https://irsa.ipac.caltech.edu/'+uri.lstrip('/'),
                    release=release[1].upper(), collection=collection, mjd=float(row['observed_mjd']),
                    field_key='archive', field_name='Archive search', context=[], discovery_api='IRSA TAP')
        key = item['id'], item['detector']
        rank = (config['collections'].index(collection),
                -int(version[2]+version[3]) if version else 0, -int(version[1]) if version else 0)
        if key not in unique or rank < unique[key][0]:
            unique[key] = rank, item
    return sorted([value[1] for value in unique.values()], key=lambda r:(r['mjd'],r['detector']))


def discovery_snapshot(ra, dec, radius, start, end):
    from backend.archive import CACHE
    key = json.dumps([round(ra, 8), round(dec, 8), radius, start, end])
    return CACHE / 'lab-discovery' / (hashlib.sha256(key.encode()).hexdigest() + '.json')


def read_discovery_snapshot(ra, dec, radius, start, end):
    # A previously successful all-date query can also recover a narrower date range.
    ranges = [(start, end)] if start is None and end is None else [(start, end), (None, None)]
    for first, last in ranges:
        try:
            path = discovery_snapshot(ra, dec, radius, first, last)
            rows = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        return [row for row in rows if (start is None or row['mjd'] >= start)
                and (end is None or row['mjd'] < end)]
    return []


def query(config, ra, dec, radius=.001, start=None, end=None, *, latest=False):
    """Use the first complete result for interactive searches, or merge both for warmup."""
    pool = ThreadPoolExecutor(max_workers=2)
    futures = {
        pool.submit(query_public_sia, config, ra, dec, radius, start, end): 'IRSA SIA',
        pool.submit(query_tap, config, ra, dec, start, end): 'IRSA TAP',
    }
    errors = []
    partial = []
    complete = []
    try:
        for future in as_completed(futures):
            try:
                records = future.result()
                if not records:
                    continue
                for record in records:
                    record['discovery_api'] = futures[future]
                if any(record.get('discovery_warning') for record in records):
                    partial = records
                    continue
                complete.extend(records)
                if not latest:
                    break
            except (requests.RequestException, ValueError, RuntimeError, KeyError) as error:
                errors.append(error)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    if complete:
        if latest:
            from .featured_views import combined_rows
            complete = combined_rows(partial, complete)
            complete = [{key: value for key, value in row.items() if key != 'discovery_warning'}
                        for row in complete]
        snapshot = discovery_snapshot(ra, dec, radius, start, end)
        try:
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            write_json(snapshot, complete)
        except OSError:
            pass  # A successful search still works on a read-only cache.
        return complete
    from .featured_views import catalog_field, combined_rows, field_inventory
    field = catalog_field(None, dict(ra=ra, dec=dec))
    cached = field_inventory(field) if field else []
    cached = [row for row in cached if (start is None or row['mjd'] >= start)
              and (end is None or row['mjd'] < end)]
    saved = read_discovery_snapshot(ra, dec, radius, start, end)
    previous = saved or saved_discovery(ra, dec, start, end)
    footprints = mirror_rows(ra, dec, start, end)
    if footprints:
        cached = combined_rows(cached, footprints)
    records = combined_rows(cached, previous) if cached else previous
    if partial or records:
        warning = (partial[0]['discovery_warning'] if partial else
                   'Live IRSA search unavailable. Showing a saved subset from the AWS SPHEREx mirror.')
        if records:
            records = [dict(row, discovery_api=row.get('discovery_api', 'Saved exposure index')
                            if cached else 'Saved IRSA observation index')
                       for row in records]
        return [dict(row, discovery_warning=warning)
                for row in (combined_rows(records, partial) if records and partial else records or partial)]
    if len(errors) < len(futures):
        return []
    reason = next((reason for error in errors if (reason := irsa_outage(error))), None)
    raise RuntimeError('Live IRSA search is unavailable'
                       + (f' ({reason}).' if reason else '.')
                       + ' Retry in a few minutes; no saved observations cover this position.') from errors[0]


def saved_discovery(ra, dec, start=None, end=None):
    """Reuse recorded archive identities, never manufacture a sky-coverage result."""
    from backend.archive import discovery_query, key_for, saved_manifest
    from backend.saved_archive import local_rows
    name = 'query-' + key_for(discovery_query(ra, dec)) + '.json'
    rows = list(local_rows(ra, dec))
    for manifest in (name, 'sia-' + name):
        saved, _ = saved_manifest(manifest)
        rows.extend(saved or [])
    unique = {}
    for row in rows:
        uri = row.get('url', '')
        identity = re.search(r'level2_(.+)D([1-6])_spx_', uri)
        release = re.search(r'/spherex/((?:qr|dr)\d+)/', uri)
        mjd = float(row['mjd'])
        if not identity or not release or (start is not None and mjd < start) or (end is not None and mjd >= end):
            continue
        item = dict(id=identity[1], detector=int(identity[2]), source=uri,
                    release=release[1].upper(), collection='spherex_'+release[1], mjd=mjd,
                    field_key='archive', field_name='Saved archive search', context=[])
        key = item['id'], item['detector']
        if key not in unique or reduction_priority(item) > reduction_priority(unique[key]):
            unique[key] = item
    return sorted(unique.values(), key=lambda r: (r['mjd'], r['detector']))


def query_public_sia(config, ra, dec, radius, start, end):
    """Query release collections separately when a combined SIA request fails."""
    try:
        return query_sia(config, ra, dec, radius, start, end, timeout=(5, 8))
    except (requests.RequestException, ValueError, KeyError):
        if len(config['collections']) < 2:
            raise
    records = {}
    failed = []
    from backend.archive import LOW_MEMORY
    with ThreadPoolExecutor(max_workers=1 if LOW_MEMORY else 4) as pool:
        requests_by_collection = {pool.submit(query_sia, dict(config, collections=[collection]),
                                               ra, dec, radius, start, end, (6, 14)): collection
                                  for collection in config['collections']}
        for future in as_completed(requests_by_collection):
            try:
                for row in future.result():
                    key = row['id'], row['detector']
                    if key not in records or reduction_priority(row) > reduction_priority(records[key]):
                        records[key] = row
            except (requests.RequestException, ValueError, KeyError):
                failed.append(requests_by_collection[future])
    if not records and failed:
        raise RuntimeError('IRSA SIA could not read ' + ', '.join(sorted(failed)))
    if failed:
        for row in records.values():
            row['discovery_warning'] = 'Partial IRSA response. Unavailable collections: ' + ', '.join(sorted(failed))
    return sorted(records.values(), key=lambda r: (r['mjd'], r['detector']))


def query_sia(config, ra, dec, radius=.001, start=None, end=None, timeout=(6,20), *, attempts=1):
    params = [('COLLECTION', name) for name in config['collections']]
    params += [('POS', f'circle {ra} {dec} {radius}'), ('MAXREC', '20000')]
    if start is not None or end is not None:
        params.append(('TIME', f"{start if start is not None else '-Inf'} {end if end is not None else 'Inf'}"))
    response = _irsa('GET', config['sia_endpoint'], params=params, timeout=timeout, attempts=attempts)
    if b'OVERFLOW' in response.content:
        raise ValueError('IRSA truncated the search. Narrow the dates; no truncated result is accepted.')
    if b'value="ERROR"' in response.content:
        raise ValueError('IRSA reported an error in its search response.')
    table = parse_single_table(BytesIO(response.content)).to_table(use_names_over_ids=True)
    unique = {}
    for row in table:
        if str(row['access_format']) != 'image/fits' or str(row['dataproduct_subtype']) != 'science':
            continue
        band = str(row['energy_bandpassname'])
        if band not in [f'SPHEREx-D{i}' for i in range(1, 7)]:
            continue
        collection = str(row['obs_collection'])
        rank = config['collections'].index(collection)
        uri = str(row['access_url'])
        identity = re.search(r'level2_(.+)D([1-6])_spx_', uri)
        if not identity or int(identity[2]) != int(band[-1]):
            continue
        item = dict(id=identity[1], detector=int(band[-1]), source=uri,
                    release=collection.removeprefix('spherex_').removesuffix('_deep').upper(), collection=collection,
                    mjd=float(row['t_min']), field_key='archive', field_name='Archive search', context=[])
        key = item['id'], item['detector']
        if key not in unique or rank < unique[key][0]:
            unique[key] = rank, item
    return sorted([value[1] for value in unique.values()], key=lambda r: (r['mjd'], r['detector']))


def download(record, ra, dec, fov, cache, *, prefer_mirror=False, mirror_only=False):
    source = record.get('source', '')
    parsed = urlparse(source)
    if (parsed.scheme != 'https' or parsed.netloc != 'irsa.ipac.caltech.edu'
            or not parsed.path.startswith('/ibe/data/spherex/') or not parsed.path.endswith('.fits')):
        raise ValueError('Expected an official IRSA SPHEREx FITS URL.')
    # Cutouts follow detector axes. Pad the requested square for any sky rotation,
    # plus several pixels for interpolation. A 60 arcmin view uses a 90 arcmin source.
    source_width = round(float(fov) / 60 * 1.5, 8)
    url = source + '?' + urlencode({'center': f'{float(ra)},{float(dec)}', 'size': source_width})
    key = hashlib.sha256(url.encode()).hexdigest()
    path = cache / f'{key}.fits'
    sidecar = cache / f'{key}.record.json'
    download_lock = DOWNLOAD_LOCKS[int(key[:4], 16) % len(DOWNLOAD_LOCKS)]
    with download_lock:
        from .featured_views import BUNDLE
        bundled, bundled_info = BUNDLE / path.name, BUNDLE / sidecar.name
        if cache != BUNDLE and bundled.is_file() and bundled_info.is_file():
            meta = json.loads(bundled_info.read_text(encoding='utf-8'))
            if bundled.stat().st_size == meta.get('file_bytes') and meta['id'] == record['id'] and meta['detector'] == record['detector']:
                return dict(record, **meta, path=str(bundled), fits_url=f'/cache/{bundled.name}')
        if path.exists() and sidecar.exists():
            meta = json.loads(sidecar.read_text())
            if path.stat().st_size == meta.get('file_bytes') and meta['id'] == record['id'] and meta['detector'] == record['detector']:
                return dict(record, **meta, path=str(path), fits_url=f'/cache/{path.name}')
        if not path.exists():
            if shutil.disk_usage(cache).free < 256_000_000:
                raise OSError('Less than 256 MB disk space remains; download paused. Existing data is safe.')
            # Share Parallax's bounded transfer and official S3 range-read
            # fallback. Retrying a failed IPAC proxy cannot repair an outage.
            from backend.archive import download_cutout
            if mirror_only:
                from backend.cloud import mirror_key
                if mirror_key(source) is None:
                    raise ValueError('This exposure has no public AWS mirror path.')
                prefer_mirror = True
            try:
                if prefer_mirror:
                    transport = download_cutout(source, url, path, float(ra), float(dec), float(fov)*1.5,
                                                prefer_mirror=True)
                else:
                    transport = download_cutout(source, url, path, float(ra), float(dec), float(fov)*1.5)
            except (requests.RequestException, OSError, ValueError):
                if mirror_only or not prefer_mirror:
                    raise
                transport = download_cutout(source, url, path, float(ra), float(dec), float(fov)*1.5)
            try:
                metadata = fits_metadata(path)
            except (OSError, ValueError, KeyError):
                path.unlink(missing_ok=True)
                raise
            if metadata['id'] != record['id'] or metadata['detector'] != record['detector']:
                path.unlink(missing_ok=True)
                raise ValueError('The downloaded FITS identity does not match the archive record.')
        meta = fits_metadata(path)
        if meta['id'] != record['id'] or meta['detector'] != record['detector']:
            raise ValueError('Cached FITS identity does not match the archive record.')
        meta.update(file_bytes=path.stat().st_size, requested_source_width_deg=source_width,
                    download_center=[float(ra), float(dec)], download_url=url,
                    provenance='Official IRSA FITS; observation and detector verified; padded source for sky alignment')
        if 'transport' in locals():
            meta['transport'] = transport
            if transport != 'IRSA cutout service':
                from backend.archive import CONFIG as archive_config
                from backend.cloud import mirror_key
                meta['download_url'] = archive_config['cloud_origin'] + mirror_key(source)
                meta['provenance'] = transport + '; native FITS pixels; observation and detector verified'
        write_json(sidecar, meta)
        return dict(record, **meta, path=str(path), fits_url=f'/cache/{path.name}')
