"""Curated starters built from real SPHEREx archive observations."""
import gzip
import json
import logging
import shutil
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from hashlib import sha256

import numpy as np
from astropy.io import fits
from astropy.time import Time

from .analysis import aligned_products
from .archive import CACHE, ROOT, align_cutout, atomic_json, download_cutout, key_for

DATA = ROOT/'backend/data'
LOG = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def featured():
    return json.loads((DATA/'featured-fields.json').read_text(encoding='utf8'))


def starter_path(key):
    return CACHE/f'featured-{key}-v2.json'


def prepared_starter(key):
    snapshot = starter_path(key)
    if not snapshot.is_file():
        return None
    try:
        cached = json.loads(snapshot.read_text(encoding='utf8'))
        if all((CACHE/(f['cache_id']+'.'+ext)).is_file()
               for f in cached['frames'] if f['status']=='ready'
               for ext in ('npy','fits','npz')):
            return cached
    except (OSError, ValueError, KeyError):
        pass
    return None


def load_native(row, key, target, field):
    bundled_name = row['local'].rsplit('/',1)[-1].replace(f"-d{row['detector']}.fits", '.fits.gz')
    bundled = DATA/'vesta'/bundled_name
    teammate = ROOT/'nasaSpace-main/outputs/spherex-viewer'/row['local']
    temp = target.with_suffix('.featured.part')
    try:
        if key=='vesta' and bundled.is_file():
            with gzip.open(bundled,'rb') as source, temp.open('wb') as out:
                shutil.copyfileobj(source,out)
            temp.replace(target)
            return 'Bundled IRSA cutout'
        if teammate.is_file() and sha256(teammate.read_bytes()).hexdigest()==row['source_sha256']:
            shutil.copyfile(teammate,temp)
            temp.replace(target)
            return 'Verified local IRSA cutout'
        return download_cutout(row['url'],row['cutout_url'],target,**field)
    finally:
        temp.unlink(missing_ok=True)


def prepare_starter(key):
    cached = prepared_starter(key)
    if cached is not None:
        return cached
    item = featured()[key]
    field = {name:item[name] for name in ('ra','dec','fov')}
    frames, contrasts = [], {}
    for row in sorted(item['frames'], key=lambda entry:entry['date']):
        archive_id = key_for('featured-v2:'+row['source_sha256'])
        target = CACHE/(archive_id+'.fits')
        frame = dict(**field,id=key_for(row['url']),index=len(frames),cache_id=archive_id,
                     detector=row['detector'],band='SPHEREx-D'+str(row['detector']),release=row['release'],
                     date=row['date'],mjd=float(Time(row['date'],scale='utc').mjd),url=row['url'],
                     cutout_url=row['cutout_url'],source_sha256=row['source_sha256'])
        frames.append(frame)
        try:
            transport = load_native(row,key,target,field) if not target.is_file() else 'Saved IRSA cutout'
            with fits.open(target,memmap=False) as hdus:
                values, metadata = align_cutout(hdus,**field)
                if not np.isfinite(values).any():
                    raise ValueError('No usable observed pixels in the field.')
                np.savez_compressed(CACHE/(archive_id+'.npz'),**aligned_products(hdus,**field))
            np.save(CACHE/(archive_id+'.npy'),values,allow_pickle=False)
            frame.update(metadata,status='ready',stage='prepared',transport=transport)
            band = 'D'+str(row['detector'])
            if band not in contrasts:
                low, high = np.nanpercentile(values,[1,99.7])
                contrasts[band] = dict(black=float(low),white=float(max(high,low+1e-8)),
                                       reference_frame=frame['index'],unit=metadata['unit'])
        except (OSError, ValueError, KeyError) as exc:
            LOG.warning('Featured exposure unavailable: %s (%s)', row['date'], type(exc).__name__)
            frame.update(status='error',error='Archived starter exposure unavailable')
    if not contrasts:
        raise ValueError('The selected archive observations could not be loaded.')
    if key=='vesta':
        note = 'Archived D3 observations, 4–5 August 2025. Compare positions; their wavelengths differ.'
    else:
        note = 'Curated archive exposures. Search the full archive to discover additional dates and wavelengths.'
    result = dict(**field,id='example-'+key,example=key,title=item['title'],status='complete',stage='complete',
                  source='example',frames=frames,contrast=next(iter(contrasts.values())),contrasts=contrasts,
                  discovery_complete=False,discovery_note=note)
    if all(frame['status']=='ready' for frame in frames):
        atomic_json(starter_path(key),result)
    return result


def prepare_all():
    keys = list(featured())
    def prepare(key):
        try:
            result = prepare_starter(key)
            print(f"{result['title']}: {sum(f['status']=='ready' for f in result['frames'])} prepared",flush=True)
        except ValueError as exc:
            print(f'{key}: {exc}',flush=True)
    prepare('vesta')
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(prepare,[key for key in keys if key!='vesta']))


if __name__=='__main__':
    prepare_all()
