import requests,json
from pathlib import Path
from PIL import Image
D=Path(__file__).resolve().parents[1]/'web/assets'
u='https://planetarydata.jpl.nasa.gov/img/data/test/messenger/MDIS_MAPS/EXTRAS/BROWSE/Mercury_MESSENGER_MDIS_Basemap_MD3Color_Mosaic_Global_665m.jpg'
r=requests.get(u,timeout=50);r.raise_for_status();(D/'mercury-messenger-source.jpg').write_bytes(r.content)
im=Image.open(D/'mercury-messenger-source.jpg');im.thumbnail((4096,2048));im.save(D/'mercury.jpg',quality=94)
(D/'mercury-map.json').write_text(json.dumps(dict(url=u,credit='NASA/JHUAPL/Carnegie/USGS MESSENGER MDIS global color mosaic; three-band visualization, not current weather')))
print('Global MESSENGER Mercury map installed',im.size,flush=True)
