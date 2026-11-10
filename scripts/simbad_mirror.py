import sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
from astroquery.simbad import Simbad
for server in ['simbad.harvard.edu']:
 try:
  s=Simbad();s.server=server;s.TIMEOUT=15
  original=s._session.request
  def bounded(*a,**kw):kw.setdefault('timeout',15);return original(*a,**kw)
  s._session.request=bounded
  t=s.query_objects(["Barnard's Star","eps Indi B","RW Aur","R Dra","WISE J085510.83-071442.5"])
  print(t,flush=True);print(t.colnames,flush=True)
  if t is not None:t.write(Path(__file__).resolve().parents[1]/'docs/simbad-presets.ecsv',overwrite=True)
 except Exception:traceback.print_exc()
