"""Real archive smoke test. Coverage is necessary, but does NOT prove visible motion.
Run explicitly: RUN_LIVE_IRSA=1 python -m pytest -m live -v
"""
import os
import numpy as np
import pytest
from backend.archive import discover, fetch_frame, CACHE

@pytest.mark.live
@pytest.mark.skipif(os.environ.get("RUN_LIVE_IRSA") != "1", reason="Set RUN_LIVE_IRSA=1 to use the real IRSA archive")
def test_wise_0855_real_observed_epochs():
    ra,dec=133.79512916666667,-7.245147222222222
    rows=discover(ra,dec)
    assert rows, "IRSA returned no WISE 0855 field coverage"
    d6=[r for r in rows if r['detector']==6]
    assert len(d6)>=2, "Need long-wavelength images of this cold target"
    assert d6[-1]['mjd']-d6[0]['mjd']>90, "Insufficient time baseline for a motion inspection"
    for row in (d6[0],d6[-1]):
        identity,metadata=fetch_frame(row,ra,dec,8)
        arr=np.load(CACHE/(identity+'.npy'),allow_pickle=False)
        assert metadata['provenance']=='observed'
        assert np.isfinite(arr).mean()>.25
    # Do not assert motion from unrelated sources or from a simulated moving dot.
    # A documented visual/source-identification review is still required for acceptance.
