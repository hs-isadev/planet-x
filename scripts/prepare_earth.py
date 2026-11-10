import sys,json,requests,gzip,xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from backend.archive import ROOT
D=ROOT/'web/assets';s=requests.Session();sources=json.loads((D/'sources.json').read_text())
def fetch(url,file):
 p=D/file
 if not p.exists():r=s.get(url,timeout=90);r.raise_for_status();p.write_bytes(r.content)
 return p
# Discover the actual HGT object in the documented AWS public terrain bucket.
r=s.get('https://elevation-tiles-prod.s3.amazonaws.com/',params={'list-type':'2','prefix':'skadi/N19/','max-keys':1000},timeout=40);r.raise_for_status();tree=ET.fromstring(r.content);keys=[e.text for e in tree.iter() if e.tag.endswith('}Key')];key=next(k for k in keys if k.endswith('N19W156.hgt.gz'));url='https://elevation-tiles-prod.s3.amazonaws.com/'+key
raw=gzip.decompress(fetch(url,'earth-hgt.gz').read_bytes());a=np.frombuffer(raw,dtype='>i2');side=int(np.sqrt(len(a)));a=a.reshape(side,side).astype(float);a[a==-32768]=np.nan
lat,lon=19.82,-155.47;span=6000;n=193;xx,zz=np.meshgrid(np.linspace(-span/2,span/2,n),np.linspace(-span/2,span/2,n));la=lat-zz/111320;lo=lon+xx/(111320*np.cos(np.deg2rad(lat)));heights=map_coordinates(a,[(20-la)*(side-1),(lo+156)*(side-1)],order=1,mode='nearest')
if not np.isfinite(heights).all():raise ValueError('Measured Earth terrain contains voids; refusing invented ground.')
(D/'surface-earth.json').write_text(json.dumps(dict(body='earth',name='Mauna Kea summit region',latitude=lat,longitude=lon,span_m=span,n=n,heights_m=heights.round(2).ravel().tolist(),source='Mapzen Terrain Tiles / SRTM-derived elevation, AWS Open Data',resolution_m=round(111320/(side-1)),temperature_note='Local weather and temperature are unavailable; no live value is invented.',note='Measured elevation. Rock color and astronaut equipment are illustrative; no current-weather simulation.')))
sources.append(dict(file='surface-earth.json',url=url,credit='Mapzen Terrain Tiles; SRTM and contributing national datasets; https://github.com/tilezen/joerd/blob/master/docs/attribution.md',type='observed elevation / computed resampling'))
(D/'sources.json').write_text(json.dumps(sources,indent=2));print('Earth terrain prepared',float(heights.min()),float(heights.max()),flush=True)
