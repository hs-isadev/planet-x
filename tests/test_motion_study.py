"""Motion study: unit checks on the maths and a contract check on the bundled study files."""
import json
import math
from pathlib import Path

import numpy as np
import pytest

from backend.observation_lab_core import motion_study as ms

ROOT = Path(__file__).resolve().parents[1]
STUDIES = ROOT / 'web/assets/motion-study'


def test_expected_position_follows_proper_motion():
    cat = dict(ra=100.0, dec=0.0, pmra_mas_yr=3600.0, pmdec_mas_yr=-7200.0, parallax_mas=0.0)
    ra, dec, east, north = ms.expected(cat, ms.J2000 + 365.25 * 10)
    assert math.isclose(east, 36.0, rel_tol=1e-9) and math.isclose(north, -72.0, rel_tol=1e-9)
    assert math.isclose(dec, -72.0 / 3600, rel_tol=1e-9) and math.isclose(ra, 100 + 36.0 / 3600, rel_tol=1e-6)


def test_parallax_amplitude_is_bounded_by_the_catalog_value():
    cat = dict(ra=269.45, dec=4.69, pmra_mas_yr=0.0, pmdec_mas_yr=0.0, parallax_mas=547.0)
    shifts = [math.hypot(*ms.expected(cat, ms.J2000 + d)[2:]) for d in range(0, 366, 15)]
    assert max(shifts) <= 0.547 * 1.02 and max(shifts) > 0.3


def test_fit_recovers_a_known_proper_motion():
    rng = np.random.default_rng(1)
    pts = []
    for t in np.linspace(0, 16, 30):
        pts.append(dict(mjd=ms.J2000 + 3650 + t * 365.25, east=-0.8 * t + rng.normal(0, .3), north=10.4 * t + rng.normal(0, .3),
                        err=.3, plx_east=0.0, plx_north=0.0))
    fit = ms.fit_motion(pts, {})
    assert abs(fit['pmra_mas_yr'] + 800) < 3 * fit['pmra_err'] and abs(fit['pmdec_mas_yr'] - 10400) < 3 * fit['pmdec_err']


def test_verdict_rules():
    cat = dict(pmra_mas_yr=-800.0, pmdec_mas_yr=10400.0)
    fits = dict(combined=dict(pmra_mas_yr=-805.0, pmdec_mas_yr=10390.0, pmra_err=15.0, pmdec_err=15.0, baseline_yr=16.0,
                              total_mas_yr=10421.0, n=28))
    pts = [dict(err=.4)] * 28
    meta = dict(expect='motion')
    assert ms.decide(meta, cat, fits, pts, [], {'tested': False}, {})['code'] == 'as-predicted'
    fits['combined'].update(pmdec_mas_yr=9000.0, total_mas_yr=9035.0)
    assert ms.decide(meta, cat, fits, pts, [], {'tested': False}, {})['code'] == 'differs'
    still = dict(pmra_mas_yr=0.0, pmdec_mas_yr=0.0)
    quiet = dict(combined=dict(pmra_mas_yr=20.0, pmdec_mas_yr=-10.0, pmra_err=200.0, pmdec_err=200.0, baseline_yr=1.0,
                               total_mas_yr=22.4, n=3))
    assert ms.decide(dict(expect='brightness'), still, quiet, pts[:3], [], {'tested': True, 'variable': True, 'method': 'PSF fit',
                     'median_amplitude_mag': 1.2, 'threshold_mag': .2, 'rule': 'r'}, {})['code'] == 'brightness'
    assert ms.decide(meta, still, quiet, pts[:3], [], {'tested': False}, {})['code'] == 'too-small'


@pytest.mark.parametrize('field', ['barnard', 'epsilon-indi', 'wise-0855', 'proxima-centauri', 'rw-aur', 'r-dra', 'vesta'])
def test_bundled_study_contract(field):
    path = STUDIES / field / 'study.json'
    if not path.is_file():
        pytest.skip('study not generated')
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['field'] == field and data['verdict']['title'] and data['verdict']['rule']
    images = [f['png'] for f in data['timelapse']] + [s['png'] for v in data['visits'] for s in v['stacks'].values()]
    images += list(data['differences'].values()) + [f['png'] for f in data.get('sky', [])]
    assert images
    for name in images:
        assert (STUDIES / field / 'img' / name).is_file(), name
    if field in ('barnard', 'epsilon-indi', 'wise-0855'):
        assert data['verdict']['code'] == 'as-predicted'
        assert data['astrometry']['fits']['combined']['baseline_yr'] > 10
