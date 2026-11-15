"""Computed metric Solar System positions, never image-derived depths."""
from functools import lru_cache
import warnings
import numpy as np
import astropy.units as u
from astropy.time import Time
from astropy.coordinates import get_body_barycentric, get_body
from fastapi import HTTPException
from .archive import ROOT
import json
# Mean radii and sidereal orbital periods: JPL Planetary Physical Parameters.
BODIES=[
 ('sun','Sun','G-type star',695700,0,'Our star, at the center of this heliocentric view.'),
 ('mercury','Mercury','Terrestrial planet',2439.4,.2408467,'The innermost planet. Its mapped surface is heavily cratered.'),
 ('venus','Venus','Terrestrial planet',6051.8,.61519726,'A rocky planet hidden beneath a dense atmosphere.'),
 ('earth','Earth','Terrestrial planet',6371.0084,1.0000174,'Our home world. The globe uses NASA’s Blue Marble satellite composite.'),
 ('mars','Mars','Terrestrial planet',3389.5,1.8808476,'A rocky world. The surface mosaic comes from NASA’s Viking mission.'),
 ('jupiter','Jupiter','Gas giant',69911,11.862615,'The largest planet. Its cloud map was observed by Cassini in December 2000.'),
 ('saturn','Saturn','Gas giant',58232,29.447498,'A gas giant surrounded by a broad system of icy rings.'),
 ('uranus','Uranus','Ice giant',25362,84.016846,'An ice giant in the outer Solar System.'),
 ('neptune','Neptune','Ice giant',24622,164.79132,'The most distant of the eight known planets.'),
]
EPS=np.deg2rad(23.439291111)
def ecliptic(xyz):
    a=np.asarray(xyz,dtype=float)
    return np.stack([a[0],np.cos(EPS)*a[1]+np.sin(EPS)*a[2],-np.sin(EPS)*a[1]+np.cos(EPS)*a[2]],axis=-1)

@lru_cache(maxsize=96)
def solar_snapshot(date):
    try:
        t=Time(date+'T00:00:00',scale='utc')
        if not 1900<=t.datetime.year<=2100:raise ValueError()
    except Exception:raise ValueError('Choose a valid UTC date from 1900 through 2100.')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        sun=get_body_barycentric('sun',t,ephemeris='builtin')
        result=[]
        for key,name,kind,radius,period,description in BODIES:
            xyz=(get_body_barycentric(key,t,ephemeris='builtin')-sun).xyz.to_value(u.au)
            row=dict(id=key,name=name,kind=kind,radius_km=radius,xyz_au=ecliptic(xyz).tolist(),distance_sun_au=float(np.linalg.norm(xyz)),description=description,provenance='computed',position_source='Astropy builtin ERFA epv00/plan94',texture=None,texture_note='No verified surface map installed. Neutral untextured geometry; no invented surface detail.')
            row['orbital_period_days']=round(period*365.25,2) if period else None
            if key=='sun':row['effective_temperature_k']=5772
            if (ROOT/'web/assets'/f'surface-{key}.json').exists():row['surface']=f'/assets/surface-{key}.json'
            if key!='earth':
                apparent=get_body(key,t,ephemeris='builtin').icrs
                # get_body returns geocentric GCRS. Read RA/Dec there, not a barycentric ICRS transform.
                apparent=get_body(key,t,ephemeris='builtin')
                row.update(ra=float(apparent.ra.deg),dec=float(apparent.dec.deg),sky_coordinate_frame='Geocentric apparent GCRS; not a fixed distant-source ICRS position')
            if (ROOT/'web/assets'/f'{key}.glb').exists():
                row.update(model=f'/assets/{key}.glb',texture_note='NASA VTAD illustrative appearance model (computed); not an observed surface measurement or current photograph.')
            if period:
                times=t+np.linspace(-period*365.25/2,period*365.25/2,257)*u.day
                orbit=(get_body_barycentric(key,times,ephemeris='builtin')-get_body_barycentric('sun',times,ephemeris='builtin')).xyz.to_value(u.au)
                row['orbit_au']=ecliptic(orbit).tolist()
            for extension in ('png','jpg'):
                if (ROOT/'web/assets'/f'{key}.{extension}').exists():
                    row['texture']=f'/assets/{key}.{extension}'
                    row['texture_note']={'earth':'Observed NASA Blue Marble composite (2001 surface observations). Historical map, not current weather.','mars':'Observed NASA/JPL/USGS Viking mosaic.','mercury':('NASA/JHUAPL/Carnegie/USGS MESSENGER global three-band visualization mosaic; historical observed source.' if (ROOT/'web/assets/mercury-map.json').exists() else 'Observed NASA/JPL/USGS Mariner 10 partial map. Dark unmapped regions are missing data.'),'jupiter':'Observed NASA/JPL/Space Science Institute Cassini cylindrical mosaic, December 2000. Historical clouds.'}.get(key,'NASA imagery-derived visualization map; not a current observation.')
            result.append(row)
    return dict(date=date+'T00:00:00Z',objects=result,units='AU',frame='Heliocentric mean ecliptic and equinox J2000; simultaneous geometric positions',provenance='computed',notes=['Centers and orbit curves use Astropy builtin ERFA epv00/plan94 approximations; this is an educational ephemeris, not navigation-grade.','All center-to-center distances are linear and to scale. Display radii are enlarged; physical mean radii are shown in the inspector.','Globe orientation is illustrative; surface longitude, spin, limb shape and ring orientation are not ephemeris solutions.','Planet surface maps are historical observations reprojected onto computed spheres. They are separate from observed SPHEREx images.','No Planet X position is known; no hypothetical planet is inserted.','Nearby stars use a separate parsec-scale catalog view. Solar System AU and stellar distances are never compressed into one misleading scale.'])

def install_solar_routes(app):
    @app.get('/api/solar')
    def solar(date:str=''):
        from datetime import datetime,timezone
        if not date:date=datetime.now(timezone.utc).date().isoformat()
        try:return solar_snapshot(date)
        except ValueError as exc:raise HTTPException(422,str(exc))
