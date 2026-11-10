import sys,json,re,gzip,requests
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from backend.archive import ROOT
D=ROOT/'web/assets';s=requests.Session()
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[]
 def handle_starttag(self,tag,attrs):
  for k,v in attrs:
   if k in ('href','src') and v:self.links.append(v)
try:
 url='https://svs.gsfc.nasa.gov/4720';r=s.get(url,timeout=40);r.raise_for_status();p=Links();p.feed(r.text)
 links=list(dict.fromkeys(urljoin(url,x) for x in p.links if any(k in x.lower() for k in ['lroc_color','ldem_','lroc_cgi'])))
 (D/'moon-data-links.json').write_text(json.dumps(links,indent=2));print('MOON_LINKS',json.dumps(links),flush=True)
except Exception as e:print('MOON_ERROR',str(e),flush=True)
