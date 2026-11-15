"""Catalog-distance space. No image-derived or decorative depths."""
import json
import time
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from .archive import ROOT,CONFIG,CACHE,atomic_json,key_for
from .catalogs import gaia_rows,number,tap_query,propagate_gaia


def distance_record(row):
    r=dict(row);p=row.get('parallax');e=row.get('parallax_error')
    if p is not None and e is not None and p>0 and e>0 and p/e>=5:
        distance=1000/p;lo=1000/(p+e);hi=1000/(p-e)
        method='parallax inversion (S/N ≥ 5)';source=row.get('catalog','Gaia DR3')
    elif row.get('distance_gspphot') is not None and row['distance_gspphot']>0 and row.get('distance_gspphot_lower') is not None and row.get('distance_gspphot_upper') is not None:
        distance=row['distance_gspphot'];lo=row['distance_gspphot_lower'];hi=row['distance_gspphot_upper'];method='GSP-Phot model-derived catalog distance';source='Gaia DR3 GSP-Phot'
        if not 0<lo<=distance<=hi:return dict(r,distance_pc=None,distance_note='Invalid catalog distance interval; depth omitted.')
    else:return dict(r,distance_pc=None,distance_note='No reliable positive parallax or usable catalog distance interval; depth omitted.')
    a=np.deg2rad(row['ra']);d=np.deg2rad(row['dec'])
    unit=[float(np.cos(d)*np.cos(a)),float(np.cos(d)*np.sin(a)),float(np.sin(d))]
    return dict(r,distance_pc=float(distance),distance_lower_pc=float(lo),distance_upper_pc=float(hi),distance_method=method,distance_source=source,xyz_pc=[float(distance*v) for v in unit],direction=unit,provenance='catalog',position_provenance='computed from ICRS direction and catalog distance',uncertain=bool((row.get('ruwe') or 0)>1.4 or 'model' in method),distance_note='Catalog statistical interval; parallax zero-point and other systematics are not corrected.')


def simbad_distances(ra,dec,radius,nearby):
    endpoint=CONFIG['simbad_tap_endpoint']
    condition=f'plx_value >= {1000/nearby}' if nearby else f"1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra},{dec},{radius})) AND plx_value>0"
    query=f'SELECT TOP 200 main_id,ra,dec,pmra,pmdec,plx_value,plx_err,plx_bibcode,otype FROM basic WHERE {condition} ORDER BY plx_value DESC'
    cache=CACHE/('simbad-distance-'+key_for(query)+'.json')
    if cache.exists() and time.time()-cache.stat().st_mtime<604800:return json.loads(cache.read_text())
    table=tap_query(endpoint,query,200);rows=[]
    for raw in table:
        row=dict(id=str(raw['main_id']),name=str(raw['main_id']),ra=number(raw['ra']),dec=number(raw['dec']),parallax=number(raw['plx_value']),parallax_error=number(raw['plx_err']),distance_bibcode=str(raw['plx_bibcode']),object_type=str(raw['otype']),catalog='SIMBAD',source=endpoint,ref_epoch=2000.0,pmra=number(raw['pmra']),pmdec=number(raw['pmdec']))
        if row['ra'] is not None and row['dec'] is not None:rows.append(row)
    atomic_json(cache,rows);return rows


def eligible_stellar_record(row):
    # SIMBAD planet entries inherit host coordinates/parallax, not resolved orbital positions.
    return not str(row.get('object_type','')).startswith('Pl')


def space_catalog(ra,dec,fov,scope='nearby',radius_pc=25,include_simbad=False,mjd=None):
    radius=fov/60/np.sqrt(2)
    result=gaia_rows(ra,dec,radius,nearby=radius_pc if scope=='nearby' else None)
    rows=result['rows'];notes=[]
    if scope=='field' and mjd is not None:rows=[propagate_gaia(r,mjd) for r in rows]
    objects=[distance_record(r) for r in rows];fallback_count=0
    if include_simbad:
        try:
            fallback=simbad_distances(ra,dec,radius,radius_pc if scope=='nearby' else None)
            existing=SkyCoord([r['ra'] for r in rows],[r['dec'] for r in rows],unit='deg') if rows else None
            for row in fallback:
                if not eligible_stellar_record(row):continue
                row=propagate_gaia(row,mjd if scope=='field' and mjd is not None else 57388.5) # J2016.0, matching Gaia reference epoch
                position=SkyCoord(row['ra'],row['dec'],unit='deg')
                if existing is not None:
                    separation=position.separation(existing).arcsec
                    if np.min(separation)<2:
                        matched=objects[int(np.argmin(separation))]
                        matched['catalog_name']=row['name'];matched['simbad_source']=row['source'];matched['name']=row['name'].replace('NAME ','').replace('* ','')
                        continue
                r=distance_record(row)
                if r['distance_pc'] is not None:
                    objects.append(r);fallback_count+=1
                    existing=SkyCoord([o['ra'] for o in objects],[o['dec'] for o in objects],unit='deg')
        except Exception:notes.append('SIMBAD distance fallback is unavailable. No substitute distances were added.')
    properties_file=ROOT/'web/assets/stellar-properties.json'
    properties=json.loads(properties_file.read_text()) if properties_file.exists() else {}
    for row in objects:
        row.update(properties.get(row['id'],{}))
    known=[r for r in objects if r['distance_pc'] is not None]
    unknown=[r for r in objects if r['distance_pc'] is None]
    return dict(objects=known,unknown=unknown,scope=scope,radius_pc=radius_pc,truncated=result['truncated'],limit=result['limit'],fallback_count=fallback_count,provenance='catalog',position_provenance='computed',epoch=('image-date angular positions; radial distances at catalog epoch' if scope=='field' and mjd else 'catalog reference epochs (Gaia DR3 2016.0)'),notes=notes+['Observed SPHEREx photos are flat. Depth comes from catalog distances, never from the image.','Distant stars are unresolved light profiles. Close-ups are computed plasma illustrations, not resolved observations. Colors use Gaia temperature/color where available; unknown colors are neutral. Names are SIMBAD matches where available; catalog IDs are retained.','Unknown/poor distances are omitted from 3D and listed separately, not placed at an invented radius.','Nearby mode is a parallax-selected capped sample, not a complete stellar census.','Parallax inversion is used only at S/N ≥ 5; otherwise a labeled GSP-Phot model distance is used if its interval is valid.','Distance intervals exclude unmodeled systematics. High RUWE and model-derived distances are marked as uncertain.'])
