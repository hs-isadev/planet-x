"""Prepared Lab views bundled with the app or saved on the runtime disk."""
from functools import lru_cache
import json

from backend.archive import CACHE as PLANET_CACHE, ROOT
from .archive import reduction_priority, write_json

CACHE = PLANET_CACHE / 'observation-lab'
BUNDLE = ROOT / 'backend/data/spherex-seed'
INDEX = 'featured-views'
PRESET_FOV = 10
NAMED_STARS = 50
COLLECTION = ROOT / 'backend/observation_lab_core/data/collection.json'
HISTORY = ROOT / 'backend/data/preset-archive-index.json'


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
                                                description='HYG 4.1 catalog position', frames=[]))
    return core + list(distinct.values())


def view_entry(key):
    for base in (CACHE, BUNDLE):
        try:
            entry = json.loads((base / INDEX / f'{key}.json').read_text(encoding='utf-8'))
            if (base / entry['session'] / 'manifest.json').is_file():
                return base, entry
        except (OSError, ValueError, KeyError):
            continue
    return None, None


def save_entry(base, field, manifest, complete):
    (base / INDEX).mkdir(parents=True, exist_ok=True)
    frames = manifest['frames']
    old_base, old = view_entry(field['key'])
    # Keep serving a larger usable view during failed or incomplete refreshes.
    if not frames or old and not complete and old['loaded'] >= len(frames):
        return
    counts = {str(d): 0 for d in range(1, 7)}
    for frame in frames:
        counts[str(frame['detector'])] += 1
    info = dict(session=manifest['id'], loaded=len(frames), detectors=counts,
                discovered=manifest['archive_matches'], failures=len(manifest['failures']),
                excluded=len(manifest.get('excluded_frames', [])),
                complete=complete, updated=manifest['created_utc'],
                thumbnail=frames[0]['preview'])
    write_json(base / INDEX / f"{field['key']}.json", info)


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
    for base in (CACHE, BUNDLE):
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


def combined_rows(known, current):
    by_identity = {}
    for row in [*known, *current]:
        identity = (row['id'], row['detector'])
        if identity not in by_identity or reduction_priority(row) >= reduction_priority(by_identity[identity]):
            by_identity[identity] = row
    return sorted(by_identity.values(), key=lambda row: (row['mjd'], row['detector'], row['id']))
