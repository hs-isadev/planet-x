"""Location-specific terrain from the documented Mapzen public HGT collection."""
import math,gzip,json,threading
import requests
import numpy as np
from scipy.ndimage import map_coordinates
from PIL import Image
from fastapi import HTTPException,Query
from .archive import ROOT,CACHE,atomic_json,key_for
LOCK=threading.Lock()
ORIGIN='https://elevation-tiles-prod.s3.amazonaws.com/'
def tile(lat,lon):
    name=f'{"N" if lat>=0 else "S"}{abs(lat):02d}{"E" if lon>=0 else "W"}{abs(lon):03d}'
    file=CACHE/('mapzen-'+name+'.hgt.gz')
    if not file.exists():
        import xml.etree.ElementTree as ET
        prefix='skadi/'+name[:3]+'/'
        r=requests.get(ORIGIN,params={'list-type':'2','prefix':prefix,'max-keys':1000},timeout=18);r.raise_for_status()
        keys=[e.text for e in ET.fromstring(r.content).iter() if e.tag.endswith('}Key')]
        match=next((k for k in keys if k.endswith('/'+name+'.hgt.gz')),None)
        if not match:raise ValueError('The elevation archive has no tile at this location.')
        r=requests.get(ORIGIN+match,timeout=25);r.raise_for_status();raw=gzip.decompress(r.content)
        size=int(math.sqrt(len(raw)//2))
        if size*size*2!=len(raw):raise ValueError('Invalid elevation tile.')
        file.write_bytes(r.content)
        for old in sorted(CACHE.glob('mapzen-*.hgt.gz'),key=lambda p:p.stat().st_mtime,reverse=True)[16:]:old.unlink(missing_ok=True)
    raw=gzip.decompress(file.read_bytes());a=np.frombuffer(raw,dtype='>i2');n=int(math.sqrt(a.size));a=a.reshape(n,n).astype(float);a[a==-32768]=np.nan
    return a,111320/(n-1)
def patch(lat,lon):
    cache=CACHE/('terrain-'+key_for(f'{lat:.4f}|{lon:.4f}|1500')+'.json')
    if cache.exists():return json.loads(cache.read_text())
    # A historical map supplies broad color context only, not meter-scale imagery.
    im=Image.open(ROOT/'web/assets/earth.png').convert('RGB');rgb=im.getpixel((min(im.width-1,int((lon+180)/360*im.width)),min(im.height-1,int((90-lat)/180*im.height))))
    water=rgb[2]>rgb[0]*1.4 and rgb[2]>rgb[1]*1.1
    span=1500;n=129;x,z=np.meshgrid(np.linspace(-span/2,span/2,n),np.linspace(-span/2,span/2,n))
    la=lat-z/111320;lo=lon+x/(111320*max(.03,math.cos(math.radians(lat))))
    lo=(lo+180)%360-180;heights=np.full((n,n),np.nan);resolution=31.
    if water:
        heights[:]=0
        source='Computed mean sea-level surface; water inferred from historical NASA Blue Marble color, not bathymetry'
    else:
        for ilat in np.unique(np.floor(la).astype(int)):
            for ilon in np.unique(np.floor(lo).astype(int)):
                selected=(np.floor(la)==ilat)&(np.floor(lo)==ilon)
                if not selected.any():continue
                a,resolution=tile(int(ilat),int(ilon));side=a.shape[0]
                heights[selected]=map_coordinates(a,[(ilat+1-la[selected])*(side-1),(lo[selected]-ilon)*(side-1)],order=1,mode='nearest')
        if not np.isfinite(heights).all():raise ValueError('This terrain patch contains elevation voids. No unrelated landing site was substituted.')
        source='Mapzen Terrain Tiles compiled elevation / USGS, SRTM and contributors'
    result=dict(body='earth',name=f'Landing {lat:.4f}°, {lon:.4f}°',latitude=lat,longitude=lon,span_m=span,n=n,heights_m=heights.round(2).ravel().tolist(),source=source,resolution_m=round(resolution),context_rgb=rgb,water=water,temperature_note='No current local temperature or weather data loaded.',note='Location follows the displayed globe coordinates; globe rotation is illustrative. '+('Sea-level hover simulation; no walkable ground or seabed inferred.' if water else 'Measured relief. Ground microtexture, lighting and astronaut are illustrative, not observed local imagery.'))
    atomic_json(cache,result);return result
def install_terrain_routes(app):
    @app.get('/api/terrain/earth')
    def terrain(lat:float=Query(ge=-85,le=85),lon:float=Query(ge=-180,le=180)):
        try:
            with LOCK:return patch(lat,lon)
        except Exception as e:raise HTTPException(503,'Terrain unavailable for this exact location: '+str(e))
