"""Browse the documented public IRSA S3 mirror; no guessed spatial index."""
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
import aiohttp
import numpy as np
import requests
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from .archive import CONFIG,CACHE,key_for,atomic_json,align_cutout,throttle
from .analysis import aligned_products

NS={'s':'http://s3.amazonaws.com/doc/2006-03-01/'}


def validate_prefix(prefix):
    if len(prefix)>350 or '..' in prefix or not re.fullmatch(r'(qr[23]/level2/)[A-Za-z0-9_./-]*',prefix):
        raise ValueError('Choose a released spectral-image archive folder.')
    return prefix


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
    # HTTP range reads follow IRSA's cloud-access tutorial. Only a native cutout
    # and small WCS table are transferred, not the full ~70 MB MEF.
    throttle()
    with fits.open(url,use_fsspec=True,fsspec_kwargs={'block_size':1048576,'client_kwargs':{'timeout':aiohttp.ClientTimeout(total=90),'trust_env':True}},memmap=False) as remote:
        header=remote['IMAGE'].header
        ra,dec=center if center else (float(header['CRVAL1']),float(header['CRVAL2']));source=WCS(header).celestial
        x,y=source.world_to_pixel_values(ra,dec);r=int(np.ceil(fov*60/CONFIG['pixel_scale_arcsec']*.85))
        x0=max(0,int(np.floor(x))-r);x1=min(remote['IMAGE'].shape[1],int(np.ceil(x))+r+1)
        y0=max(0,int(np.floor(y))-r);y1=min(remote['IMAGE'].shape[0],int(np.ceil(y))+r+1)
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
        for name in ['BUNIT','MJD-OBS','DATE-OBS','MJD-AVG','TIMESYS']:
            if name in header:cut_header[name]=header[name]
        hdus=[fits.PrimaryHDU(header=remote[0].header.copy())]
        for name in ['IMAGE','FLAGS','VARIANCE']:
            hdus.append(fits.ImageHDU(remote[name].section[y0:y1,x0:x1].copy(),header=cut_header.copy(),name=name))
        yy,xx=np.mgrid[y0:y1,x0:x1]
        swcs=WCS(header,fobj=remote,key='W');swcs.sip=None
        wave,_=swcs.pixel_to_world(xx,yy)
        hdus.append(fits.ImageHDU(wave.to_value('um').astype('f4'),name='WAVELENGTH'))
        mjd=float(header['MJD-OBS'])
        flags_summary=[dict(name=k.replace('L2 N_',''),count=int(header[k]),scope='full exposure') for k in header.keys() if k.startswith('L2 N_') and isinstance(header[k],(int,float)) and header[k]>0]
    local=fits.HDUList(hdus);local.writeto(fits_file,overwrite=True)
    values,metadata=align_cutout(local,ra,dec,fov)
    products=aligned_products(local,ra,dec,fov)
    if not np.isfinite(values).any():raise ValueError('No usable pixels in the selected exposure center.')
    np.save(CACHE/(identity+'.npy'),values,allow_pickle=False)
    np.savez_compressed(CACHE/(identity+'.npz'),**products)
    wm=products['wavelength'];center=wm[wm.shape[0]//2,wm.shape[1]//2]
    metadata['wavelength_um']=float(center) if np.isfinite(center) else None
    metadata['analysis_version']=3
    match=re.search(r'D([1-6])_spx',key);det=int(match.group(1)) if match else None
    metadata.update(id=key_for(url),url=url,cutout_url=url,cache_id=identity,ra=ra,dec=dec,fov=fov,mjd=mjd,date=Time(mjd,format='mjd').isot+'Z',detector=det,band=f'SPHEREx-D{det}',release=key.split('/')[0],observation=key.rsplit('/',1)[-1],source_key=key,quality_summary=flags_summary,wavelength_source='Per-pixel WCS-WAVE; approximate visualization wavelengths',origin='IRSA public cloud mirror',status='ready',index=0)
    atomic_json(meta_file,metadata)
    return identity,metadata
