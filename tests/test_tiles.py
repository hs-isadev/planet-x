"""Sky tiling used by scripts/fetch_track.py and the tiled fixed-sky view of the motion study."""
from backend.observation_lab_core import tiles as T


def test_projection_round_trip():
    for ra, dec in [(10, 20), (359.9, -45), (0.1, 89), (180, 0)]:
        xi, eta = T.to_plane(ra + .05, dec - .03, ra, dec)
        r, d = T.from_plane(xi, eta, ra, dec)
        assert abs((r - (ra + .05) + 180) % 360 - 180) < 1e-9 and abs(d - (dec - .03)) < 1e-9


def test_one_tile_inside_two_near_edge_four_at_corner():
    t = T.Tiling(150, 10, 10, 1.5)
    centre = T.from_plane(0, 0, 150, 10)
    assert t.near(*centre) == {(0, 0)}
    edge = T.from_plane(4.2, 0, 150, 10)                # 0.8' from the east edge
    assert t.near(*edge) == {(0, 0), (1, 0)}
    corner = T.from_plane(4.2, -4.2, 150, 10)
    assert t.near(*corner) == {(0, 0), (1, 0), (0, -1), (1, -1)}


def test_scenes_grow_then_split():
    pts = [dict(mjd=60000 + k * .1, ra=T.from_plane(k * 4, 0, 150, 10)[0], dec=T.from_plane(k * 4, 0, 150, 10)[1]) for k in range(12)]
    scenes = T.build_scenes(pts, 10, 1.5, 3, None, (150, 10))
    assert sum(len(s['members']) for s in scenes) == 12
    assert all(max(T.box_dims(s['box'])) <= 3 for s in scenes)
    assert T.box_dims(scenes[0]['box'])[0] == 3 and len(scenes) > 1


def test_static_star_stays_in_one_tile():
    pts = [dict(mjd=60000 + k * 30, ra=150 + k * 1e-6, dec=10) for k in range(20)]
    scenes = T.build_scenes(pts, 10, 1.5, 3, None, (150, 10))
    assert [s['box'] for s in scenes] == [[0, 0, 0, 0]]
