import io
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import numpy as np
from PIL import Image
from matplotlib import colormaps
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from astroquery.simbad import Simbad
from .archive import CONFIG, CACHE, ROOT, discover, fetch_frame, atomic_json, prune_cache, ensure_frame_files, key_for
from .coordinates import parse_coordinates

app = FastAPI(title="Planet X / SPHEREx Observatory", version="1.0.0")
JOBS = {}
GUARD = threading.RLock()
CLIENTS = {}
PRESET_LOCK = threading.Lock()
PRESETS = [
    dict(id="barnard", name="Barnard’s Star", simbad="Barnard's Star", kind="NEARBY STAR", description="A nearby red dwarf with exceptionally fast proper motion."),
    dict(id="epsilon", name="Epsilon Indi B", simbad="eps Indi B", kind="BROWN DWARF", description="A nearby brown-dwarf system, bright in the infrared."),
    dict(id="wise", name="WISE 0855", kind="COLD BROWN DWARF", description="An exceptionally cold nearby brown dwarf; a demanding motion target.", ra=133.79512916666667, dec=-7.245147222222222, coordinate_source="User-supplied coordinates; reference epoch unspecified."),
    dict(id="rw", name="RW Aurigae", simbad="RW Aur", kind="YOUNG STAR", description="A young variable star with a dusty, changing environment."),
    dict(id="rdraconis", name="R Draconis", simbad="R Dra", kind="VARIABLE STAR", description="A pulsating Mira variable; look for brightness changes."),
]


@app.get("/api/health")
def health():
    return {"status": "ok", "data_source": "IRSA SPHEREx", "synthetic_images": False}


@app.get("/api/presets")
def presets():
    cache = CACHE / "presets.json"
    with PRESET_LOCK:
        if cache.exists() and time.time() - cache.stat().st_mtime < 30 * 86400:
            return json.loads(cache.read_text())
        items = [dict(p) for p in PRESETS]
        try:
            names = [p["simbad"] for p in items if "simbad" in p]
            from .simbad_client import query_names
            table, server = query_names(names)
            if table is None:
                raise ValueError("SIMBAD returned no coordinates.")
            # Modern astroquery returns decimal degree ra/dec columns.
            for item in items:
                if "simbad" not in item:
                    continue
                matches = table[np.char.strip(np.asarray(table["user_specified_id"]).astype(str)) == item["simbad"]] if "user_specified_id" in table.colnames else []
                if len(matches) != 1:
                    raise ValueError("SIMBAD did not uniquely resolve " + item["simbad"])
                row = matches[0]
                if np.ma.is_masked(row["ra"]) or np.ma.is_masked(row["dec"]) or not np.isfinite(float(row["ra"])) or not np.isfinite(float(row["dec"])):
                    item["error"] = "SIMBAD has no valid coordinates for this target."
                    continue
                item.update(ra=float(row["ra"]), dec=float(row["dec"]), coordinate_source="SIMBAD via astroquery ("+server+"); ICRS J2000 catalog position, not propagated.")
            atomic_json(cache, items)
        except Exception as exc:
            for item in items:
                if "ra" not in item:
                    item["error"] = "SIMBAD is unavailable. Enter verified coordinates manually or retry."
            # Failures aren't cached. Never replace catalog positions with invented coordinates.
        return items


class Search(BaseModel):
    ra: str = Field(max_length=80)
    dec: str = Field(max_length=80)
    fov: float = Field(default=8, ge=2, le=20, description="Square field width in arcminutes")


