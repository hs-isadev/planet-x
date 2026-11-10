import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from backend.catalogs import tap_query,number
endpoint='https://exoplanetarchive.ipac.caltech.edu/TAP'
schema=tap_query(endpoint,"SELECT column_name FROM TAP_SCHEMA.columns WHERE table_name='pscomppars'",3000)
names={str(r['column_name']).strip() for r in schema}
cols=['pl_name','hostname','ra','dec','pl_orbper','pl_orbsmax','pl_rade','st_rad','st_teff','sy_dist']
assert set(cols)<=names,(set(cols)-names)
table=tap_query(endpoint,'SELECT '+','.join(cols)+' FROM pscomppars WHERE pl_orbsmax IS NOT NULL AND pl_orbper IS NOT NULL',10000)
rows=[{k:(str(r[k]) if k in ['pl_name','hostname'] else number(r[k])) for k in cols} for r in table]
Path('web/assets/exoplanet-orbits.json').write_text(json.dumps(dict(source=endpoint,table='pscomppars',columns=cols,rows=rows),indent=2))
print('Real catalog orbit records',len(rows),flush=True)
