"""Catalog overlays: Gaia DR3 via ESA TAP, AllWISE via documented IRSA cloud dataset."""
import json
import time
import warnings
import re
import os
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
import pyvo
import requests
from filelock import FileLock
from .archive import CACHE,CONFIG,atomic_json,key_for,throttle,output_grid


def tap_query(endpoint,query,maxrec,timeout=45):
    session=requests.Session();original=session.request
    def bounded(*a,**k):k.setdefault('timeout',timeout);return original(*a,**k)
    session.request=bounded;throttle()
    return pyvo.dal.TAPService(endpoint,session=session).search(query,maxrec=maxrec).to_table()


def number(value):
    if np.ma.is_masked(value):return None
    try:
        value=float(value);return value if np.isfinite(value) else None
    except (ValueError,TypeError):return None


def normalized_query(query):
    # Serialization differences below 1e-9 deg are far below the catalog/image precision.
    return re.sub(r'(?<![A-Za-z_])[+-]?\d+\.\d+(?:[eE][+-]?\d+)?',lambda m:f'{float(m.group()):.9f}',query)


def cached_gaia_query(query):
    cache=CACHE/('gaia-'+key_for(query)+'.json')
    if cache.exists() and time.time()-cache.stat().st_mtime<CONFIG['catalog_cache_seconds']:
        return json.loads(cache.read_text())
    normalized=normalized_query(query)
    # Reuse a genuine legacy result only for the numerically equivalent query,
    # never for a different footprint, table, selection, limit or ordering.
    for candidate in sorted(CACHE.glob('gaia-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:40]:
        if time.time()-candidate.stat().st_mtime>=CONFIG['catalog_cache_seconds']:continue
        try:
            result=json.loads(candidate.read_text())
            if normalized_query(result.get('query',''))==normalized:
                atomic_json(cache,result);stamp=candidate.stat().st_mtime;os.utime(cache,(stamp,stamp));return result
        except (OSError,ValueError):continue
    return None


def _gaia_rows(ra,dec,radius,nearby=None):
    limit=CONFIG['catalog_limit']
    if nearby is None:
        condition=f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{float(ra)},{float(dec)},{float(radius)}))"
        order='phot_g_mean_mag ASC'
    else:
        condition=f'parallax >= {1000/float(nearby)} AND parallax_over_error >= 5'
        order='parallax DESC'
    query=f"SELECT TOP {limit+1} source_id,designation,ra,dec,ref_epoch,parallax,parallax_error,pmra,pmdec,phot_g_mean_mag,ruwe,distance_gspphot,distance_gspphot_lower,distance_gspphot_upper FROM {CONFIG['gaia_table']} WHERE {condition} ORDER BY {order}"
    cache=CACHE/('gaia-'+key_for(query)+'.json')
    cached=cached_gaia_query(query)
    if cached is not None:return cached
    error=None
    for endpoint in [CONFIG['gaia_tap_endpoint']]+CONFIG.get('gaia_tap_fallbacks',[]):
        try:table=tap_query(endpoint,query,limit+1);break
        except Exception as exc:error=exc
    else:raise error
    rows=[]
    for r in table[:limit]:
        row={name:number(r[name]) for name in ['ra','dec','ref_epoch','parallax','parallax_error','pmra','pmdec','phot_g_mean_mag','ruwe','distance_gspphot','distance_gspphot_lower','distance_gspphot_upper']}
        row.update(id=str(r['source_id']),name=str(r['designation']),catalog='Gaia DR3',provenance='catalog',source=endpoint)
        rows.append(row)
    result=dict(rows=rows,truncated=len(table)>limit,limit=limit,query=query)
    atomic_json(cache,result);return result


