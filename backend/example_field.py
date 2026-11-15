"""Bundled IRSA cutouts for an offline asteroid blink demonstration."""
import gzip
import json
import shutil
import time

import numpy as np
from astropy.io import fits
from astropy.time import Time

from .analysis import aligned_products
from .archive import CACHE, ROOT, align_cutout, download_cutout, key_for

VESTA = ROOT/'backend/data/vesta'


def vesta_example():
    data = json.loads((VESTA/'manifest.json').read_text(encoding='utf8'))
    field = {key:data[key] for key in ('ra','dec','fov')}
    frames = []
    contrast = None
    for index, row in enumerate(data['frames']):
        archive_id = key_for('vesta-example-v1:'+row['retained_sha256'])
        path = CACHE/(archive_id+'.fits')
        if not path.is_file():
            bundled = VESTA/row['file']
            if bundled.is_file():
                temp = path.with_suffix('.example.part')
                with gzip.open(bundled,'rb') as original, temp.open('wb') as out:
                    shutil.copyfileobj(original,out)
                temp.replace(path)
            else:
                download_cutout(row['source_url'],row['cutout_url'],path,**field)
        with fits.open(path,memmap=False) as hdus:
            values, info = align_cutout(hdus,**field)
            np.savez_compressed(CACHE/(archive_id+'.npz'),**aligned_products(hdus,**field))
        np.save(CACHE/(archive_id+'.npy'),values,allow_pickle=False)
        if contrast is None:
            low, high = np.nanpercentile(values,[1,99.7])
            contrast = dict(black=float(low),white=float(max(high,low+1e-8)),reference_frame=0,unit=info['unit'])
        frames.append(dict(info,**field,id=key_for(row['source_url']),index=index,status='ready',stage='prepared',
                           cache_id=archive_id,detector=data['detector'],band='SPHEREx-D3',release=data['release'],
                           date=row['date'],mjd=float(Time(row['date'],scale='utc').mjd),url=row['source_url'],
                           cutout_url=row['cutout_url'],transport='Selected IRSA cutout',source_sha256=row['source_sha256']))
    return dict(**field,id='example-vesta',title='Vesta · 4–5 August 2025',status='complete',stage='complete',created=time.monotonic(),
                source='example',frames=frames,contrast=contrast,discovery_complete=False,
                discovery_note='Two archived IRSA D3 exposures, 4–5 August 2025. Wavelengths differ; use positions, not flux changes, for motion.')
