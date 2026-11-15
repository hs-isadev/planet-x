"""Resumable bulk mirror of public DR1 and QR3 spectral image FITS files."""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import backend  # Sets the application astronomy cache paths before Astropy.
from astropy.io import fits
from filelock import FileLock, Timeout
from backend.archive import CACHE, CONFIG
from backend.saved_archive import CUTOUTS, SAVED, STATE, original_path, inventory_status

GIB = 1024**3
NS = {'s': 'http://s3.amazonaws.com/doc/2006-03-01/'}
ORIGIN = CONFIG['cloud_origin']

def connect():
    SAVED.mkdir(exist_ok=True)
    db = sqlite3.connect(STATE, timeout=20)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript("""
      CREATE TABLE IF NOT EXISTS periods (prefix TEXT PRIMARY KEY, token TEXT,
        done INTEGER NOT NULL DEFAULT 0, pages INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS images (key TEXT PRIMARY KEY, prefix TEXT NOT NULL,
        size INTEGER NOT NULL, rank INTEGER NOT NULL, sha256 TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, error TEXT);
      CREATE INDEX IF NOT EXISTS queue ON images(sha256,rank,attempts);
    """)
    return db

def listing(prefix, token=None, delimiter=None):
    params = {'list-type': '2', 'prefix': prefix, 'max-keys': 1000}
    if delimiter:
        params['delimiter'] = delimiter
    if token:
        params['continuation-token'] = token
    response = requests.get(ORIGIN, params=params, timeout=(8, 25))
    response.raise_for_status()
    tree = ET.fromstring(response.content)
    return tree, tree.findtext('s:NextContinuationToken', namespaces=NS)

def seed(db):
    for release in CONFIG['releases']:
        prefix, token = release + '/level2/', None
        while True:
            tree, token = listing(prefix, token, delimiter='/')
            periods = [(node.text,) for node in tree.findall('s:CommonPrefixes/s:Prefix', NS)]
            db.executemany('INSERT OR IGNORE INTO periods(prefix) VALUES(?)', periods)
            db.commit()
            if not token:
                break

def enumerate_page(prefix, token):
    tree, next_token = listing(prefix, token)
    images = []
    for node in tree.findall('s:Contents', NS):
        key = node.findtext('s:Key', namespaces=NS)
        try:
            original_path(key)
        except ValueError:
            continue
        size = int(node.findtext('s:Size', namespaces=NS))
        rank = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        images.append((key, prefix, size, rank))
    return images, next_token

def save_cutouts():
    CUTOUTS.mkdir(exist_ok=True)
    count = 0
    for source in CACHE.iterdir():
        if not source.is_file() or not (source.name.startswith(('query-', 'sia-query-')) and source.suffix == '.json' or
            len(source.stem) == 24 and source.suffix in ('.fits', '.npz', '.npy', '.json')):
            continue
        destination = CUTOUTS / source.name
        if destination.is_file():
            continue
        try:
            # A second NTFS link survives cleanup in the active cache without duplicating bytes.
            os.link(source, destination)
        except OSError:
            temporary = destination.with_suffix(destination.suffix + '.tmp')
            try:
                shutil.copyfile(source, temporary)
                temporary.replace(destination)
            except FileNotFoundError:
                pass
            finally:
                temporary.unlink(missing_ok=True)
        count += destination.is_file()
    return count

def download(key, size):
    path = original_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix('.part')
    digest = hashlib.sha256()
    try:
        with requests.get(ORIGIN + quote(key, safe='/'), timeout=(8, 25), stream=True) as response:
            response.raise_for_status()
            if int(response.headers.get('Content-Length', -1)) != size:
                raise ValueError('Archive size changed; restart inventory for this prefix.')
            count = 0
            deadline = time.monotonic() + 180
            with part.open('wb') as out:
                for block in response.iter_content(1024 * 1024):
                    count += len(block)
                    if count > size or time.monotonic() > deadline:
                        raise ValueError('Unexpected archive size or transfer exceeded 180 seconds.')
                    digest.update(block)
                    out.write(block)
            if count != size:
                raise ValueError('Incomplete archive transfer.')
        with fits.open(part, memmap=True) as hdus:
            hdus.verify('exception')
            if not {'IMAGE','FLAGS','VARIANCE'} <= {h.name for h in hdus}:
                raise ValueError('Missing native SPHEREx science extensions.')
            if hdus[-1].fileinfo()['datLoc'] + hdus[-1].fileinfo()['datSpan'] > size:
                raise ValueError('Truncated FITS extension.')
        part.replace(path)
        return digest.hexdigest()
    finally:
        part.unlink(missing_ok=True)


