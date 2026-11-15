import sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import backend
from astroquery.simbad import Simbad
try:
 s=Simbad();s.TIMEOUT=20;print(s.query_objects(["Barnard's Star","eps Indi B","RW Aur","R Dra"]),flush=True)
except Exception:traceback.print_exc()
