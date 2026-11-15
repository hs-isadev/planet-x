"""Reconstruct the archived SPHEREx detector view from its native FITS."""
import base64
import io
import os
import uuid

import numpy as np
import requests
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import NoConvergence, WCS
from fastapi import HTTPException, Query
from fastapi.responses import FileResponse
from filelock import FileLock, Timeout
from PIL import Image

from .archive import CACHE, CONFIG, ensure_frame_files

DETECTOR_SIZE = 2040
STAR_MAP = 'https://svs.gsfc.nasa.gov/vis/a000000/a003800/a003895/starmap_4k.jpg'
MAX_STAR_MAP_BYTES = 4 * 1024 * 1024


def sky_position(wcs, x, y):
    sky = wcs.pixel_to_world(x, y).icrs
    ra, dec = float(sky.ra.deg), float(sky.dec.deg)
    if not np.isfinite([ra, dec]).all():
        raise ValueError("The detector WCS cannot locate this pixel on the sky.")
    return {"ra": ra, "dec": dec}


def detector_offset(header, width, height):
    """Use the documented 0-based original detector pixel WCS."""
    if (header.get("WCSNAMEA") or "").strip() != "0-based active pixel coordinates":
        return None
    try:
        offset = np.array([1 - float(header[f"CRPIX{i}A"]) for i in (1, 2)])
    except (KeyError, ValueError, TypeError):
        return None
    rounded = np.rint(offset)
    if (not np.isfinite(offset).all() or not np.allclose(offset, rounded, atol=1e-6)
            or np.any(rounded < 0) or np.any(rounded + [width, height] > DETECTOR_SIZE)):
        return None
    return rounded.astype(int).tolist()


def spacecraft_position(header):
    frame = (header.get("XYZ_SC_SYSTEM") or "").strip()
    if frame != "GEOCENTER":
        return None
    for suffix, date_key, name in (("", "DATE-AVG", "midpoint"), ("_START", "DATE-BEG", "start")):
        try:
            xyz = [float(header[f"{axis}_SC{suffix}"]) for axis in "XYZ"]
            time = str(header[date_key])
        except (KeyError, ValueError, TypeError):
            continue
        if np.isfinite(xyz).all() and 6378 < np.linalg.norm(xyz) < 100000:
            return {"xyz_km": xyz, "frame": frame, "time": time, "sample": name}
    return None


def image_preview(hdus):
    image = hdus["IMAGE"].data
    variance = hdus["VARIANCE"].data
    flags = hdus["FLAGS"].data
    good = (np.isfinite(image) & np.isfinite(variance) & (variance > 0)
            & np.isin(flags, CONFIG["accepted_pixel_flags"]))
    if not good.any():
        raise ValueError("No valid observed pixels remain after applying the quality mask.")
    lo, hi = np.percentile(image[good], [1, 99.7])
    scale = max(float(hi - lo), 1e-12)
    level = np.clip((np.where(good, image, lo) - lo) / scale, 0, 1)
    gray = np.round(255 * np.arcsinh(8 * level) / np.arcsinh(8)).astype(np.uint8)
    rgba = np.dstack([gray, gray, gray, good.astype(np.uint8) * 255])
    stream = io.BytesIO()
    Image.fromarray(np.flipud(rgba)).save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode()


def camera_geometry(hdus):
    image = hdus["IMAGE"]
    height, width = image.data.shape
    header = image.header
    wcs = WCS(header, fobj=hdus).celestial
    if not wcs.has_celestial:
        raise ValueError("This exposure has no celestial detector calibration.")
    offset = detector_offset(header, width, height)
    crop_center = ((width - 1) / 2, (height - 1) / 2)
    center = ((DETECTOR_SIZE - 1) / 2 - offset[0],
              (DETECTOR_SIZE - 1) / 2 - offset[1]) if offset is not None else crop_center
    return {
        "width": width, "height": height,
        "detector_size": DETECTOR_SIZE if offset is not None else None,
        "detector_offset": offset,
        "crop_center": sky_position(wcs, *crop_center),
        "detector_center": sky_position(wcs, *center),
        "camera_right": sky_position(wcs, center[0] + 1, center[1]),
        "camera_up": sky_position(wcs, center[0], center[1] + 1),
        "spacecraft": spacecraft_position(header) or spacecraft_position(hdus[0].header),
    }, wcs


