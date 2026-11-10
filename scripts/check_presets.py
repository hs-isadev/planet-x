import sys,traceback,numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from backend.simbad_client import query_names
from backend.main import PRESETS,presets
try:
 names=[p['simbad'] for p in PRESETS if 'simbad' in p];t,server=query_names(names)
 print(server,repr(np.asarray(t['user_specified_id']).astype(str)),flush=True)
 for p in PRESETS:
  if 'simbad' in p:
   m=t[np.asarray(t['user_specified_id']).astype(str)==p['simbad']];print(p['simbad'],len(m),repr(m),flush=True)
except Exception:traceback.print_exc()
print(presets(),flush=True)
