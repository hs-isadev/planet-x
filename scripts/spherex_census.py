"""Read-only SPHEREx discovery census: per-provider/collection counts and NEW UTC dates vs the saved set.
Run from repo root: .venv/Scripts/python.exe -X utf8 scripts/spherex_census.py [target ...]"""
import json, math, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.observation_lab_core import archive as A
from backend.observation_lab_core.featured_views import fields, view_entry, field_inventory, MOTION_EXAMPLES

CFG = json.loads((ROOT / 'backend/observation_lab_core/archive-config.json').read_text())
AWS = json.loads((ROOT / 'backend/config.json').read_text())['cloud_origin']
TARGETS = ['wise-0855', 'barnard', 'epsilon-indi', 'rw-aur', 'r-dra']
RADIUS = .001  # deg, the app's SIA default; fields are 10 arcmin so proper motion (arcsec) is irrelevant
HEAD_MAX = 30
UA = {'User-Agent': 'parallax-census/1'}


def day(mjd): return math.floor(mjd)
def utc(d): return (datetime(1858, 11, 17, tzinfo=timezone.utc) + timedelta(days=d)).strftime('%Y-%m-%d')
def mirror_url(src): return AWS + src.split('/ibe/data/spherex/', 1)[1] if '/ibe/data/spherex/' in src else None


def probe(provider, collection, fn):
    t = time.time(); out = dict(provider=provider, collection=collection)
    try:
        rows = fn()
        out.update(status='ok', rows=len(rows))
    except Exception as e:  # a failure is a result, not a crash
        rows = []
        r = getattr(e, 'response', None)
        out.update(status=f'HTTP {r.status_code}' if r is not None else type(e).__name__, rows=0, error=str(e)[:300])
    out['seconds'] = round(time.time() - t, 1)
    return out, rows


def run_query(args, tries=3):
    for i in range(tries):  # few retries with backoff
        out, rows = probe(*args)
        if out['status'] == 'ok' or i == tries - 1:
            return out, rows
        time.sleep(4 * (i + 1))


def census(field):
    ra, dec = field['ra'], field['dec']
    providers, pool = [], {}
    for coll in CFG['collections']:
        cfg = dict(CFG, collections=[coll])
        for name, fn in (('SIA', lambda: A.query_sia(cfg, ra, dec, RADIUS, timeout=(10, 60))),
                         ('TAP', lambda: A.query_tap(cfg, ra, dec))):
            if name == 'TAP' and coll.endswith('_deep'):
                continue  # query_tap has no ADQL collection filter; it parses the release from the URI, so deep is covered by SIA only
            out, rows = run_query((name, coll, fn))
            providers.append(out)
            for r in rows:
                r['collection'] = r.get('collection', coll)
                k = r['id'], r['detector']
                if k not in pool or A.reduction_priority(r) > A.reduction_priority(pool[k]):
                    pool[k] = r
            time.sleep(1)
    arch = sorted(pool.values(), key=lambda r: (r['mjd'], r['detector']))
    base, entry = view_entry(field['key'])
    frames = json.loads((base / entry['session'] / 'manifest.json').read_text())['frames'] if entry else []
    saved = {(f['id'], f['detector']) for f in frames}
    inv = field_inventory(field)
    known = {(r['id'], r['detector']) for r in inv}
    saved_days = {day(f['mjd']) for f in frames}
    known_days = {day(r['mjd']) for r in inv}
    arch_days = {day(r['mjd']) for r in arch}
    new_rows = [r for r in arch if (r['id'], r['detector']) not in saved]
    new_days = sorted(arch_days - saved_days)
    cand = {}
    for r in arch:
        if day(r['mjd']) in new_days:
            cand.setdefault(day(r['mjd']), []).append(dict(
                id=r['id'], detector=r['detector'], mjd=r['mjd'], utc_date=utc(day(r['mjd'])), release=r['release'],
                collection=r['collection'], irsa_url=r['source'], aws_url=mirror_url(r['source'])))
    picks = [v[0] for v in cand.values()]  # one exposure per new date, spread to at most HEAD_MAX
    if len(picks) > HEAD_MAX:
        picks = [picks[round(i * (len(picks) - 1) / (HEAD_MAX - 1))] for i in range(HEAD_MAX)]
    heads = 0
    for c in picks:
        try:
            r = requests.head(c['aws_url'], timeout=15, headers=UA, allow_redirects=True) if c['aws_url'] else None
            c['aws_head'] = r.status_code if r is not None else 'no-url'
            c['aws_bytes'] = int(r.headers.get('Content-Length', 0)) if r is not None else None
        except requests.RequestException as e:
            c['aws_head'] = type(e).__name__
        heads += c['aws_head'] == 200
        time.sleep(.2)
    ex = json.loads(MOTION_EXAMPLES.read_text()).get(field['key'], {})
    mdet = sorted({p['detector'] for p in ex.get('points', [])})
    fr = lambda s: (utc(min(s)), utc(max(s))) if s else (None, None)
    return dict(key=field['key'], name=field['name'], ra=ra, dec=dec, providers=providers,
        archive=dict(exposures=len(arch), dates=len(arch_days), first=fr(arch_days)[0], last=fr(arch_days)[1]),
        saved=dict(exposures=len(saved), dates=len(saved_days), first=fr(saved_days)[0], last=fr(saved_days)[1]),
        known_inventory=dict(exposures=len(known), dates=len(known_days)),
        new_exposures_not_saved=len(new_rows),
        new_exposures_not_in_inventory=len([r for r in new_rows if (r['id'], r['detector']) not in known]),
        new_dates=[utc(d) for d in new_days],
        new_dates_not_in_inventory=[utc(d) for d in sorted(set(new_days) - known_days)],
        motion_detectors=mdet,
        new_dates_matching_motion_detector=[utc(d) for d, v in sorted(cand.items()) if any(c['detector'] in mdet for c in v)],
        aws_head=dict(checked=len(picks), ok=heads), candidates={utc(d): v for d, v in sorted(cand.items())})


