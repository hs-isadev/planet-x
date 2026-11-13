"""Offline: the bundled WISE/NEOWISE supplemental series is served and matches the UI contract."""
import backend  # noqa: F401  configure astronomy caches first
from fastapi.testclient import TestClient
from backend import main

FRAME_KEYS = {'id', 'date_utc', 'mjd', 'epoch_start', 'epoch_end', 'preview', 'fits', 'source_url', 'release',
              'scan_id', 'frame_num', 'quality', 'expected_target_xy'}


def test_bundled_series_matches_contract_and_files_are_served():
    client = TestClient(main.app)
    data = client.get('/observation-lab/api/supplemental/wise-0855').json()
    assert data['field'] == 'wise-0855' and data['series'] and set(data['discovery']) >= {'matched', 'downloaded', 'valid', 'failures'}
    for s in data['series']:
        assert {s['band']} == {f"W{s['id'][-1]}"} and s['distinct_dates'] == len(s['frames'])
        dates = [f['date_utc'][:10] for f in s['frames']]
        assert dates == sorted(dates) and len(set(dates)) == len(dates)  # one frame per UTC date, chronological
        for f in s['frames'] + s['extra']:
            assert FRAME_KEYS <= set(f) and f['source_url'].startswith('https://irsa.ipac.caltech.edu/')
            assert {'qual_frame', 'target_finite', 'target_saturated', 'snr_at_target'} <= set(f['quality'])
            xy = f['expected_target_xy']
            assert xy is None or all(0 <= v <= 1 for v in xy)
    frame = data['series'][0]['frames'][0]
    assert client.get(frame['preview']).content[:4] == b'\x89PNG'
    assert client.get(frame['fits']).content[:2] == b'\x1f\x8b'


def test_bad_keys_and_traversal_are_rejected():
    client = TestClient(main.app)
    assert client.get('/observation-lab/api/supplemental/no-such-field').status_code == 404
    assert client.get('/observation-lab/api/supplemental/..%2Fbackend').status_code == 404
    assert client.get('/observation-lab/supplemental/wise-0855/series.json').status_code == 404
    assert client.get('/observation-lab/supplemental/wise-0855/..%2F..%2Fsimbad_client.py').status_code == 404
