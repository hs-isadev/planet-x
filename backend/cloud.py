"""Browse the documented public IRSA S3 mirror; no guessed spatial index."""
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote, urlsplit
import aiohttp
import numpy as np
import requests
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from .archive import CONFIG,CACHE,key_for,atomic_json,align_cutout,output_grid,throttle
from .analysis import aligned_products
from .saved_archive import saved_original, preserve_cutout

NS={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}


def validate_prefix(prefix):
    if len(prefix)>350 or '..' in prefix or not re.fullmatch(r'((dr1|qr[23])/level2/)[A-Za-z0-9_./-]*',prefix):
        raise ValueError('Choose a released spectral-image archive folder.')
    return prefix


def mirror_key(url):
    parsed = urlsplit(url)
    prefix = "/ibe/data/spherex/"
    if parsed.scheme != "https" or parsed.netloc != "irsa.ipac.caltech.edu" or not parsed.path.startswith(prefix):
        return None
    key = parsed.path.removeprefix(prefix)
    try:
        validate_prefix(key)
    except ValueError:
        return None
    return key if key.endswith(".fits") else None


def list_archive(prefix='qr3/level2/',cursor=None):
    validate_prefix(prefix)
    if cursor and len(cursor)>4096:raise ValueError('Invalid archive cursor.')
    cache=CACHE/('listing-'+key_for(prefix+str(cursor))+'.json')
    if cache.exists() and time.time()-cache.stat().st_mtime<3600:return __import__('json').loads(cache.read_text())
    params={'list-type':'2','delimiter':'/','prefix':prefix,'max-keys':CONFIG.get('archive_browser_page_size',60)}
    if cursor:params['continuation-token']=cursor
    throttle();response=requests.get(CONFIG['cloud_origin'],params=params,timeout=20);response.raise_for_status()
    tree=ET.fromstring(response.content)
    folders=[e.text for e in tree.findall('s:CommonPrefixes/s:Prefix',NS)]
    files=[]
    for node in tree.findall('s:Contents',NS):
        key=node.find('s:Key',NS).text
        if not key.endswith('.fits'):continue
        files.append(dict(key=key,name=key.rsplit('/',1)[-1],size_bytes=int(node.find('s:Size',NS).text),url=CONFIG['cloud_origin']+quote(key,safe='/')))
    token=tree.find('s:NextContinuationToken',NS)
    result=dict(prefix=prefix,folders=folders,files=files,next_cursor=token.text if token is not None else None,source=CONFIG['cloud_origin'],provenance='catalog',note='Released archive file listing. It is not a coordinate-coverage result.')
    atomic_json(cache,result);return result


def first_exposure():
    prefix='qr3/level2/'
    for _ in range(6):
        page=list_archive(prefix)
        if page['files']:return page['files'][0]['key']
        if not page['folders']:raise ValueError('No released exposures in this folder.')
        prefix=page['folders'][0]
    raise ValueError('Select an exposure in the archive browser.')