def _wise_rows(ra,dec,radius):
    """Cloud partition strategy and names come from IRSA cloud-access tutorial."""
    cache=CACHE/('wise-v2-'+key_for(f'{ra}|{dec}|{radius}')+'.json')
    if cache.exists() and time.time()-cache.stat().st_mtime<CONFIG['catalog_cache_seconds']:return json.loads(cache.read_text())
    # IEEE-754 adjacent values represent the same user coordinate after parsing.
    # Try only those exact legacy cache keys; do not substitute another sky patch.
    for ar in (float(ra),float(np.nextafter(ra,-np.inf)),float(np.nextafter(ra,np.inf))):
        for de in (float(dec),float(np.nextafter(dec,-np.inf)),float(np.nextafter(dec,np.inf))):
            candidate=CACHE/('wise-v2-'+key_for(f'{ar}|{de}|{radius}')+'.json')
            if candidate!=cache and candidate.exists() and time.time()-candidate.stat().st_mtime<CONFIG['catalog_cache_seconds']:
                result=json.loads(candidate.read_text());atomic_json(cache,result);stamp=candidate.stat().st_mtime;os.utime(cache,(stamp,stamp));return result
    import pyarrow.dataset as ds
    import pyarrow.fs as pafs
    from astropy_healpix import HEALPix
    hp=HEALPix(nside=32,order='nested',frame='icrs')
    cells=hp.cone_search_skycoord(SkyCoord(ra,dec,unit='deg'),radius*u.deg).tolist()
    remote=pafs.S3FileSystem(region=CONFIG['wise_cloud_region'],anonymous=True,connect_timeout=10,request_timeout=30)
    root=CONFIG['wise_cloud_bucket']+'/'+CONFIG['wise_parquet_root']
    dataset=ds.dataset(root,filesystem=remote,format='parquet',partitioning='hive')
    # Inspect actual schema before selecting fields; absent motion metadata stays absent.
    required=['designation','ra','dec','w1mpro','w2mpro','healpix_k5']
    if any(c not in dataset.schema.names for c in required):raise ValueError('AllWISE cloud schema changed; update the configured adapter.')
    extra=[c for c in ['cc_flags','pmra','pmdec','ra_pm','dec_pm','sigpmra','sigpmdec','pmcode','w1mjdmean','w2mjdmean'] if c in dataset.schema.names]
    columns=list(dict.fromkeys(required+extra))
    dec_min,dec_max=max(-90,dec-radius),min(90,dec+radius)
    condition=ds.field('healpix_k5').isin(cells)&(ds.field('dec')>=dec_min)&(ds.field('dec')<=dec_max)
    span=radius/max(np.cos(np.deg2rad(dec)),.001)
    if span<180:
        lo,hi=(ra-span)%360,(ra+span)%360
        ra_condition=((ds.field('ra')>=lo)&(ds.field('ra')<=hi)) if lo<hi else ((ds.field('ra')>=lo)|(ds.field('ra')<=hi))
        condition=condition&ra_condition
    table=dataset.to_table(columns=columns,filter=condition)
    rows=[];center=SkyCoord(ra,dec,unit='deg')
    for raw in table.to_pylist():
        if center.separation(SkyCoord(raw['ra'],raw['dec'],unit='deg')).deg>radius:continue
        row={k:(number(v) if k not in ('designation','cc_flags') else str(v)) for k,v in raw.items()}
        row.update(id=str(raw['designation']),name='WISEA J'+str(raw['designation']).lstrip('J'),catalog='AllWISE',provenance='catalog',source='IRSA public cloud AllWISE catalog',motion_applied=False,motion_note='AllWISE non-moving solution position. Motion-fit parameters are not applied without a verified matching reference epoch.')
        rows.append(row)
    rows.sort(key=lambda r:r.get('w2mpro') if r.get('w2mpro') is not None else 99)
    result=dict(rows=rows[:CONFIG['catalog_limit']],truncated=len(rows)>CONFIG['catalog_limit'],limit=CONFIG['catalog_limit'])
    atomic_json(cache,result);return result


def gaia_rows(ra,dec,radius,nearby=None):
    with FileLock(str(CACHE/('gaia-request-'+key_for(f'{ra}|{dec}|{radius}|{nearby}')+'.lock')),timeout=60):
        return _gaia_rows(ra,dec,radius,nearby)


def wise_rows(ra,dec,radius):
    with FileLock(str(CACHE/('wise-request-'+key_for(f'{ra}|{dec}|{radius}')+'.lock')),timeout=60):
        return _wise_rows(ra,dec,radius)


