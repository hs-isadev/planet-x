"""Prepare dated SPHEREx cutouts and previews before someone opens a field."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from threading import Lock
import time
import uuid

from filelock import FileLock, Timeout

from . import server
from .archive import query, write_json
from .featured_views import CACHE, PRESET_FOV, combined_rows, fields, historical_rows, save_entry, view_entry

LOG = logging.getLogger(__name__)


def sample(rows, count):
    if len(rows) <= count:
        return rows
    return [rows[round(i * (len(rows) - 1) / (count - 1))] for i in range(count)]


def refresh(fields_to_warm=None, force=False):
    targets = [f for f in fields() if f['key'] != 'vesta'
               and (not fields_to_warm or f['key'] in fields_to_warm)]
    if not targets or fields_to_warm and set(fields_to_warm) != {f['key'] for f in targets}:
        raise ValueError('Select preset or catalog field keys from /observation-lab/api/library.')
    progress_file = CACHE / 'warmup-status.json'
    state = dict(status='Preparing SPHEREx cache', completed=0, total=len(targets), fields={})
    progress_lock = Lock()

    def publish(key, message, result=None, done=False):
        with progress_lock:
            state.update(status=message, updated=datetime.now(timezone.utc).isoformat())
            if result is not None:
                state['fields'][key] = result
            state['completed'] += int(done)
            write_json(progress_file, state)

    def field_views(group):
        for field in group:
            key = field['key']
            full = bool(field['frames'])
            base, entry = view_entry(key)
            if not force and base == CACHE and entry:
                age = time.time() - datetime.fromisoformat(entry['updated'].replace('Z', '+00:00')).timestamp()
                if age < 86400 and (entry['complete'] or not full and not entry['failures']):
                    publish(key, 'Cached ' + field['name'], entry, True)
                    continue
            publish(key, 'Preparing ' + field['name'])
            try:
                inventory = CACHE / f'{key}-inventory.json'
                if not force and inventory.is_file() and time.time() - inventory.stat().st_mtime < 86400:
                    rows = json.loads(inventory.read_text(encoding='utf-8'))
                else:
                    known = historical_rows(key) if full else []
                    try:
                        rows = query(server.CONFIG, field['ra'], field['dec'], latest=full)
                    except (RuntimeError, ValueError):
                        if not known:
                            raise
                        rows = []
                    partial = not rows or any(row.get('discovery_warning') for row in rows)
                    if partial and known:
                        rows = combined_rows(known, rows)
                        for row in rows:
                            row['discovery_warning'] = 'IRSA live search incomplete; known released exposures are being cached.'
                    elif rows:
                        write_json(inventory, rows)
                requested = rows if full else sample(rows, 4)
                if not requested:
                    raise ValueError('The archive returned no observations covering this position.')
                limits = [len(requested)]
                if full and len(requested) > 96:
                    limits = []
                    limit = 96
                    loaded = entry['loaded'] if entry else 0
                    while limit < len(requested):
                        if limit > loaded:
                            limits.append(limit)
                        limit *= 2
                    limits.append(len(requested))
                for limit in limits:
                    job = uuid.uuid4().hex
                    selected = sample(requested, limit)
                    options = dict(ra=field['ra'], dec=field['dec'], fov=PRESET_FOV,
                                   detector=0, source='archive', mosaic=False, field=key)
                    with server.LOCK:
                        server.JOBS[job] = {'status': 'running', 'stage': 'Warming cache', 'id': job, 'warmup': True}
                    try:
                        server.create_session(job, options, archive_rows=selected)
                    finally:
                        with server.LOCK:
                            result = server.JOBS.pop(job)
                    manifest = result.get('result')
                    if not manifest or not manifest['frames']:
                        raise RuntimeError(result.get('stage') if not manifest else
                                           '; '.join(manifest['failures'][:2]) or 'No usable frames')
                    manifest['archive_matches'] = len(rows)
                    complete = len(selected) == len(rows) and not manifest['failures']
                    write_json(CACHE / job / 'manifest.json', manifest)
                    save_entry(CACHE, field, manifest, complete)
                    _, entry = view_entry(key)
                    report = dict(entry or {}, requested=len(selected), discovered=len(rows),
                                  failures=len(manifest['failures']), last_error=next(iter(manifest['failures']), None))
                    publish(key, 'Prepared ' + field['name'], report, limit == limits[-1] and not manifest['failures'])
                    LOG.info('%s: %s ready, %s discovered, %s errors', key, len(manifest['frames']), len(rows),
                             len(manifest['failures']))
            except Exception as error:
                LOG.warning('SPHEREx warmup %s: %s', key, error)
                publish(key, 'Could not finish ' + field['name'], dict(entry or {}, error=str(error)))
            server.trim_cache()

    try:
        with FileLock(str(CACHE / 'warmup.lock'), timeout=0):
            # Give the long challenge sequences dedicated capacity while nearby/bright
            # fields warm independently.
            core = [f for f in targets if f['frames']]
            stars = [f for f in targets if not f['frames']]
            with ThreadPoolExecutor(max_workers=3) as pool:
                list(pool.map(field_views, (core[::2], core[1::2], stars)))
            status = 'SPHEREx cache ready' if state['completed'] == state['total'] else 'Will retry incomplete SPHEREx fields'
            publish(None, status)
    except Timeout:
        state['status'] = 'The SPHEREx cache is already warming.'
        LOG.info(state['status'])
    return state


def run_forever():
    while True:
        try:
            status = refresh()
            delay = 3600 if status['completed'] == status['total'] else 900
        except Exception:
            LOG.exception('SPHEREx cache refresh failed')
            delay = 900
        time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--field', action='append', help='Only warm this catalog or preset key. Repeat to select several.')
    parser.add_argument('--force', action='store_true', help='Rediscover the archive even when the cache is current.')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    result = refresh(args.field, force=args.force)
    print(f"{result['status']} ({result['completed']}/{result['total']} fields)")
    return 0 if result['completed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