def run_job(job, resume=False):
    with GUARD:
        if job.get('worker_active'):return
        job['worker_active']=True
    try:
        rows = job["frames"] if resume else sorted(discover(job["ra"], job["dec"]), key=lambda f: (float(f["mjd"]), f["id"]))
        with GUARD:
            if not resume:
                job["frames"] = [dict(r, status="pending", index=i) for i, r in enumerate(rows)]
            job["status"] = "fetching" if rows else "empty"
        if not rows:
            job["message"] = "No released spectral images cover this position. Try a nearby field or another preset."
            return
        # Hydrate genuine cached products before any network call. The manifest stays chronological.
        for frame in job['frames']:
            key=key_for(f"{frame['url']}|{float(job['ra'])}|{float(job['dec'])}|{float(job['fov'])}|native-analysis-v2")
            if all((CACHE/(key+ext)).exists() for ext in ('.json','.npy','.npz')):
                try:
                    meta=json.loads((CACHE/(key+'.json')).read_text())
                    with GUARD:frame.update(meta,cache_id=key,status='ready',ra=job['ra'],dec=job['dec'],fov=job['fov'])
                except (ValueError,OSError):pass
        job.setdefault('contrasts',{})
        for f in job['frames']:
            band='D'+str(f.get('detector'))
            if f['status']=='ready' and band not in job['contrasts']:
                a=np.load(CACHE/(f['cache_id']+'.npy'),allow_pickle=False);lo,hi=np.nanpercentile(a,[1,99.7])
                job['contrasts'][band]=dict(black=float(lo),white=float(max(hi,lo+1e-8)),reference_frame=f['index'],unit=f['unit'])
        if job['contrast'] is None:
            cached=next((f for f in job['frames'] if f['status']=='ready'),None)
            if cached:
                a=np.load(CACHE/(cached['cache_id']+'.npy'),allow_pickle=False);lo,hi=np.nanpercentile(a,[1,99.7])
                with GUARD:job['contrast']=dict(black=float(lo),white=float(max(hi,lo+1e-8)),reference_frame=cached['index'],unit=cached['unit'])
        def load(frame):
            if job.get("prefetch_paused") or frame.get("status")=="ready":return
            try:
                identity, metadata = fetch_frame(frame, job["ra"], job["dec"], job["fov"])
                with GUARD:
                    band='D'+str(frame.get('detector'))
                    if band not in job['contrasts']:
                        a=np.load(CACHE/(identity+'.npy'),allow_pickle=False);low,high=np.nanpercentile(a,[1,99.7])
                        job['contrasts'][band]=dict(black=float(low),white=float(max(high,low+1e-8)),reference_frame=frame['index'],unit=metadata['unit'])
                    # A physical surface-brightness range is locked for each detector.
                    # It never auto-rescales between frames while prefetching.
                    if job["contrast"] is None:
                        arr = np.load(CACHE / (identity + ".npy"), allow_pickle=False)
                        lo, hi = np.nanpercentile(arr, [1, 99.7])
                        if hi <= lo:
                            hi = lo + 1
                        job["contrast"] = {"black": float(lo), "white": float(hi), "reference_frame": frame["index"], "unit": metadata["unit"]}
                    frame.update(metadata, cache_id=identity, status="ready", ra=job["ra"], dec=job["dec"], fov=job["fov"])
            except Exception as exc:
                with GUARD:
                    frame.update(status="error", error="Cutout unavailable or rejected by quality mask.", detail=type(exc).__name__)
        # First result is downloaded before parallel background prefetch for deterministic contrast.
        load(job["frames"][0])
        with ThreadPoolExecutor(max_workers=CONFIG["concurrent_downloads"]) as executor:
            # Seed a sparse span of real epochs in each detector before filling the rest.
            # The manifest remains chronological; download order is not an observation time.
            priority=[];seen={job['frames'][0]['id']}
            same=[f for f in job['frames'][1:] if f.get('detector')==job['frames'][0].get('detector') and abs(f['mjd']-job['frames'][0]['mjd'])>=1]
            for fraction in (1,.75,.5,.25):
                if same:
                    f=same[round((len(same)-1)*fraction)]
                    if f['id'] not in seen:priority.append(f);seen.add(f['id'])
            for fraction in (0,1,1/3,2/3):
                for detector in range(1,7):
                    group=[f for f in job['frames'] if f.get('detector')==detector]
                    if not group:continue
                    f=group[round((len(group)-1)*fraction)]
                    if f['id'] not in seen:priority.append(f);seen.add(f['id'])
            priority.extend(f for f in job['frames'][1:] if f['id'] not in seen)
            list(executor.map(load,priority))
        with GUARD:
            ready = sum(f["status"] == "ready" for f in job["frames"])
            job["status"] = "paused" if job.get("prefetch_paused") else ("complete" if ready else "error")
            job["message"] = f"{ready} of {len(rows)} cutouts available. " + ("Background loading paused; resume to continue." if job.get("prefetch_paused") else "Missing or flagged pixels remain blank.")
    except Exception as exc:
        with GUARD:
            job.update(status="error", message="IRSA could not be reached or returned an invalid response. Retry shortly. No substitute images are displayed.", detail=type(exc).__name__)

    finally:
        with GUARD:
            job['worker_active']=False
            if not job.get('prefetch_paused') and job['status'] not in ('error','empty','querying') and any(f.get('status')=='pending' for f in job['frames']):
                job['status']='fetching'
                threading.Thread(target=run_job,args=(job,True),daemon=True).start()


