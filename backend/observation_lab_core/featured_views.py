"""Prepared Lab views bundled with the app or saved on the runtime disk."""
from functools import lru_cache
import hashlib
import json
import math
import shutil
import uuid

from backend.archive import CACHE as PLANET_CACHE, ROOT
from .archive import reduction_priority, write_json

CACHE = PLANET_CACHE / 'observation-lab'
BUNDLE = ROOT / 'backend/data/spherex-seed'
INDEX = 'featured-views'
PRESET_FOV = 10
ALTERNATE_FRAME_LIMIT = 60
NAMED_STARS = 50
COLLECTION = ROOT / 'backend/observation_lab_core/data/collection.json'
HISTORY = ROOT / 'backend/data/preset-archive-index.json'
INVENTORIES = BUNDLE / 'inventories'
MOTION_EXAMPLES = BUNDLE.parent / 'motion-examples.json'


@lru_cache(maxsize=1)
def fields():
    core = json.loads(COLLECTION.read_text(encoding='utf-8'))['fields']
    catalog = json.loads((ROOT / 'web/assets/expanded-stars.json').read_text(encoding='utf-8'))
    stars = catalog['objects']
    nearby = sorted((row for row in stars if row['distance_pc'] <= 10), key=lambda row: row['distance_pc'])
    bright = sorted((row for row in stars if row['v_mag'] is not None), key=lambda row: row['v_mag'])
    distinct = {}
    for grouping, candidates in (('Nearby star', nearby), ('Bright star', bright[:NAMED_STARS])):
        for row in candidates:
            if any(abs(row['ra'] - field['ra']) < .1 and abs(row['dec'] - field['dec']) < .1 for field in core):
                continue
            distinct.setdefault(row['id'], dict(key=row['id'].replace(':', '-'), name=' '.join(row['name'].split()),
                                                ra=row['ra'], dec=row['dec'], category=grouping,
                                                distance_pc=row['distance_pc'],
                                                description='HYG 4.1 catalog position', frames=[]))
    if not any(entry['name'].casefold() == 'proxima centauri' for entry in distinct.values()):
        distinct['proxima-centauri'] = dict(
            key='proxima-centauri', name='Proxima Centauri',
            ra=217.39232147200883, dec=-62.67607511676666, distance_pc=1.302,
            category='Nearby star', description='Archived SPHEREx cutout field near Proxima Centauri', frames=[])
    return core + sorted(distinct.values(), key=lambda field: field['distance_pc'])


def view_entry(key, bases=None):
    candidates = []
    for base in (CACHE, BUNDLE) if bases is None else bases:
        try:
            entry = json.loads((base / INDEX / f'{key}.json').read_text(encoding='utf-8'))
            if (base / entry['session'] / 'manifest.json').is_file():
                candidates.append((base, entry))
        except (OSError, ValueError, KeyError):
            continue
    return max(candidates, key=lambda item: (item[1]['loaded'], item[1]['complete'], item[1]['updated']),
               default=(None, None))


def save_entry(base, field, manifest, complete, *, replace=False):
    (base / INDEX).mkdir(parents=True, exist_ok=True)
    frames = manifest['frames']
    _, old = view_entry(field['key'], (base,))
    # Keep serving a larger usable view during failed or incomplete refreshes.
    if not frames or not replace and old and (old['loaded'] > len(frames) or
                              old['loaded'] == len(frames) and old.get('dates') is not None and not complete):
        return
    counts = {str(d): 0 for d in range(1, 7)}
    for frame in frames:
        counts[str(frame['detector'])] += 1
    info = dict(session=manifest['id'], loaded=len(frames), detectors=counts,
                dates=len(observing_days(frames)),
                discovered=manifest['archive_matches'], failures=len(manifest['failures']),
                excluded=len(manifest.get('excluded_frames', [])),
                complete=complete, updated=manifest['created_utc'],
                thumbnail=frames[0]['preview'])
    write_json(base / INDEX / f"{field['key']}.json", info)


