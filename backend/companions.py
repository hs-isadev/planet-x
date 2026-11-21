"""Catalog orbit summaries for illustrative companion layouts, not ephemerides."""
import gzip
import json
from functools import lru_cache
import numpy as np
from .archive import ROOT

@lru_cache(maxsize=1)
def planet_rows():
    rows = json.loads((ROOT/'web/assets/exoplanet-orbits.json').read_text(encoding='utf-8'))['rows']
    path = ROOT/'backend/data/gaia-companion-hosts.json'
    additions = json.loads(path.read_text(encoding='utf-8'))['rows'] if path.is_file() else []
    return rows + additions

def planets_for(ra,dec,name=''):
    # High proper-motion hosts need a name match, not a broad angular match.
    normal=name.lower().strip().replace('’', "'")
    host={"barnard":"barnard's star", "barnard star":"barnard's star", "proxima centauri":"proxima cen", "alpha centauri c":"proxima cen", "v* proxima cen":"proxima cen"}.get(normal,normal)
    if normal.startswith('gaia dr3 '):
        rows=[r for r in planet_rows() if str(r.get('gaia_dr3_id','')).lower()==normal]
        # An unmatched Gaia ID must not inherit a nearby, unrelated host's planets.
        return [p for r in rows if (p:=orbit_parameters(r))]
    rows=[r for r in planet_rows() if r['hostname'].lower()==host]
    if not rows:
        cos=np.cos(np.deg2rad(dec))
        rows=[r for r in planet_rows() if abs(r['dec']-dec)<3/3600 and abs((r['ra']-ra+180)%360-180)*cos<3/3600]
    return [p for r in rows if (p:=orbit_parameters(r))]


def orbit_parameters(row):
    period = row.get('pl_orbper')
    a = row.get('pl_orbsmax')
    estimated = not a and bool(period and row.get('st_mass'))
    if estimated:
        a = (row['st_mass']*(period/365.25)**2)**(1/3)
    if not (a and period and a>0 and period>0):
        return None
    return dict(name=row['pl_name'],semimajor_au=a,period_days=period,
                radius_earth=row.get('pl_rade'),star_radius_solar=row.get('st_rad'),
                temperature_k=row.get('st_teff'),semimajor_estimated=estimated,
                provenance='catalog / computed',source='https://exoplanetarchive.ipac.caltech.edu/',
                note='Orbital scale estimated from catalog period and stellar mass using Kepler’s third law.'
                     if estimated else 'Orbital scale and period from the NASA Exoplanet Archive.')


@lru_cache(maxsize=1)
def teammate_gaia_stars():
    path = ROOT/'backend/data/gaia-teammate-stars.json.gz'
    if not path.exists():
        return []
    with gzip.open(path,'rt',encoding='utf8') as stream:
        rows = json.load(stream)['rows']
    result = []
    hosts = {r['gaia_dr3_id'].split()[-1]:r for r in planet_rows() if r.get('gaia_dr3_id')}
    for sid, ra, dec, distance, mag, color in rows:
        lon, lat = np.deg2rad([ra,dec])
        host = hosts.get(sid, {})
        aliases = {'Gaia DR3':sid}
        if host: aliases['NASA Exoplanet Archive'] = host['hostname']
        result.append(dict(id='gaia:'+sid,name='Gaia DR3 '+sid,ra=ra,dec=dec,distance_pc=distance,
            xyz_pc=[distance*np.cos(lat)*np.cos(lon),distance*np.cos(lat)*np.sin(lon),distance*np.sin(lat)],
            catalog='Gaia DR3',catalog_ids=aliases,teff_gspphot=host.get('st_teff'),provenance='catalog',
            ref_epoch=2016,phot_g_mean_mag=mag,bp_rp=color,expanded_catalog=True))
    return result


def install_companion_routes(app):
    from fastapi import Query
    @app.get('/api/companions')
    def companions(ra:float=Query(ge=0,lt=360),dec:float=Query(ge=-90,le=90),name:str=''):
        return dict(planets=planets_for(ra,dec,name),note='No catalog match means no known planetary orbit is installed; it does not mean the star has no planets.')

    @app.get('/api/context-sky')
    @lru_cache(maxsize=1)
    def context_sky():
        objects={}
        for r in planet_rows():
            distance=r.get('sy_dist')
            if not distance or not np.isfinite(distance):continue
            ra,dec=np.deg2rad([r['ra'],r['dec']])
            objects[r['hostname']]=dict(id='host:'+r['hostname'],name=r['hostname'],ra=r['ra'],dec=r['dec'],
                distance_pc=distance,xyz_pc=[distance*np.cos(dec)*np.cos(ra),distance*np.cos(dec)*np.sin(ra),distance*np.sin(dec)],
                teff_gspphot=r.get('st_teff'),catalog='NASA Exoplanet Archive',provenance='catalog',phot_g_mean_mag=None)
        expansion = json.loads((ROOT/'web/assets/expanded-stars.json').read_text(encoding='utf-8'))
        gaia = teammate_gaia_stars()
        from scipy.spatial import cKDTree
        existing = list(objects.values()) + expansion['objects'] + gaia
        bright = json.loads((ROOT/'web/assets/sky/bright-distances.json').read_text(encoding='utf-8'))
        positions = np.array([row['xyz_pc'] for row in existing])
        positions /= np.linalg.norm(positions, axis=1)[:, None]
        tree = cKDTree(positions)
        additions = []
        for hr, name, ra, dec, distance, mag, constellation, designation in bright['rows']:
            lon, lat = np.deg2rad([ra, dec])
            unit = np.array([np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)])
            separation, index = tree.query(unit)
            if separation < np.deg2rad(30/3600):
                row = existing[index]
                row['catalog_ids'] = {**row.get('catalog_ids', {}), 'HR': str(hr), 'BSC name': name}
                continue
            additions.append(dict(id=f'hr:{hr}', name=name, ra=ra, dec=dec, distance_pc=distance,
                xyz_pc=(distance*unit).tolist(), v_mag=mag, constellation=constellation,
                catalog='Yale Bright Star / BSC5P', catalog_ids={'HR':str(hr), 'designation':designation},
                provenance='catalog', expanded_catalog=True, description=bright['attribution']))
        return dict(objects=existing+additions, added_stars=expansion['count']+len(gaia)+len(additions),
            bright_star_count=len(additions), bright_star_sources=bright['sources'], teammate_gaia_count=len(gaia),
            sources=['Gaia DR3 via NOIRLab Astro Data Lab','NASA Exoplanet Archive', 'Hipparcos / HYG 4.1', 'Yale Bright Star / HYG 4.1', 'Gliese / HYG 4.1'],
            attribution=expansion['attribution'], license=expansion['license'],
            note='Incomplete mixed catalog: exoplanet hosts, HYG stars, and the teammate Gaia DR3 sample. HYG epoch J2000.0; catalog memberships overlap. Display point sizes adapted for visibility; V magnitude is not Gaia G. Catalog distances have no new uncertainty estimate. Photos are flat; depth comes from catalog distances.')
