"""Catalog orbit summaries for illustrative companion layouts, not ephemerides."""
import json
from functools import lru_cache
import numpy as np
from .archive import ROOT

@lru_cache(maxsize=1)
def planet_rows():
    return json.loads((ROOT/'web/assets/exoplanet-orbits.json').read_text(encoding='utf-8'))['rows']

def planets_for(ra,dec,name=''):
    # High proper-motion hosts need a name match, not a broad angular match.
    normal=name.lower().strip()
    host={"barnard":"barnard's star"}.get(normal,normal)
    rows=[r for r in planet_rows() if r['hostname'].lower()==host]
    if not rows:
        cos=np.cos(np.deg2rad(dec))
        rows=[r for r in planet_rows() if abs(r['dec']-dec)<3/3600 and abs((r['ra']-ra+180)%360-180)*cos<3/3600]
    return [dict(name=r['pl_name'],semimajor_au=r['pl_orbsmax'],period_days=r['pl_orbper'],
                 radius_earth=r.get('pl_rade'),star_radius_solar=r.get('st_rad'),temperature_k=r.get('st_teff'),
                 provenance='catalog / computed',source='https://exoplanetarchive.ipac.caltech.edu/',
                 note='Catalog period and orbital scale. Circular face-on layout, phase, inclination, display size and appearance are illustrative; not a measured planet position.')
            for r in rows if r.get('pl_orbsmax') and r.get('pl_orbper')]

def install_companion_routes(app):
    from fastapi import Query
    @app.get('/api/companions')
    def companions(ra:float=Query(ge=0,lt=360),dec:float=Query(ge=-90,le=90),name:str=''):
        return dict(planets=planets_for(ra,dec,name),note='No catalog match means no known planetary orbit is installed; it does not mean the star has no planets.')

    @app.get('/api/context-sky')
    def context_sky():
        objects={}
        for r in planet_rows():
            distance=r.get('sy_dist')
            if not distance or not np.isfinite(distance):continue
            ra,dec=np.deg2rad([r['ra'],r['dec']])
            objects[r['hostname']]=dict(id='host:'+r['hostname'],name=r['hostname'],ra=r['ra'],dec=r['dec'],
                distance_pc=distance,xyz_pc=[distance*np.cos(dec)*np.cos(ra),distance*np.cos(dec)*np.sin(ra),distance*np.sin(dec)],
                teff_gspphot=r.get('st_teff'),catalog='NASA Exoplanet Archive',provenance='catalog',phot_g_mean_mag=None)
        return dict(objects=list(objects.values()),note='Incomplete catalog of exoplanet host stars. Display point sizes adapted for visibility; not measured sky brightness. Photos are flat; 3D depth comes from catalog distances.')