def next_files(db, slots, allowance, active):
    # Prefer the release/period with the fewest originals already saved, so
    # early progress spans survey weeks and sectors independent of the presets.
    rows = db.execute("""
        WITH saved AS (
          SELECT prefix, count(*) AS n FROM images WHERE sha256 IS NOT NULL GROUP BY prefix
        )
        SELECT key,size FROM images LEFT JOIN saved USING(prefix)
        WHERE sha256 IS NULL AND attempts<3 AND size<=?
        ORDER BY coalesce(n,0), attempts, rank LIMIT ?
    """, (allowance, slots+len(active))).fetchall()
    for key,size in rows:
        if key not in active:
            yield key,size

def run(db, options):
    print(json.dumps({'saved_existing_cache_files': save_cutouts()}), flush=True)
    seed(db)
    for key,size in db.execute('SELECT key,size FROM images WHERE sha256 IS NOT NULL').fetchall():
        path=original_path(key)
        if not path.is_file() or path.stat().st_size!=size:
            db.execute('UPDATE images SET sha256=NULL,attempts=0 WHERE key=?',(key,))
    db.commit()
    if options.retry_failed:
        db.execute('UPDATE images SET attempts=0 WHERE sha256 IS NULL')
        db.commit()
    bytes_saved = db.execute('SELECT coalesce(sum(size),0) FROM images WHERE sha256 IS NOT NULL').fetchone()[0]
    budget, reserve = options.budget_gib*GIB, options.keep_free_gib*GIB
    indexing, loading = {}, {}
    next_progress = 0
    with ThreadPoolExecutor(4) as catalog, ThreadPoolExecutor(options.workers) as files:
        while True:
            for future in [f for f in indexing if f.done()]:
                prefix = indexing.pop(future)
                try:
                    rows, token = future.result()
                except (requests.RequestException, ET.ParseError) as error:
                    print(json.dumps({'index_error':prefix,'error':str(error)}), flush=True)
                    time.sleep(3)
                    continue
                db.executemany('INSERT OR IGNORE INTO images(key,prefix,size,rank) VALUES(?,?,?,?)', rows)
                db.execute('UPDATE periods SET pages=pages+1,token=?,done=? WHERE prefix=?', (token, token is None, prefix))
                db.commit()
            for future in [f for f in loading if f.done()]:
                key, size = loading.pop(future)
                try:
                    sha = future.result()
                    db.execute('UPDATE images SET sha256=?,error=NULL WHERE key=?', (sha,key))
                    bytes_saved += size
                except Exception as error:
                    db.execute('UPDATE images SET attempts=attempts+1,error=? WHERE key=?', (str(error)[:500],key))
                db.commit()
            active_prefixes = set(indexing.values())
            for prefix,token in db.execute("SELECT prefix,token FROM periods WHERE done=0 ORDER BY pages, prefix").fetchall():
                if len(indexing)>=4:
                    break
                if prefix not in active_prefixes:
                    indexing[catalog.submit(enumerate_page,prefix,token)] = prefix
            free = shutil.disk_usage(SAVED).free
            reserved = sum(size for _,size in loading.values())
            allowance = min(budget-bytes_saved,free-reserve)-reserved
            if allowance>0 and len(loading)<options.workers:
                active = {key for key,_ in loading.values()}
                for key,size in next_files(db,options.workers-len(loading),allowance,active):
                    if size<=allowance:
                        loading[files.submit(download,key,size)] = (key,size)
                        allowance -= size
                    if len(loading)>=options.workers:
                        break
            if time.monotonic()>=next_progress or not indexing and not loading:
                print(json.dumps(inventory_status(db) | {'free_bytes':free,'budget_bytes':budget,'active_transfers':len(loading)}), flush=True)
                next_progress=time.monotonic()+10
            if not indexing and not loading:
                return
            wait([*indexing,*loading],timeout=.75,return_when=FIRST_COMPLETED)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--budget-gib',type=int,default=24)
    parser.add_argument('--keep-free-gib',type=int,default=40)
    parser.add_argument('--workers',type=int,default=3,choices=range(1,5))
    parser.add_argument('--status',action='store_true')
    parser.add_argument('--retry-failed',action='store_true')
    options=parser.parse_args()
    if options.budget_gib<0 or options.keep_free_gib<0:
        parser.error('Disk limits must be nonnegative.')
    with connect() as db:
        if options.status:
            print(json.dumps(inventory_status(db),indent=2))
        else:
            try:
                with FileLock(str(SAVED/'prefetch.lock'),timeout=0):
                    run(db, options)
            except Timeout:
                parser.exit(1,'A prefetch process is already running. Use --status.\n')