def direction_for_pixel(geometry, wcs, x, y):
    offset = geometry["detector_offset"]
    if offset is None:
        left, bottom, width, height = -.5, -.5, geometry["width"], geometry["height"]
    else:
        left, bottom = -.5 - offset[0], -.5 - offset[1]
        width = height = geometry["detector_size"]
    if not np.isfinite([x, y]).all() or not (left <= x <= left + width and bottom <= y <= bottom + height):
        raise ValueError("Choose a point within the selected detector.")
    return sky_position(wcs, x, y)


def cached_star_map():
    path = CACHE / "catalog-sky-svs3895.jpg"
    if path.is_file():
        return path
    with FileLock(str(path) + ".lock", timeout=8):
        if path.is_file():
            return path
        staged = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
        try:
            with requests.get(STAR_MAP, timeout=(4, 8), stream=True) as response:
                response.raise_for_status()
                size = 0
                with staged.open("wb") as output:
                    for block in response.iter_content(64 * 1024):
                        size += len(block)
                        if size > MAX_STAR_MAP_BYTES:
                            raise ValueError("Catalog sky exceeded its download limit.")
                        output.write(block)
            with Image.open(staged) as image:
                if image.format != "JPEG" or image.size != (4096, 2048):
                    raise ValueError("Unexpected NASA sky map format.")
                image.verify()
            os.replace(staged, path)
        finally:
            staged.unlink(missing_ok=True)
    return path


def install_satellite_view_routes(app, jobs, guard):
    @app.get("/api/satellite-star-map.jpg", include_in_schema=False)
    def satellite_star_map():
        try:
            return FileResponse(cached_star_map(), media_type="image/jpeg",
                                headers={"Cache-Control": "public, max-age=604800"})
        except (OSError, ValueError, Timeout, requests.RequestException) as exc:
            raise HTTPException(503, "NASA catalog sky is temporarily unavailable.") from exc

    def get_frame(identity, index, exposure_id):
        with guard:
            job = jobs.get(identity)
            if job is None:
                raise HTTPException(404, "This session expired. Search the field again.")
            frames = job["frames"]
            if not 0 <= index < len(frames) or frames[index]["id"] != exposure_id:
                raise HTTPException(409, "The selected exposure changed. Open SPHEREx view again.")
            frame = dict(frames[index])
            target = {"ra": job["ra"], "dec": job["dec"]}
        if frame["status"] != "ready":
            raise HTTPException(425, "Wait for this exposure to load.")
        cache_id = frame.get("cache_id")
        if not cache_id:
            raise HTTPException(410, "Native FITS information is unavailable for this exposure.")
        path = CACHE / (cache_id + ".fits")
        if not path.is_file():
            try:
                ensure_frame_files(frame, {"ra": target["ra"], "dec": target["dec"], "fov": job["fov"]}, native=True)
            except Exception as exc:
                raise HTTPException(503, "IRSA could not reload this native exposure. Try another exposure or retry.") from exc
            path = CACHE / (frame["cache_id"] + ".fits")
            if not path.is_file():
                raise HTTPException(410, "This native exposure is unavailable.")
        return frame, path, target

    @app.get("/api/jobs/{identity}/satellite-view/{index}")
    def satellite_view(identity: str, index: int, exposure_id: str = Query(max_length=80)):
        frame, path, target = get_frame(identity, index, exposure_id)
        try:
            with fits.open(path, memmap=False) as hdus:
                geometry, wcs = camera_geometry(hdus)
                image = image_preview(hdus)
                try:
                    x, y = wcs.world_to_pixel(SkyCoord(target["ra"], target["dec"], unit="deg", frame="icrs"))
                    target_pixel = [float(x), float(y)] if np.isfinite([x, y]).all() else None
                except NoConvergence:
                    target_pixel = None
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"Cannot reconstruct this detector view. {exc}") from exc
        return {**geometry, "target": target, "target_pixel": target_pixel, "image": image, "exposure_id": frame["id"],
                "observation": frame.get("observation"), "archive_url": frame.get("url"),
                "date": frame["date"], "detector": frame.get("detector")}

    @app.get("/api/jobs/{identity}/satellite-view/{index}/direction")
    def satellite_direction(identity: str, index: int, x: float, y: float,
                            exposure_id: str = Query(max_length=80)):
        _, path, _ = get_frame(identity, index, exposure_id)
        try:
            with fits.open(path, memmap=False) as hdus:
                geometry, wcs = camera_geometry(hdus)
                return direction_for_pixel(geometry, wcs, x, y)
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, f"Cannot resolve this detector direction. {exc}") from exc