def propagate_gaia(row,mjd):
    result=dict(row);result['motion_applied']=False
    if all(row.get(k) is not None for k in ('ra','dec','pmra','pmdec','ref_epoch')):
        c=SkyCoord(ra=row['ra']*u.deg,dec=row['dec']*u.deg,pm_ra_cosdec=row['pmra']*u.mas/u.yr,pm_dec=row['pmdec']*u.mas/u.yr,obstime=Time(row['ref_epoch'],format='jyear'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore');c=c.apply_space_motion(new_obstime=Time(mjd,format='mjd'))
        result.update(ra=float(c.ra.deg),dec=float(c.dec.deg),motion_applied=True,motion_note='Linear angular proper motion to image date; no parallax or radial-velocity displacement applied.')
    else:result['motion_note']='Proper motion unavailable; catalog position retained.'
    return result


def wise_gaia_context(rows,mjd):
    """Gaia angular astrometry at the WISE motion-fit epoch and image date."""
    usable=[r for r in rows if all(number(r.get(k)) is not None for k in ('ra','dec','pmra','pmdec','ref_epoch')) and (r.get('ruwe') is None or r['ruwe']<=1.4)]
    if not usable:return None
    c=SkyCoord(ra=[r['ra'] for r in usable]*u.deg,dec=[r['dec'] for r in usable]*u.deg,
        pm_ra_cosdec=[r['pmra'] for r in usable]*u.mas/u.yr,pm_dec=[r['pmdec'] for r in usable]*u.mas/u.yr,
        obstime=Time([r['ref_epoch'] for r in usable],format='jyear'))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        reference=c.apply_space_motion(new_obstime=Time(float(CONFIG.get('wise_motion_reference_mjd',55400.)),format='mjd'))
        current=c.apply_space_motion(new_obstime=Time(mjd,format='mjd'))
    return dict(rows=usable,reference=reference,current=current)


def propagate_wise(row,mjd,gaia_context=None):
    """Use only unambiguous Gaia associations for date-dependent WISE markers.

    IRSA AllWISE Supplement II.6.b.i explicitly advises against predicting
    other epochs from its apparent-motion measurements. Those are NOT used.
    The AllWISE motion-fit position has a documented MJD 55400 epoch and is
    used only for the cross-match, not as a proper-motion model.
    """
    result=dict(row,motion_applied=False)
    result['motion_note']='Stationary AllWISE position retained: no unambiguous Gaia proper-motion association. AllWISE apparent motion is not extrapolated.'
    if gaia_context is None or any(number(row.get(k)) is None for k in ('ra_pm','dec_pm')):return result
    code=str(row.get('pmcode') or '')
    if len(code)>1 and code[1]=='Y':
        result['motion_note']='AllWISE blend-swap flag: stationary position retained.';return result
    if not (0<=row['ra_pm']<360 and -90<=row['dec_pm']<=90):return result
    source=SkyCoord(row['ra_pm']*u.deg,row['dec_pm']*u.deg)
    separations=source.separation(gaia_context['reference']).arcsec
    matches=np.flatnonzero(separations<=float(CONFIG.get('wise_gaia_match_arcsec',1.)))
    if len(matches)!=1:return result
    index=int(matches[0]);g=gaia_context['rows'][index];pos=gaia_context['current'][index]
    result.update(ra=float(pos.ra.deg),dec=float(pos.dec.deg),motion_applied=True,
        catalog_ra=row['ra'],catalog_dec=row['dec'],astrometry_catalog='Gaia DR3 association',
        gaia_source_id=g['id'],association_separation_arcsec=float(separations[index]),
        motion_note='Marker uses Gaia angular proper motion for a unique association at the AllWISE MJD 55400 position (within 1 arcsec). No annual parallax; the cross-match is not a confirmed SPHEREx detection.')
    return result


def catalog_overlay(job,index,catalog):
    frame=job['frames'][index];radius=job['fov']/60/np.sqrt(2)+120/3600
    response=gaia_rows(job['ra'],job['dec'],radius) if catalog=='gaia' else wise_rows(job['ra'],job['dec'],radius)
    wcs,n,_=output_grid(job['ra'],job['dec'],job['fov']);markers=[];wise_context=None
    if catalog=='wise':
        try:wise_context=wise_gaia_context(gaia_rows(job['ra'],job['dec'],radius)['rows'],frame['mjd'])
        except Exception:pass
    for row in response['rows']:
        if row.get('ra') is None or row.get('dec') is None:continue
        r=propagate_gaia(row,frame['mjd']) if catalog=='gaia' else propagate_wise(row,frame['mjd'],wise_context)
        x,y=wcs.world_to_pixel_values(r['ra'],r['dec']);x=(float(x)+.5)/n;y=1-(float(y)+.5)/n
        if 0<=x<=1 and 0<=y<=1:markers.append(dict(r,x=x,y=y))
    return dict(catalog=catalog,provenance='catalog',positions='computed propagation and projection',markers=markers,truncated=response['truncated'],mjd=frame['mjd'],notes=['Markers are catalog predictions, not detections in SPHEREx pixels.','Gaia proper motions are applied where available; parallax displacement is not modeled.','WISE date-dependent markers use unique Gaia proper-motion associations at the documented MJD 55400 motion-fit position. Unmatched/blend-swapped sources retain stationary WISE coordinates. AllWISE apparent motions are not extrapolated.'])
