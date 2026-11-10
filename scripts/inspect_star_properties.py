import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import backend
from backend.catalogs import tap_query,number
from backend.archive import CONFIG,ROOT
q="SELECT TOP 1001 source_id,teff_gspphot,teff_gspphot_lower,teff_gspphot_upper,logg_gspphot,bp_rp FROM gaiadr3.gaia_source WHERE parallax>=40 AND parallax_over_error>=5 ORDER BY parallax DESC"
t=tap_query(CONFIG['gaia_tap_endpoint'],q,1001)
rows={str(r['source_id']):{k:number(r[k]) for k in t.colnames if k!='source_id'} for r in t}
(ROOT/'cache/stellar-properties.json').write_text(json.dumps(rows));(ROOT/'web/assets/stellar-properties.json').write_text(json.dumps(rows));print('Property records',len(rows),'temperatures',sum(r['teff_gspphot'] is not None for r in rows.values()),flush=True)