@app.post("/api/search", status_code=202)
def search(body: Search, request: Request):
    try:
        coord = parse_coordinates(body.ra, body.dec)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    now = time.monotonic()
    client = request.client.host if request.client else "unknown"
    with GUARD:
        ra, dec = float(coord.ra.deg), float(coord.dec.deg)
        for job in JOBS.values():
            if abs(job["ra"]-ra)<1e-9 and abs(job["dec"]-dec)<1e-9 and job["fov"]==body.fov and now - job["created"] < CONFIG["query_ttl_seconds"] and job["status"] != "error":
                if job["status"]=="paused":
                    if sum(j["status"] in ("querying","fetching") for j in JOBS.values())>=CONFIG["max_active_jobs"]:
                        raise HTTPException(429,"The observatory is busy. Please retry shortly.")
                    job["prefetch_paused"]=False;job["status"]="fetching"
                    threading.Thread(target=run_job,args=(job,True),daemon=True).start()
                return {"id": job["id"]}
        hits=[t for t in CLIENTS.get(client,[]) if now-t<60]
        if len(hits)>=10:raise HTTPException(429,'Please wait a minute before requesting another new field.')
        CLIENTS[client]=hits+[now]
        active = sum(j["status"] in ("querying", "fetching") for j in JOBS.values())
        if active >= CONFIG["max_active_jobs"]:
            raise HTTPException(429, "The observatory is processing other fields. Please retry shortly.")
        if active == 0:
            # Evict completed manifests before their cache files can be pruned.
            for old_id in list(JOBS):
                if now - JOBS[old_id]["created"] > CONFIG["query_ttl_seconds"]:
                    del JOBS[old_id]
            if not JOBS:
                prune_cache()
        job = dict(id=uuid.uuid4().hex, ra=ra, dec=dec, fov=body.fov, created=now,
                   status="querying", frames=[], contrast=None, message="Searching released SPHEREx spectral images…")
        JOBS[job["id"]] = job
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return {"id": job["id"]}


def get_job(identity):
    if identity not in JOBS:
        raise HTTPException(404, "This session expired. Search this field again.")
    return JOBS[identity]


@app.post('/api/jobs/{identity}/pause')
def pause_job(identity:str):
    with GUARD:
        job=get_job(identity)
        if job.get('source')!='cloud' and job['status'] in ('querying','fetching'):
            job['prefetch_paused']=True
            job['status']='paused'
        return {'id':identity,'paused':bool(job.get('prefetch_paused'))}


@app.post('/api/jobs/{identity}/resume')
def resume_job(identity:str):
    with GUARD:
        job=get_job(identity)
        if job['status']=='paused':
            if sum(j['status'] in ('querying','fetching') for j in JOBS.values())>=CONFIG['max_active_jobs']:
                raise HTTPException(429,'The observatory is busy. Please retry shortly.')
            job['prefetch_paused']=False;job['status']='fetching'
            threading.Thread(target=run_job,args=(job,True),daemon=True).start()
        return {'id':identity}


@app.get("/api/jobs/{identity}")
def job_status(identity: str):
    with GUARD:
        job = get_job(identity)
        publish=job['contrast'] is not None
        visible=[dict(f, status='pending') if f['status']=='ready' and not publish else dict(f) for f in job['frames']]
        return dict(job, frames=visible, ready=sum(f['status']=='ready' for f in visible),
                    failed=sum(f["status"] == "error" for f in job["frames"]),
                    notes=["Observed SPHEREx IMAGE data; false-color display, not visible-light photography.",
                           "Frames vary in wavelength and date. Brightness differences and artifacts can mimic motion.",
                           "North-up WCS registration is computed. Masked pixels are transparent; no data are synthesized.",
                           "Positions are not corrected for target proper motion. A preset name does not establish a source identification.",
                           "Physical contrast range locked to the first usable frame in each detector; zodiacal background is not subtracted."])


