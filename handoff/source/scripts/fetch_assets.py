import sys,json,requests
from pathlib import Path
from urllib.parse import urljoin
from html.parser import HTMLParser
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'web/assets';OUT.mkdir(parents=True,exist_ok=True)
class Links(HTMLParser):
    def __init__(self):super().__init__();self.links=[]
    def handle_starttag(self,tag,attrs):
        for k,v in attrs:
            if k in ('href','src') and v:self.links.append(v)
s=requests.Session()
assets=[('earth.png','https://svs.gsfc.nasa.gov/vis/a000000/a002900/a002915/bluemarble-2048.png','NASA/Goddard SVS; Reto Stockli; Blue Marble composite; not current clouds'),('mars.jpg','https://space.jpl.nasa.gov/tmaps/pix/mar0kuu2.jpg','NASA/JPL/USGS Viking mosaic'),('mercury.jpg','https://space.jpl.nasa.gov/tmaps/pix/mer0muu2.jpg','NASA/JPL/USGS Mariner 10 partial mosaic; black areas are unmapped')]
for name,url,credit in assets:
    try:
        r=s.get(url,timeout=30);r.raise_for_status();(OUT/name).write_bytes(r.content);print(name,len(r.content),flush=True)
    except Exception as e:print(name,str(e),flush=True)
# Discover rather than guess the NASA page's linked data products.
for body,url in [('jupiter','https://science.nasa.gov/photojournal/cassinis-best-maps-of-jupiter-cylindrical-map/'),('saturn','https://science.nasa.gov/resource/saturn-3d-model/'),('neptune','https://science.nasa.gov/resource/neptune-3d-model/'),('uranus','https://science.nasa.gov/resource/uranus-3d-model/'),('venus','https://science.nasa.gov/resource/venus-3d-model/')]:
    try:
        r=s.get(url,timeout=30);r.raise_for_status();p=Links();p.feed(r.text)
        found=list(dict.fromkeys(urljoin(url,v) for v in p.links if any(ext in v.lower() for ext in ('.glb','.gltf','.jpg','.zip')) and ('assets.science.nasa.gov' in v or 'photojournal' in v)))
        (OUT/(body+'-links.json')).write_text(json.dumps(found,indent=2));print(body,found,flush=True)
    except Exception as e:print(body,str(e),flush=True)
(OUT/'sources.json').write_text(json.dumps([dict(file=n,url=u,credit=c) for n,u,c in assets],indent=2))
