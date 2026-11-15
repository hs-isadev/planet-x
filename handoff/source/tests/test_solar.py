import numpy as np
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.solar import solar_snapshot,ecliptic

def test_geometric_solar_positions_are_finite_metric_and_dated():
    r=solar_snapshot('2026-11-09')
    assert r['units']=='AU' and r['provenance']=='computed'
    assert [d['id'] for d in r['objects']]==['sun','mercury','venus','earth','mars','jupiter','saturn','uranus','neptune']
    for d in r['objects']:
        assert np.isfinite(d['xyz_au']).all()
        assert np.linalg.norm(d['xyz_au'])==pytest.approx(d['distance_sun_au'])
        assert d['radius_km']>0
    earth=next(d for d in r['objects'] if d['id']=='earth')
    assert .98<earth['distance_sun_au']<1.02
    assert 'ra' not in earth # no sky coordinate as observed from Earth's center
    assert r['objects'][0]['distance_sun_au']==0
    assert len(earth['orbit_au'])==257
    np.testing.assert_allclose(earth['orbit_au'][128],earth['xyz_au'],atol=1e-10)
    assert not any(d['id']=='planet-x' for d in r['objects'])

def test_epoch_changes_positions_and_rotation_preserves_distances():
    a=solar_snapshot('2026-01-01');b=solar_snapshot('2026-07-01')
    earth=lambda r:next(d for d in r['objects'] if d['id']=='earth')
    assert np.linalg.norm(np.array(earth(a)['xyz_au'])-earth(b)['xyz_au'])>1.9
    v=np.array([1.,2.,3.]);assert np.linalg.norm(ecliptic(v))==pytest.approx(np.linalg.norm(v))

def test_plain_frontend_and_color_scale_routes():
    c=TestClient(app)
    assert c.get('/').status_code==200
    assert 'importmap' in c.get('/').text and '/app.js' in c.get('/').text
    assert 'React' not in c.get('/').text
    assert c.get('/api/solar?date=not-a-date').status_code==422
    assert c.get('/api/solar?date=2200-01-01').status_code==422
    assert c.get('/api/colorbar?cmap=gray&stretch=asinh').content.startswith(b'\x89PNG')
    assert c.get('/api/colorbar?cmap=invalid').status_code==422

def test_live_schema_guard_rejects_changed_columns(tmp_path,monkeypatch):
    import backend.archive as archive
    import json
    monkeypatch.setattr(archive,'CACHE',tmp_path)
    (tmp_path/'verified-spherex-schema.json').write_text(json.dumps([dict(table_name='spherex.plane',column_name='wrong',datatype='char')]))
    with pytest.raises(ValueError,match='No columns are guessed'):archive.verify_service_schema(None)
