import json,requests,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=R/'web/assets';s=requests.Session()
sources=json.loads((D/'sources.json').read_text())
for name in ['saturn','neptune','uranus','venus']:
    urls=json.loads((D/(name+'-links.json')).read_text());url=next(x for x in urls if '.glb' in x.lower())
    r=s.get(url,timeout=40);r.raise_for_status();(D/(name+'.glb')).write_bytes(r.content)
    sources.append(dict(file=name+'.glb',url=url,credit='NASA Visualization Technology Applications and Development (VTAD)',type='computed appearance model; not observed SPHEREx data'))
    print(name,len(r.content),flush=True)
urls=json.loads((D/'jupiter-links.json').read_text());print([x for x in urls if '07782' in x],flush=True)
url=next(x for x in urls if '07782' in x and '.jpg' in x.lower() and 'dynamicimage' not in x)
r=s.get(url,timeout=40);r.raise_for_status();(D/'jupiter-source.jpg').write_bytes(r.content)
from PIL import Image
im=Image.open(D/'jupiter-source.jpg');print('Jupiter dimensions',im.size,flush=True)
# PIA07782 JPEG is the no-grid, full 360x180 cylindrical map linked by NASA.
im.save(D/'jupiter.jpg',quality=94)
sources.append(dict(file='jupiter.jpg',url=url,credit='NASA/JPL/Space Science Institute, Cassini ISS, PIA07782, 2000-12-11/12',type='observed historical cylindrical composite'))
(D/'sources.json').write_text(json.dumps(sources,indent=2))
