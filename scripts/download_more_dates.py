"""Download every released SPHEREx exposure for the saved fields into the app's bundle.

Run this on a machine with normal internet access (your Windows PC is fine), from the project root:

    python -m scripts.download_more_dates --check        # test the connection and show what is saved now
    python -m scripts.download_more_dates                # the five preset targets
    python -m scripts.download_more_dates --field barnard --field epsilon-indi
    python -m scripts.download_more_dates --all-fields   # presets plus the nearby and bright stars
    python -m scripts.download_more_dates --mirror-only  # skip IRSA, read indexed exposures from the AWS mirror

Where the files go (this is where the app already looks for them):
    backend/data/spherex-seed/<hash>.fits and <hash>.record.json   the FITS cutouts and their provenance
    backend/data/spherex-seed/<session>/                           aligned previews and the manifest
    backend/data/spherex-seed/featured-views/<field>.json          the index the viewer reads

Nothing is overwritten with a smaller set: a field's saved view is only replaced when the new one holds at
least as many exposures. After it finishes, deploy the updated backend/data/spherex-seed folder as usual.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SEED = ROOT / 'backend/data/spherex-seed'
PRESETS = ['barnard', 'epsilon-indi', 'wise-0855', 'rw-aur', 'r-dra']
ENDPOINTS = {
    'IRSA TAP (finds exposures)': 'https://irsa.ipac.caltech.edu/TAP/capabilities',
    'IRSA cutouts (downloads FITS)': 'https://irsa.ipac.caltech.edu/ibe/',
    'AWS mirror (downloads FITS)': 'https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/',
}


def check_connection():
    """Report plainly which hosts answer. A 403 from a proxy or firewall is a block, not a server error."""
    reachable = {}
    for name, url in ENDPOINTS.items():
        try:
            response = requests.get(url, timeout=20)
            # The public S3 bucket root answers 403 AccessDenied itself; that still proves we reached it.
            served = response.status_code < 500 and (response.status_code != 403 or 'x-amz-request-id' in response.headers)
            reachable[name] = served
            print(f"  {'OK     ' if served else 'BLOCKED'} {name}: HTTP {response.status_code}")
        except requests.exceptions.ProxyError as error:
            reachable[name] = False
            print(f'  BLOCKED {name}: a proxy or firewall refused the connection ({str(error)[:90]})')
        except requests.RequestException as error:
            reachable[name] = False
            print(f'  FAILED  {name}: {type(error).__name__}: {str(error)[:90]}')
    return reachable


def saved_summary(keys=None):
    rows = {}
    for path in sorted((SEED / 'featured-views').glob('*.json')):
        key = path.stem
        if keys and key not in keys:
            continue
        entry = json.loads(path.read_text(encoding='utf-8'))
        manifest = SEED / entry['session'] / 'manifest.json'
        stamps = []
        if manifest.is_file():
            stamps = sorted(frame['timestamp'] for frame in json.loads(manifest.read_text(encoding='utf-8'))['frames'])
        rows[key] = dict(exposures=entry['loaded'], dates=entry.get('dates'), discovered=entry.get('discovered'),
                         first=stamps[0][:10] if stamps else '', last=stamps[-1][:10] if stamps else '')
    return rows


def print_table(title, rows):
    print(f'\n{title}')
    print(f"  {'field':<14}{'exposures':>10}{'dates':>7}{'archive lists':>15}  first -> last")
    for key, row in rows.items():
        print(f"  {key:<14}{row['exposures']:>10}{str(row['dates']):>7}{str(row['discovered']):>15}  {row['first']} -> {row['last']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--field', action='append', help='Field key to download (repeat for several). Default: the five presets.')
    parser.add_argument('--all-fields', action='store_true', help='Every saved field, not only the five presets.')
    parser.add_argument('--mirror-only', action='store_true', help='Use the saved exposure index and the AWS mirror; do not call IRSA.')
    parser.add_argument('--daily-only', action='store_true', help='Fetch one exposure per UTC date only (fastest way to gain dates).')
    parser.add_argument('--check', action='store_true', help='Test the connection and show what is saved; download nothing.')
    args = parser.parse_args()

    print('Checking the connection...')
    reachable = check_connection()
    tap = reachable['IRSA TAP (finds exposures)']
    cutouts = reachable['IRSA cutouts (downloads FITS)'] or reachable['AWS mirror (downloads FITS)']
    keys = None if args.all_fields else (args.field or PRESETS)
    before = saved_summary(keys)
    print_table('Saved now', before)
    if args.check:
        return 0
    if not cutouts:
        print('\nNo download host is reachable from this machine, so nothing can be fetched. This is a network block'
              ' (firewall, proxy, VPN or an offline connection), not a problem with the app. Run it from a connection that can'
              ' open https://irsa.ipac.caltech.edu in a browser.')
        return 2
    mirror_only = args.mirror_only
    if not tap and not mirror_only:
        print('\nIRSA discovery is not reachable, so switching to --mirror-only: only exposures already listed in'
              ' backend/data/mirror-footprints.json can be found, which cannot reveal brand-new dates.')
        mirror_only = True

    from backend.observation_lab_core.warm_cache import refresh
    started = time.time()
    result = refresh(keys, force=True, bundle=True, mirror_only=mirror_only, daily_only=args.daily_only)
    after = saved_summary(keys)
    print_table('Saved after this run', after)
    print('\nChange per field')
    for key, row in after.items():
        old = before.get(key, dict(exposures=0, dates=0))
        print(f"  {key:<14}{row['dates'] - (old['dates'] or 0):+d} dates, {row['exposures'] - old['exposures']:+d} exposures")
    status = (result.get('fields') or {})
    for key, info in status.items():
        if info.get('error') or info.get('failures'):
            print(f"  note {key}: {info.get('error') or str(info.get('failures')) + ' download errors'}")
    print(f"\nFinished in {time.time() - started:.0f}s. Files are in {SEED}")
    print('If a field gained no dates, the archive does not list more observations of it yet: this script downloads '
          'everything IRSA releases, so new dates only appear when IRSA publishes new data.')
    return 0 if result['completed'] == result['total'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
