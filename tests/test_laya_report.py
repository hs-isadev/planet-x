import json

from fastapi.testclient import TestClient

from backend import guide, laya_sequence
from backend.main import app

REVIEW_ID = 'laya-seq-testreceipt'


def test_saved_report_distinguishes_visual_change_and_measured_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(laya_sequence, 'CACHE', tmp_path)
    exposure_ids = ['earlier', 'later']
    dates = ['2025-04-20', '2025-10-20']
    batch = dict(exposure_ids=exposure_ids, dates=dates, group='D4', crop=[0, 0, 16, 16],
                 compatible_pixels=200, measured_residual_pixels=3)
    task = dict(id=REVIEW_ID, status='complete', total=3, loaded=2, reviewed=2, failed=[],
                batches=[dict(batch, key='a', choice='shifted position'),
                         dict(batch, key='b', choice='appeared or brightened'),
                         dict(batch, key='b', choice='appeared or brightened')],
                exposures=[dict(id=exposure_ids[0], mjd=60000, wavelength_um=3.50),
                           dict(id=exposure_ids[1], mjd=60183, wavelength_um=3.51)])
    (tmp_path/(REVIEW_ID+'.json')).write_text(json.dumps(task), encoding='utf-8')

    client = TestClient(app)
    response = client.get(f'/api/laya/sequence/{REVIEW_ID}/report')
    assert response.status_code == 200
    report = response.json()
    assert report['completed_comparisons'] == 2
    assert report['classification_counts']['possible_position_shift'] == 1
    assert report['classification_counts']['appeared_or_brightened'] == 1
    assert report['comparisons'][0]['baseline_days'] == 183
    assert report['comparisons'][0]['significant_residual_pixels'] == 3
    assert report['comparisons'][0]['scientific_assessment'] == 'unvalidated_visual_suggestion'
    assert 'No calibrated displacement' in report['scientific_assessment']

    state = guide.app_context(guide.GuideContext(review_id=REVIEW_ID), {})
    assert state['laya']['status'] == 'complete' and 'laya_report' not in state
    state = guide.app_context(guide.GuideContext(review_id=REVIEW_ID, include_review_report=True), {})
    assert state['laya_report']['classification_counts'] == report['classification_counts']
    assert state['laya_report']['example_count'] == 2
    assert 'comparisons' not in state['laya_report']
    assert 'include_review_report' not in state
