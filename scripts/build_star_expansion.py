"""Rebuild a 240-star HYG subset with preserved catalog cross-identifications."""
import csv, hashlib, json, math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'runtime/hygdata_v41.csv'
rows=list(csv.DictReader(source.open(encoding='utf-8')))
hosts=json.loads((ROOT/'web/assets/exoplanet-orbits.json').read_text())['rows']
def vector(ra,dec):
 a,d=math.radians(ra),math.radians(dec)
 return [math.cos(d)*math.cos(a),math.cos(d)*math.sin(a),math.sin(d)]
known=[vector(r['ra'],r['dec']) for r in {r['hostname']:r for r in hosts}.values()]
def normal(s):return s.lower().replace(' ', '').replace('’', chr(39)).replace('centauri','cen')
known_names={normal(r['hostname']) for r in hosts}
chosen=[]; used=set(); buckets={}
for membership,key in [('Gliese Nearby Stars','gl'),('Yale Bright Star Catalog','hr'),('Hipparcos','hip')]:
 candidates=[r for r in rows if r[key] and 0<float(r['dist'])<100000 and r['id'] not in used]
 candidates.sort(key=lambda r: (float(r['dist']) if key=='gl' else float(r['mag']),r['id']))
 added=0
 for r in candidates:
  if r['proper'] and normal(r['proper']) in known_names:continue
  ra=float(r['ra'])*15; dec=float(r['dec']);v=vector(ra,dec)
  if any(sum(a*b for a,b in zip(v,k))>math.cos(math.radians(30/3600)) for k in known):continue
  cell=(int(ra/30),int((dec+90)/30))
  if buckets.get(cell,0)>=6:continue
  buckets[cell]=buckets.get(cell,0)+1
  distance=float(r['dist']);name=r['proper'] or r['bf'] or ('Gliese '+r['gl'] if r['gl'] else 'HIP '+r['hip'])
  chosen.append(dict(id='hyg:'+r['id'],name=name,ra=ra,dec=dec,distance_pc=distance,
   xyz_pc=[distance*x for x in v],catalog=membership+' / HYG 4.1',catalog_group=membership,
   catalog_ids={k:r[k] for k in ('hip','hd','hr','gl') if r[k]},epoch=2000.0,
   v_mag=float(r['mag']),phot_g_mean_mag=None,teff_gspphot=None,spectral_type=r['spect'],
   source_url='https://github.com/astronexus/HYG-Database/blob/main/hyg/README.md',
   provenance='catalog',expanded_catalog=True,
   description='HYG 4.1 compiled catalog position at epoch/equinox J2000.0. Visual magnitude is V, not Gaia G. Catalog distance has no uncertainty supplied in this subset; surface appearance is illustrative.'))
  used.add(r['id']);known.append(v);added+=1
  if added==80:break
 if added!=80:raise RuntimeError('Insufficient unique catalog rows: '+membership)
result=dict(version='HYG 4.1 subset',count=len(chosen),license='CC BY-SA 4.0',
 attribution='David Nash / Astronexus HYG database; Hipparcos, Yale Bright Star and Gliese input catalogs.',
 source='https://raw.githubusercontent.com/astronexus/HYG-Database/main/hyg/CURRENT/hygdata_v41.csv',
 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),epoch=2000.0,
 selection='80 records with Gliese identifiers, 80 additional Yale/HR records, 80 additional Hipparcos records. Membership is not independent measurement provenance; catalogs overlap. Distance sentinels excluded. Duplicate directions within 30 arcsec of installed exoplanet hosts or accepted rows omitted. At most 6 additions per 30-degree RA/Dec bin.',objects=chosen)
(ROOT/'web/assets/expanded-stars.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'added':len(chosen),'groups':{g:sum(r['catalog_group']==g for r in chosen) for g in sorted({r['catalog_group'] for r in chosen})}}))
