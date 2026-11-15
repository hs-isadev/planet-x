"""Save a bounded selection of real observations for the teammate Lab."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from backend.observation_lab_core.archive import download, query_sia, reduction_priority, write_json
from backend.observation_lab_core.server import CACHE, CONFIG, FEATURED, LIBRARY


def select_rows(field, rows, maximum):
    detector = field['frames'][0]['detector']
    installed = {f['id']:reduction_priority(f)[0] for f in field['frames']}
    rows = [r for r in rows if r['detector']==detector and
            reduction_priority(r)[0] > installed.get(r['id'],-1)]
    rows.sort(key=lambda r:(r['mjd'],r['id']))
    if len(rows) <= maximum:
        return rows
    return [rows[round(i*(len(rows)-1)/max(maximum-1,1))] for i in range(maximum)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--per-field',type=int,default=4,choices=range(1,41))
    parser.add_argument('--field',action='append',help='Use a quick-start field key. Default is all fixed fields.')
    args=parser.parse_args()
    fields=[f for f in LIBRARY['fields'] if f['key']!='vesta' and (not args.field or f['key'] in args.field)]
    if not fields:
        parser.error('Select at least one fixed field. The moving Vesta field is curated by epoch.')
    import json
    existing=json.loads(FEATURED.read_text(encoding='utf-8'))['records'] if FEATURED.is_file() else []
    records={(r['field_key'],r['id'],r['detector']):r for r in existing}
    for field in fields:
        try:
            rows=query_sia(CONFIG,field['ra'],field['dec'],.001,timeout=(7,24))
        except Exception as exc:
            print(f"{field['name']}: discovery unavailable ({exc})",flush=True)
            continue
        picked=select_rows(field,rows,args.per_field)

        def fetch(row):
            return download(dict(row,field_key=field['key'],field_name=field['name']),field['ra'],field['dec'],10,CACHE)

        def one(row):
            try:
                return fetch(row),None
            except Exception as exc:
                return None,f"{row['id']}: {type(exc).__name__}: {exc}"

        saved=0
        with ThreadPoolExecutor(3) as pool:
            for item, error in pool.map(one,picked):
                if error:
                    print(error,flush=True)
                    continue
                key=(field['key'],item['id'],item['detector'])
                if key not in records or reduction_priority(item)>=reduction_priority(records[key]):
                    records[key]=item
                    saved+=1
                    write_json(FEATURED,{'records':list(records.values())})
        print(f"{field['name']}: {saved}/{len(picked)} verified cutouts saved",flush=True)


if __name__=='__main__':
    main()
