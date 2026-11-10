import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from backend.simbad_client import query_names
t,server=query_names(["Barnard's star","eps Indi B","WISEA J085510.74-071442.5","RW Aur","R Dra"],fields=['plx','plx_err','propermotions','otype'])
print(t.colnames,flush=True)
rows=[]
for r in t:
 rows.append({k:(None if getattr(r[k],'mask',False) else str(r[k])) for k in t.colnames})
Path('web/assets/target-system-records.json').write_text(json.dumps(dict(server=server,rows=rows),indent=2));print(rows,flush=True)