def md(results):
    L = ['# SPHEREx discovery census', '',
         f'Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%MZ}. Position: preset ra/dec, SIA radius {RADIUS} deg, TAP point search. '
         'Fields are 10 arcmin, so proper motion of a few arcsec does not change coverage. Dates are UTC (floor MJD).', '']
    for t in results:
        a, s, k = t['archive'], t['saved'], t['known_inventory']
        L += [f"## {t['name']} ({t['key']}) ra={t['ra']:.5f} dec={t['dec']:.5f}", '',
              '| Provider | Collection | Status | Rows | Seconds | Error |', '|---|---|---|---:|---:|---|']
        L += [f"| {p['provider']} | {p['collection']} | {p['status']} | {p['rows']} | {p['seconds']} | {p.get('error','')[:90]} |" for p in t['providers']]
        L += ['', '| | Exposures | Dates | First | Last |', '|---|---:|---:|---|---|',
              f"| Archive (deduped) | {a['exposures']} | {a['dates']} | {a['first']} | {a['last']} |",
              f"| Saved in bundle | {s['exposures']} | {s['dates']} | {s['first']} | {s['last']} |",
              f"| Known inventory | {k['exposures']} | {k['dates']} | | |", '',
              f"New exposures not saved: {t['new_exposures_not_saved']} ({t['new_exposures_not_in_inventory']} not in known inventory). "
              f"NEW distinct dates: {len(t['new_dates'])} ({len(t['new_dates_not_in_inventory'])} not in known inventory). "
              f"AWS HEAD ok: {t['aws_head']['ok']}/{t['aws_head']['checked']}. Motion-demo detectors {t['motion_detectors']}; "
              f"new dates with a matching detector: {len(t['new_dates_matching_motion_detector'])}.", '']
        if t['new_dates']:
            L += ['New dates: ' + ', '.join(t['new_dates']), '']
    return '\n'.join(L)


if __name__ == '__main__':
    byk = {f['key']: f for f in fields()}
    results = []
    for k in sys.argv[1:] or TARGETS:
        print('==', k, flush=True)
        r = census(byk[k]); results.append(r)
        print(json.dumps({x: r[x] for x in ('providers', 'archive', 'saved', 'aws_head')}), len(r['new_dates']), 'new dates', flush=True)
    out = ROOT / 'docs/coverage'; out.mkdir(parents=True, exist_ok=True)
    (out / 'spherex-census.json').write_text(json.dumps(dict(generated=datetime.now(timezone.utc).isoformat(), targets=results), indent=1))
    (out / 'spherex-census.md').write_text(md(results), encoding='utf-8')
