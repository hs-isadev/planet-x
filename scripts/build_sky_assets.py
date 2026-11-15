"""Build the static star-sky assets used by the "Your sky" planetarium and the 3D backdrop.

Source data: d3-celestial 0.7.35 (Olaf Frohn, BSD-3-Clause) data folder, which packages the HYG / Hipparcos
star catalog (positions, V magnitude, B−V colour), IAU constellation lines and names, Messier objects and the
Milky Way brightness contours (5 levels). Get it with:  npm i d3-celestial@0.7.35

    python scripts/build_sky_assets.py node_modules/d3-celestial/data

Writes web/assets/sky/:
  stars.bin           little-endian float32 records [ra°, dec°, Vmag, B−V], brightest first (mag ≤ 7.5)
  sky.json            named stars, constellation lines + labels, bright deep-sky objects
  milkyway.jpg        equirectangular RA/Dec brightness map (RA 0° at the image centre... see MW_LAYOUT)
"""
import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/assets/sky'
MAG_LIMIT = 7.5
MW_W, MW_H = 4096, 2048
# Milky Way image layout: x = RA (0° at left edge, increasing to the right, 360° at the right edge),
# y = Dec (+90° at the top, −90° at the bottom). The viewer maps texture u = RA/360, v = (Dec+90)/180.


def ra_of(lon):
    return lon % 360.0


def build(src):
    OUT.mkdir(parents=True, exist_ok=True)
    stars = json.loads((src / 'stars.8.json').read_text(encoding='utf-8'))['features']
    rows = []
    for f in stars:
        mag = float(f['properties']['mag'])
        if mag > MAG_LIMIT:
            continue
        bv = f['properties'].get('bv')
        try:
            bv = float(bv)
        except (TypeError, ValueError):
            bv = 0.6
        lon, lat = f['geometry']['coordinates']
        rows.append((ra_of(lon), lat, mag, bv, f['id']))
    rows.sort(key=lambda r: r[2])
    with open(OUT / 'stars.bin', 'wb') as out:
        for r in rows:
            out.write(struct.pack('<4f', *r[:4]))

    names = json.loads((src / 'starnames.json').read_text(encoding='utf-8'))
    by_hip = {str(r[4]): r for r in rows}
    named = []
    for hip, n in names.items():
        r = by_hip.get(str(hip))
        if r and n.get('name') and r[2] < 4.0:
            named.append([round(r[0], 4), round(r[1], 4), round(r[2], 2), n['name'], n.get('c', '')])
    named.sort(key=lambda x: x[2])

    lines = []
    for f in json.loads((src / 'constellations.lines.json').read_text(encoding='utf-8'))['features']:
        for seg in f['geometry']['coordinates']:
            lines.append([f['id'], [[round(ra_of(a), 3), round(d, 3)] for a, d in seg]])
    labels = []
    for f in json.loads((src / 'constellations.json').read_text(encoding='utf-8'))['features']:
        lon, lat = f['geometry']['coordinates']
        labels.append([f['id'], f['properties']['name'], round(ra_of(lon), 3), round(lat, 3), int(f['properties'].get('rank', 3))])

    dsos = []
    for f in json.loads((src / 'messier.json').read_text(encoding='utf-8'))['features']:
        p = f['properties']
        try:
            mag = float(p.get('mag'))
        except (TypeError, ValueError):
            continue
        if mag <= 7.5:
            lon, lat = f['geometry']['coordinates']
            dsos.append([p['name'], p.get('alt') or p.get('desig', ''), p.get('type', ''), mag, round(ra_of(lon), 3), round(lat, 3)])
    sky = dict(source='d3-celestial 0.7.35 data (BSD-3-Clause): HYG/Hipparcos stars, IAU constellations, Messier catalogue, Milky Way contours',
               star_count=len(rows), mag_limit=MAG_LIMIT, named=named, lines=lines, labels=labels, dsos=dsos)
    (OUT / 'sky.json').write_text(json.dumps(sky, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

    # Milky Way: fill the five isophote levels on top of each other, then blur to a soft glow.
    mw = json.loads((src / 'mw.json').read_text(encoding='utf-8'))['features']
    level = {'ol1': .16, 'ol2': .30, 'ol3': .48, 'ol4': .70, 'ol5': 1.0}
    acc = np.zeros((MW_H, MW_W), np.float32)
    for f in mw:
        # Even-odd fill: every ring toggles the pixels inside it. Rings that run all the way round the sky (the
        # edges of the band) are closed through the north pole, so two of them toggle exactly the band between.
        mask = np.zeros((MW_H, MW_W), bool)
        for poly in f['geometry']['coordinates']:
            for ring in poly:
                xs = np.unwrap(np.radians([a for a, d in ring])) * 180 / np.pi
                xs = (xs - xs[0] + ra_of(ring[0][0])) / 360 * MW_W
                pts = list(zip(xs, [(90 - d) / 180 * MW_H for a, d in ring]))
                if abs(xs[-1] - xs[0]) > MW_W / 2:          # wraps the whole sky
                    pts += [(xs[-1], -1), (xs[0], -1)]
                layer = Image.new('1', (MW_W, MW_H), 0)
                draw = ImageDraw.Draw(layer)
                for shift in (-2 * MW_W, -MW_W, 0, MW_W, 2 * MW_W):
                    draw.polygon([(x + shift, y) for x, y in pts], fill=1)
                mask ^= np.asarray(layer, bool)
        acc = np.maximum(acc, mask.astype(np.float32) * level[f['id']])
    img = Image.fromarray((acc * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(14))
    fine = Image.fromarray((acc * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3.5))
    a = np.asarray(img, np.float32) * .55 + np.asarray(fine, np.float32) * .45
    # mottled texture: real star clouds are clumpy, not flat-filled contours
    rng = np.random.default_rng(7)
    noise = np.zeros_like(a)
    for scale, weight in ((256, .5), (64, .3), (16, .2)):
        n = rng.random((MW_H // scale + 2, MW_W // scale + 2)).astype(np.float32)
        noise += weight * np.asarray(Image.fromarray((n * 255).astype(np.uint8)).resize((MW_W + 2 * scale, MW_H + 2 * scale), Image.BICUBIC), np.float32)[scale:scale + MW_H, scale:scale + MW_W] / 255
    a = a * (.72 + .56 * noise)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(OUT / 'milkyway.jpg', quality=88)
    print(f'{len(rows)} stars ≤ mag {MAG_LIMIT}, {len(named)} named, {len(lines)} constellation lines, {len(dsos)} Messier objects → {OUT}')


if __name__ == '__main__':
    build(Path(sys.argv[1] if len(sys.argv) > 1 else 'node_modules/d3-celestial/data'))
