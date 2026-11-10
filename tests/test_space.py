import numpy as np
import pytest
from backend.space import distance_record,space_catalog


def test_high_snr_distance_and_interval():
    r=distance_record(dict(ra=0.,dec=0.,parallax=100.,parallax_error=1.,catalog='Gaia DR3',ruwe=1.))
    assert r['distance_pc']==10
    assert r['distance_lower_pc']==pytest.approx(1000/101)
    assert r['distance_upper_pc']==pytest.approx(1000/99)
    assert r['xyz_pc']==pytest.approx([10,0,0])
    assert not r['uncertain']
    assert r['position_provenance'].startswith('computed')

@pytest.mark.parametrize('ra,dec,expected',[(90,0,[0,10,0]),(180,0,[-10,0,0]),(0,90,[0,0,10])])
def test_icrs_cartesian_axes(ra,dec,expected):
    r=distance_record(dict(ra=ra,dec=dec,parallax=100.,parallax_error=1.))
    assert r['xyz_pc']==pytest.approx(expected,abs=1e-10)

@pytest.mark.parametrize('p,e',[(0,1),(-1,1),(1,1),(1,None),(None,1),(1,0)])
def test_unknown_depth_is_never_invented(p,e):
    r=distance_record(dict(ra=13.,dec=7.,parallax=p,parallax_error=e))
    assert r['distance_pc'] is None and 'xyz_pc' not in r


def test_poor_parallax_model_fallback_is_labeled():
    r=distance_record(dict(ra=0.,dec=0.,parallax=.1,parallax_error=1.,distance_gspphot=2000.,distance_gspphot_lower=1800.,distance_gspphot_upper=2500.))
    assert r['distance_pc']==2000 and r['uncertain']
    assert 'model' in r['distance_method'] and 'GSP-Phot' in r['distance_source']


def test_catalog_fallback_and_unknowns_are_separate(monkeypatch):
    import backend.space as space
    rows=[dict(id='known',ra=0.,dec=0.,parallax=100.,parallax_error=1.,catalog='Gaia DR3'),dict(id='unknown',ra=90.,dec=0.,parallax=-1.,parallax_error=1.,catalog='Gaia DR3')]
    monkeypatch.setattr(space,'gaia_rows',lambda *a,**k:dict(rows=rows,truncated=False,limit=1000))
    monkeypatch.setattr(space,'simbad_distances',lambda *a,**k:[dict(id='fallback',ra=180.,dec=0.,parallax=200.,parallax_error=2.,catalog='SIMBAD')])
    result=space_catalog(0,0,8,include_simbad=True)
    assert len(result['objects'])==2 and len(result['unknown'])==1
    assert result['fallback_count']==1
    assert next(o for o in result['objects'] if o['id']=='fallback')['distance_source']=='SIMBAD'


def test_planet_entries_cannot_be_used_as_stellar_positions():
    from backend.space import eligible_stellar_record
    assert not eligible_stellar_record({'name':'host b','object_type':'Pl'})
    assert not eligible_stellar_record({'name':'host c','object_type':'Pl?'})
    assert eligible_stellar_record({'name':'brown dwarf','object_type':'BD*'})
    assert eligible_stellar_record({'name':'star','object_type':'PM*'})