def cutout_from_mirror(key, fov, center=None):
    # HTTP range reads follow IRSA's cloud-access tutorial. Only a native cutout
    # and small WCS table are transferred, not the full ~70 MB MEF.
    validate_prefix(key)
    url = CONFIG["cloud_origin"] + quote(key, safe="/")
    local = saved_original(key)
    if local is None:
        throttle()
    http = {"block_size": 1048576, "client_kwargs": {"timeout": aiohttp.ClientTimeout(total=20), "trust_env": True}}
    source_file = fits.open(local, memmap=False) if local else fits.open(url, use_fsspec=True, fsspec_kwargs=http, memmap=False)
    with source_file as remote:
        header=remote['IMAGE'].header
        ra,dec=center if center else (float(header['CRVAL1']),float(header['CRVAL2']));source=WCS(header).celestial
        grid, n, _ = output_grid(ra, dec, fov)
        edge = np.array([0, 0, n - 1, n - 1, (n - 1) / 2])
        x, y = source.world_to_pixel(grid.pixel_to_world(edge, edge[[0, 2, 0, 2, 4]]))
        if not np.isfinite([x, y]).all():
            raise ValueError("The exposure cannot project the selected sky field.")
        height, width = remote['IMAGE'].shape
        x0, x1 = max(0, int(np.floor(x.min())) - 2), min(width, int(np.ceil(x.max())) + 3)
        y0, y1 = max(0, int(np.floor(y.min())) - 2), min(height, int(np.ceil(y.max())) + 3)

        if x1<=x0 or y1<=y0:raise ValueError('This exposure does not cover the selected field.')
        sliced=source.slice((slice(y0,y1),slice(x0,x1)))
        cut_header=sliced.to_header(relax=True)
        # Preserve native detector location and spacecraft metadata in cloud cutouts.
        for name in ("XYZ_SC_SYSTEM", "X_SC", "Y_SC", "Z_SC", "X_SC_START", "Y_SC_START",
                     "Z_SC_START", "DATE-AVG", "DATE-BEG"):
            if name in header:
                cut_header[("HIERARCH " if len(name) > 8 else "") + name] = header[name]
        if ((header.get("WCSNAMEA") or "").strip() == "0-based active pixel coordinates"
                and "CRPIX1A" in header and "CRPIX2A" in header):
            cut_header["WCSNAMEA"] = header["WCSNAMEA"]
            cut_header["CRPIX1A"] = header["CRPIX1A"] - x0
            cut_header["CRPIX2A"] = header["CRPIX2A"] - y0
        for name in ['DETECTOR','DETCOORD','BUNIT','MJD-OBS','DATE-OBS','MJD-AVG','TIMESYS']:
            if name in header:cut_header[name]=header[name]
        primary = fits.PrimaryHDU(header=remote[0].header.copy())
        primary.header["PXORIGIN"] = "IRSA saved original" if local else "IRSA public cloud mirror"
        hdus = [primary]
        for name in ("IMAGE", "FLAGS", "VARIANCE", "ZODI"):
            native = remote[name]
            layer_header = cut_header.copy()
            if "BUNIT" in native.header:
                layer_header["BUNIT"] = native.header["BUNIT"]
            else:
                layer_header.remove("BUNIT", ignore_missing=True)
            hdus.append(fits.ImageHDU(native.section[y0:y1,x0:x1].copy(), header=layer_header, name=name))
        yy,xx=np.mgrid[y0:y1,x0:x1]
        swcs=WCS(header,fobj=remote,key='W');swcs.sip=None
        wave,_=swcs.pixel_to_world(xx,yy)
        hdus.append(fits.ImageHDU(wave.to_value('um').astype('f4'),name='WAVELENGTH'))
        flags_summary=[dict(name=k.replace('L2 N_',''),count=int(header[k]),scope='full exposure') for k in header.keys() if k.startswith('L2 N_') and isinstance(header[k],(int,float)) and header[k]>0]
    return fits.HDUList(hdus), (ra, dec), flags_summary


def cloud_cutout(key,fov=8,center=None):
    validate_prefix(key)
    if not key.endswith('.fits'):raise ValueError('Choose a FITS spectral exposure.')
    url=CONFIG['cloud_origin']+quote(key,safe='/')
    identity=key_for(url+'|'+str(fov)+'|native-analysis-v2'+('|' + str(center) if center else ''))
    meta_file=CACHE/(identity+'.json');fits_file=CACHE/(identity+'.fits')
    if meta_file.exists() and (CACHE/(identity+'.npz')).exists() and fits_file.exists() and (CACHE/(identity+'.npy')).exists():
        import json
        metadata=json.loads(meta_file.read_text())
        if metadata.get('analysis_version',0)<3:
            with fits.open(fits_file,memmap=False) as hdus:products=aligned_products(hdus,metadata['ra'],metadata['dec'],fov)
            np.savez_compressed(CACHE/(identity+'.npz'),**products)
            w=products['wavelength'];center=w[w.shape[0]//2,w.shape[1]//2]
            metadata['wavelength_um']=float(center) if np.isfinite(center) else None
            metadata['analysis_version']=3;atomic_json(meta_file,metadata)
        return identity,metadata
    local, (ra,dec), flags_summary = cutout_from_mirror(key, fov, center)
    mjd=float(local['IMAGE'].header['MJD-OBS'])
    local.writeto(fits_file,overwrite=True)
    values,metadata=align_cutout(local,ra,dec,fov)
    products=aligned_products(local,ra,dec,fov)
    if not np.isfinite(values).any():raise ValueError('No usable pixels in the selected exposure center.')
    np.save(CACHE/(identity+'.npy'),values,allow_pickle=False)
    np.savez_compressed(CACHE/(identity+'.npz'),**products)
    wm=products['wavelength'];center=wm[wm.shape[0]//2,wm.shape[1]//2]
    metadata['wavelength_um']=float(center) if np.isfinite(center) else None
    metadata['analysis_version']=3
    match=re.search(r'D([1-6])_spx',key);det=int(match.group(1)) if match else None
    metadata.update(id=key_for(url),url=url,cutout_url=url,cache_id=identity,ra=ra,dec=dec,fov=fov,mjd=mjd,date=Time(mjd,format='mjd').isot+'Z',detector=det,band=f'SPHEREx-D{det}',release=key.split('/')[0],observation=key.rsplit('/',1)[-1],source_key=key,quality_summary=flags_summary,wavelength_source='Per-pixel WCS-WAVE; approximate visualization wavelengths',origin=local[0].header["PXORIGIN"],status='ready',index=0)
    atomic_json(meta_file,metadata)
    for extension in (".fits", ".npy", ".npz", ".json"):
        preserve_cutout(CACHE / (identity + extension))
    return identity,metadata
