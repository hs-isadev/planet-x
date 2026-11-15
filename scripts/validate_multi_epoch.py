"""Compare actual loaded epochs. Residual incidence here is not a ground-truth false-positive rate."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.archive import CACHE,key_for
from backend.analysis import load_products
from backend.quicklook import change_masks
browser=json.loads(Path('docs/pipeline-browser.json').read_text(encoding='utf8'))['targets']
reviews=json.loads(Path('docs/pipeline-five-laya.json').read_text(encoding='utf8'))['targets']
results=[]
for target,review in zip(browser,reviews):
    receipt=json.loads((CACHE/(review['review_id']+'.json')).read_text(encoding='utf8'))
    if not receipt.get('exposures'):
        raise RuntimeError('Review coverage has not been saved yet for '+target['name']+'. Run after the review reaches a saved checkpoint.')
    frames={f['id']:f for f in receipt['exposures']}
    pairs=set();stats=[]
    for batch in receipt['batches']:
        ids=tuple(batch['exposure_ids'])
        if ids in pairs:continue
        pairs.add(ids)
        a,b=(frames[i] for i in ids)
        keys=[key_for(f"{f['url']}|{target['ra']}|{target['dec']}|8.0|native-analysis-v2") for f in (a,b)]
        if not all((CACHE/(k+'.npz')).exists() for k in keys):continue
        x,y=(load_products({'cache_id':k}) for k in keys)
        masks=change_masks(y,x)
        stats.append(dict(exposure_ids=list(ids),dates=[a['date'],b['date']],detector=a['detector'],
            source_urls=[a['url'],b['url']],eligible_pixels=int(masks['comparable'].sum()),
            red_pixels=int(masks['red'].sum()),appearance_pixels=int(masks['appearance'].sum()),
            disappearance_pixels=int(masks['disappearance'].sum()),assessment='uncertain'))
    results.append(dict(target=target['name'],pairs=stats))
report=dict(targets=results,scope='Real multi-epoch provisional WCS-WAVE comparisons with common masked pixels. Stellar variability, PSF changes and astrometric offsets are not independently resolved. Do not infer an astronomical false-positive rate from these flags.')
Path('docs/pipeline-multi-epoch.json').write_text(json.dumps(report,indent=2),encoding='utf8')
for r in results:
    print(r['target'].encode('ascii','replace').decode(),len(r['pairs']),sum(p['red_pixels'] for p in r['pairs']),sum(p['eligible_pixels'] for p in r['pairs']))