@app.get("/api/jobs/{identity}/frames/{index}.png")
def frame_png(identity: str, index: int, cmap: str = "infrared", stretch: str = "asinh", black: float | None = None, white: float | None = None, thumbnail: bool = False, enhanced: bool = False, changes: bool = False, reference_index: int | None = None):
    with GUARD:
        job = get_job(identity)
        if index < 0 or index >= len(job["frames"]):
            raise HTTPException(404, "Unknown frame")
        frame = job["frames"][index]
        if frame["status"] != "ready":
            raise HTTPException(425, "Frame is not ready yet.")
    try:
        if not (CACHE / (frame["cache_id"] + ".npy")).exists():
            ensure_frame_files(frame,job)
    except Exception:
        raise HTTPException(503,"This cached observation expired and IRSA could not refresh it. Please retry.")
    contrast = job.get('contrasts',{}).get('D'+str(frame.get('detector')),job['contrast'])
    file = CACHE / (frame["cache_id"] + ".npy")
    if contrast is None:
        try:
            values=np.load(file,allow_pickle=False)
            if not np.isfinite(values).any():raise HTTPException(422,'No usable observed pixels.')
            low,high=np.nanpercentile(values,[1,99.7])
        except FileNotFoundError:raise HTTPException(410,'Cached frame expired; reload this field.')
        with GUARD:
            band='D'+str(frame.get('detector'))
            contrast=job.setdefault('contrasts',{}).setdefault(band,dict(black=float(low),white=float(max(high,low+1e-8)),reference_frame=index,unit=frame.get('unit','MJy/sr')))
            if job['contrast'] is None:job['contrast']=contrast
    lo = contrast["black"] if black is None else black
    hi = contrast["white"] if white is None else white
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        raise HTTPException(422, "White point must exceed black point.")
    if cmap not in ("inferno", "magma", "viridis", "gray", "infrared") or stretch not in ("linear", "sqrt", "log", "asinh"):
        raise HTTPException(422, "Unknown colormap or stretch")
    try:
        arr = np.load(file, allow_pickle=False)
    except FileNotFoundError:
        raise HTTPException(410, "Cached frame expired. Search again.")
    if enhanced:
        from .quicklook import enhanced_rgba,comparable
        reference=None
        if changes:
            candidates=[f for f in job['frames'] if f.get('status')=='ready' and comparable(frame,f) and f['mjd']<frame['mjd'] and (reference_index is None or f['index']==reference_index)]
            if not candidates:raise HTTPException(422,'No comparable wavelength/detector on another date is loaded. Load more frames or turn off red changes.')
            reference=max(candidates,key=lambda f:(f['mjd'],f['index']))
        try:rgba=enhanced_rgba(frame,reference)
        except ValueError as e:raise HTTPException(422,str(e))
        image=Image.fromarray(np.flipud(rgba));stream=io.BytesIO();image.save(stream,format='PNG')
        return Response(stream.getvalue(),media_type='image/png',headers={'Cache-Control':'private, max-age=300'})
    valid = np.isfinite(arr)
    norm = np.clip((np.nan_to_num(arr, nan=lo) - lo) / (hi - lo), 0, 1)
    if stretch == "sqrt": norm = np.sqrt(norm)
    elif stretch == "log": norm = np.log1p(100 * norm) / np.log(101)
    elif stretch == "asinh": norm = np.arcsinh(10 * norm) / np.arcsinh(10)
    if cmap == "infrared":
        from matplotlib.colors import LinearSegmentedColormap
        color = LinearSegmentedColormap.from_list("infrared", ["#050914", "#3e124f", "#a32b72", "#e77352", "#ffd18a", "#fff4d8"])
    else:
        color = colormaps[cmap]
    rgba = (color(norm) * 255).astype(np.uint8)
    rgba[..., 3] = valid.astype(np.uint8) * 255
    image = Image.fromarray(np.flipud(rgba))
    if thumbnail: image.thumbnail((96, 96), Image.Resampling.NEAREST)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return Response(stream.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=86400"})


from .routes_analysis import install_analysis_routes
install_analysis_routes(app, JOBS, GUARD, CLIENTS)

from .routes_context import install_context_routes
install_context_routes(app, JOBS, GUARD, frame_png)

from .routes_space import install_space_routes
install_space_routes(app)

from .palette import install_palette_routes
install_palette_routes(app)

from .solar import install_solar_routes
install_solar_routes(app)

from .exploration import install_exploration_routes
install_exploration_routes(app)

from .laya_review import install_laya_routes
install_laya_routes(app,JOBS,GUARD)

from .systems import install_system_routes
install_system_routes(app)


from .laya_sequence import install_sequence_routes
install_sequence_routes(app,JOBS,GUARD)

from .time_science import install_time_routes
install_time_routes(app,JOBS,GUARD)

from .companions import install_companion_routes
install_companion_routes(app)

DIST = ROOT / "web"
if DIST.exists():
    class FreshStaticFiles(StaticFiles):
        async def get_response(self, path, scope):
            response = await super().get_response(path, scope)
            if Path(path).suffix in (".js", ".css", ".html") or path in ("", "."):
                response.headers["Cache-Control"] = "no-cache"
            return response
    app.mount("/", FreshStaticFiles(directory=DIST, html=True), name="frontend")
