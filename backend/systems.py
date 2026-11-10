import json
from fastapi import HTTPException
from .archive import ROOT,CACHE
from .catalogs import number
from .space import distance_record
LABELS=[('barnard',"Barnard’s Star",'Red dwarf; high proper motion.'),('epsilon','Epsilon Indi B','Brown-dwarf binary associated with Epsilon Indi.'),('wise','WISE 0855','Cold nearby brown dwarf.'),('rw','RW Aurigae','Young variable stellar system.'),('rdraconis','R Draconis','Mira variable star.')]
def target_systems():
    file=ROOT/'web/assets/target-system-records.json'
    records=json.loads(file.read_text()) if file.exists() else {'rows':[],'server':'unavailable'}
    presets=json.loads((CACHE/'presets.json').read_text()) if (CACHE/'presets.json').exists() else []
    known=[];unknown=[];targets=[]
    for index,(id,name,description) in enumerate(LABELS):
        row=records['rows'][index] if len(records['rows'])>index else {}
        p=next((p for p in presets if p['id']==id),{})
        ra=number(row.get('ra'));dec=number(row.get('dec'))
        if ra is None:ra=p.get('ra');dec=p.get('dec')
        if ra is None:targets.append(dict(id=id,name=name,description=description,distance_note='Catalog coordinates unavailable.'));continue
        source=dict(id=id,name=name,description=description+' System location only; no measured companion orbit is installed.',ra=ra,dec=dec,parallax=number(row.get('plx_value')),parallax_error=number(row.get('plx_err')),catalog='SIMBAD',ref_epoch=2000.,pmra=number(row.get('pmra')),pmdec=number(row.get('pmdec')),source='https://'+records['server'],object_type=row.get('otype'))
        r=distance_record(source)
        from .companions import planets_for
        r['planets']=planets_for(ra,dec,name)
        if r['planets']:r['teff_gspphot']=r['planets'][0].get('temperature_k')
        targets.append(r)
        (known if r['distance_pc'] is not None else unknown).append(r)
    return dict(targets=targets,objects=known,unknown=unknown,scope='systems',notes=['Each entry is an independent named target; none is assigned to Proxima Centauri.','Depth is supplied only for reliable catalog parallax. No invented companion positions or orbit elements.'],truncated=False)
def install_system_routes(app):
    @app.get('/api/target-systems')
    def systems():return target_systems()