def bundle_view(field, entry, *, cutout_sources=None, replace=False):
    """Publish a verified view to the deploy image after copying its dependencies."""
    _, previous = view_entry(field['key'], (BUNDLE,))
    if not replace and previous and (previous['loaded'] > entry['loaded'] or
                     previous['loaded'] == entry['loaded'] and previous.get('dates') is not None
                     and not entry['complete']):
        return
    session = entry['session']
    source = CACHE / session
    manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    BUNDLE.mkdir(parents=True, exist_ok=True)
    for frame in [*manifest['frames'], *manifest.get('excluded_frames', [])]:
        name = frame['fits_url'].removeprefix('/cache/')
        destination = BUNDLE / name
        if destination.is_file():
            if 'sha256' in frame:
                with destination.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != frame['sha256']:
                        raise ValueError(f'Bundled FITS checksum mismatch: {name}')
            continue
        origin = (cutout_sources or {}).get(frame['fits_url'], CACHE / name)
        sidecar = origin.with_suffix('.record.json')
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        with origin.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != metadata['sha256']:
                raise ValueError(f'FITS checksum mismatch: {name}')
        temporary = destination.with_suffix(f'.{uuid.uuid4().hex}.tmp')
        try:
            shutil.copyfile(origin, temporary)
            write_json(destination.with_suffix('.record.json'), metadata)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    # The session is private until the atomic featured index publishes its ID.
    shutil.copytree(source, BUNDLE / session, dirs_exist_ok=True)
    save_entry(BUNDLE, field, manifest, entry['complete'], replace=replace)


def default_preset(field, options):
    return (field is not None and options['fov'] == PRESET_FOV
            and not (options['detector'] or options['start'] or options['end']))


def date_rank(frame):
    return (frame.get('footprint_coverage', 0), frame.get('coverage', 0),
            reduction_priority(frame), -frame.get('caution_fraction', 0))


def observing_days(rows):
    """Group UTC observation dates and prefer the best available coverage per day."""
    days = {}
    for row in sorted(rows, key=lambda item: (item['mjd'], item['detector'], item['id'])):
        days.setdefault(math.floor(row['mjd']), []).append(row)
    return [sorted(day, key=date_rank, reverse=True) for day in days.values()]


@lru_cache(maxsize=1)
def motion_examples():
    return json.loads(MOTION_EXAMPLES.read_bytes()) if MOTION_EXAMPLES.is_file() else {}


def sample_frames(rows, count=ALTERNATE_FRAME_LIMIT):
    if len(rows) <= count:
        return rows
    return [rows[round(i * (len(rows) - 1) / (count - 1))] for i in range(count)]


def catalog_field(field_key, options):
    return next((field for field in fields() if field['key'] != 'vesta'
                 and (not field_key or field['key'] == field_key)
                 and abs(field['ra'] - options['ra']) < 0.00001
                 and abs(field['dec'] - options['dec']) < 0.00001), None)


def locate(field_key, options):
    """Only serve an instant snapshot on its exact sky grid."""
    if options['fov'] != PRESET_FOV:
        return None
    return catalog_field(field_key, options)


def cache_path(relative):
    for base in (BUNDLE, CACHE):
        path = (base / relative).resolve()
        if path.is_relative_to(base.resolve()) and path.is_file():
            return path
    return None


@lru_cache(maxsize=1)
def preset_history():
    return json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.is_file() else {}


def historical_rows(key):
    """Recover genuine, dated exposure identities from the saved IRSA queries."""
    rows = []
    for identity, detector, mjd, source in preset_history().get(key, []):
        release = source.split('/', 1)[0]
        rows.append(dict(id=identity.rsplit(f'D{detector}', 1)[0], detector=detector, mjd=mjd,
                         source='https://irsa.ipac.caltech.edu/ibe/data/spherex/' + source,
                         collection='spherex_' + release, release=release.upper(),
                         field_key=key, field_name='Saved IRSA discovery', context=[],
                         discovery_api='Saved IRSA observation index'))
    return rows


def field_inventory(field):
    """Archive receipts for this exact coordinate can be used with AWS directly."""
    key = field['key']
    known = historical_rows(key)
    for folder in (INVENTORIES, CACHE):
        path = folder / f'{key}-inventory.json'
        if path.is_file():
            known = combined_rows(known, json.loads(path.read_text(encoding='utf-8')))
    base, entry = view_entry(key)
    if entry:
        manifest = json.loads((base / entry['session'] / 'manifest.json').read_text(encoding='utf-8'))
        receipts = [{name: frame[name] for name in ('id', 'detector', 'mjd', 'source', 'release')}
                    for frame in manifest['frames'] if frame.get('source')]
        known = combined_rows(known, receipts)
    return known


def combined_rows(known, current):
    by_identity = {}
    for row in [*known, *current]:
        identity = (row['id'], row['detector'])
        if identity not in by_identity or reduction_priority(row) >= reduction_priority(by_identity[identity]):
            by_identity[identity] = row
    return sorted(by_identity.values(), key=lambda row: (row['mjd'], row['detector'], row['id']))
