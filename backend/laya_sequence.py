"""Incremental, resumable visual review. AI coverage is not scientific validation."""
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
import numpy as np
from PIL import Image, ImageDraw
from fastapi import HTTPException
from .archive import CACHE, ROOT, key_for, atomic_json
from .analysis import load_products
from .quicklook import standardized, comparable, change_masks
from .laya_review import availability, infer, LOCK, ReviewCancelled

TASKS = {}
TASK_LOCK = threading.RLock()
VERSION = 'incremental-crops-v1'
TILE = 64
STRIDE = 48
IDLE_TIMEOUT = 120


def utc():
    return datetime.now(timezone.utc).isoformat()


def sequence_identity(job):
    model = ROOT/'runtime/laya-model-revision.json'
    revision = model.read_text() if model.exists() else 'unavailable'
    return 'laya-seq-'+key_for('|'.join([VERSION, revision, str(float(job['ra'])),
        str(float(job['dec'])), str(float(job['fov']))]+sorted(f['id'] for f in job['frames'])))


def filter_decisions(result):
    # Kept for older receipt readers. Batch model judgments do not certify tracks.
    for batch in result.get('batches', []):
        batch.setdefault('raw_model_choice', batch.get('choice', 'uncertain'))
        if len(batch['frames']) < 2:
            batch['choice'] = 'uncertain'
    for track in result.get('tracks', []):
        ids = {p['frame'] for p in track['points']}
        track['model_supported'] = any(b['group'] == track['group'] and
            b['choice'] == 'shifted position' and len(ids.intersection(b['frames'])) >= 2
            for b in result.get('batches', []))
    result['supported_motion_candidates'] = sum(t['model_supported'] for t in result.get('tracks', []))
    return result


def tiles(shape):
    h, w = shape
    def starts(n):
        return sorted(set(list(range(0, max(1, n-TILE+1), STRIDE))+[max(0, n-TILE)]))
    return [(x, y, min(w, x+TILE), min(h, y+TILE)) for y in starts(h) for x in starts(w)]


def pixel_compatibility(a, b):
    if a['value'].shape != b['value'].shape:
        return np.zeros(a['value'].shape, bool)
    if 'wavelength' not in a or 'wavelength' not in b:
        return np.zeros(a['value'].shape, bool)
    wa, wb = a['wavelength'], b['wavelength']
    return (np.isfinite(a['value']) & np.isfinite(b['value']) &
        np.isfinite(a['variance']) & (a['variance'] > 0) &
        np.isfinite(b['variance']) & (b['variance'] > 0) &
        np.isfinite(wa) & np.isfinite(wb) & (np.abs(wa-wb) <= .025))


def crop_sheet(pair, box, compatible):
    """Signed continuous stretch retains subthreshold values; no faint-source cut."""
    x0, y0, x1, y1 = box
    sheet = Image.new('RGB', (512, 288), '#10151c')
    draw = ImageDraw.Draw(sheet)
    for index, (frame, product) in enumerate(pair):
        _, _, snr, valid = standardized(product)
        s = snr[y0:y1, x0:x1]
        # Same fixed -5..+20 sigma asinh transform in every panel.
        v = np.clip((np.arcsinh(np.nan_to_num(s)/2)+np.arcsinh(2.5)) /
                    (np.arcsinh(10)+np.arcsinh(2.5)), 0, 1)
        rgb = np.repeat((v*235).astype('u1')[..., None], 3, axis=-1)
        rgb[~valid[y0:y1, x0:x1]] = [35, 45, 57]
        rgb[~compatible[y0:y1, x0:x1]] = [35, 45, 57]
        im = Image.fromarray(np.flipud(rgb)).resize((256, 256), Image.Resampling.NEAREST)
        sheet.paste(im, (index*256, 32))
        draw.text((index*256+3, 2), frame['date'][:10]+' D'+str(frame['detector']), fill='white')
        draw.text((index*256+3, 16), frame['id'][:20], fill='white')
    return sheet


def checkpoint(task, persist=True, **updates):
    with TASK_LOCK:
        task.update(updates, updated_at=utc())
        if persist:
            atomic_json(CACHE/(task['id']+'.json'), task)


def summarize(task, job, prepared):
    frames = job['frames']
    coverage = task['coverage']
    loaded = [f for f in frames if f.get('status') == 'ready']
    reviewed = [fid for fid, c in coverage.items() if c['eligible_tiles'] and
                len(c['reviewed_tiles']) == c['eligible_tiles']]
    task.update(discovered=len(frames), total=len(frames), loaded=len(loaded),
        prepared=len(prepared), reviewed=len(reviewed), reviewed_ids=sorted(reviewed),
        unassessed=max(0,len(loaded)-len(reviewed)),
        failed_downloads=sum(f.get('status') == 'error' for f in frames),
        pending_downloads=sum(f.get('status') not in ('ready', 'error') for f in frames),
        pending_review=max(0, len(frames)-len(reviewed)),
        review_compatible=sum(c['eligible_tiles'] > 0 for c in coverage.values()),
        scientifically_comparable=0, scientific_assessment='uncertain',
        batches_done=len(task['batches']),
        failed_count=len(task['failed'])+sum(f.get('status') == 'error' for f in frames))
    task['exposures'] = [dict(id=f['id'], index=f['index'], date=f['date'], mjd=f['mjd'],
        detector=f.get('detector'), wavelength_um=f.get('wavelength_um'), url=f['url'],
        load_status=f['status'], prepared=f['id'] in prepared, reviewed=f['id'] in reviewed,
        coverage=coverage.get(f['id']), error=f.get('error')) for f in frames]


def plan_crops(task, prepared, completed):
    work = {}
    coverage_by_batch = {}
    entries = list(prepared.values())
    for frame, product in entries:
        if task.get("cancelled"):
            raise ReviewCancelled("Review cancelled while preparing crops. Completed crops are saved.")
        fid = frame["id"]
        boxes = tiles(product["value"].shape)
        coverage = task["coverage"].setdefault(fid, dict(
            total_tiles=len(boxes), eligible_tiles=0, reviewed_tiles=[],
            compatible_pixels=0, total_pixels=int(product["value"].size),
            reason="No loaded calibration-compatible, same-detector temporal reference with compatible wavelength pixels."))
        assignments = task["assignments"].setdefault(fid, {})
        options = [(other, data) for other, data in entries if other["id"] != fid and comparable(frame, other)]
        options.sort(key=lambda entry: (-abs(entry[0]["mjd"]-frame["mjd"]), entry[0]["id"]))
        union = np.zeros(product["value"].shape, bool)
        pending = {str(i): box for i, box in enumerate(boxes)
                   if assignments.get(str(i)) not in prepared}
        existing = {}
        for i, box in enumerate(boxes):
            ref_id = assignments.get(str(i))
            if ref_id in prepared:
                existing.setdefault(ref_id, {})[str(i)] = box

        for reference, rp in options:
            ref_id = reference["id"]
            assigned = existing.get(ref_id, {})
            if not pending and not assigned:
                continue
            compatible = pixel_compatibility(product, rp)
            for tile_id, box in {**pending, **assigned}.items():
                x0, y0, x1, y1 = box
                crop = compatible[y0:y1, x0:x1]
                if crop.sum() < 9:
                    continue
                pending.pop(tile_id, None)
                assignments[tile_id] = ref_id
                union[y0:y1, x0:x1] |= crop
                key = key_for("|".join(sorted([fid, ref_id])) + "|" + str(box))
                if key in completed:
                    if tile_id not in coverage["reviewed_tiles"]:
                        coverage["reviewed_tiles"].append(tile_id)
                else:
                    pair = sorted([(frame, product), (reference, rp)], key=lambda entry: entry[0]["mjd"])
                    work.setdefault(key, (key, pair, box))
                    coverage_by_batch.setdefault(key, []).append((coverage, tile_id))
        coverage["eligible_tiles"] = len(assignments)
        coverage["compatible_pixels"] = int(union.sum())
        coverage["compatible_fraction"] = float(union.mean())
        if assignments:
            coverage["reason"] = ("Preliminary WCS-WAVE pixel compatibility only. "
                                  "Unmatched or flagged pixels remain unreviewed. PSF and field-star registration are unvalidated.")
    return deque(work.values()), coverage_by_batch


def run_sequence(job, task):
    prepared = {}
    attempted = set()
    # Durable completed crop receipts survive cancellation, failure and restart.
    completed = {b['key'] for b in task['batches']}
    last_input = time.monotonic()
    previous_ready = -1
    planned = -1
    try:
        while True:
            if task.get('cancelled'):
                raise ReviewCancelled('Review cancelled. Completed crops are saved; press Review / resume to continue.')
            ready = sorted((f for f in job['frames'] if f.get('status') == 'ready'), key=lambda f:(f['mjd'], f['id']))
            if len(ready) != previous_ready:
                last_input = time.monotonic()
                previous_ready = len(ready)
            task['loaded'] = len(ready)
            for f in ready:
                if f['id'] in prepared or f['id'] in attempted:
                    continue
                attempted.add(f['id'])
                checkpoint(task, persist=False, stage='preparing_images', message='Preparing loaded exposure '+f['id'])
                try:
                    p = load_products(f)
                    standardized(p)
                    prepared[f['id']] = (dict(f), p)
                    task.update(prepared=len(prepared), last_progress_at=utc())
                except Exception as exc:
                    task['failed'].append(dict(id=f['id'], stage='preparation', error=type(exc).__name__+': '+str(exc)))
            if len(prepared) != planned:
                work, coverage_by_batch = plan_crops(task, prepared, completed)
                planned = len(prepared)
            summarize(task, job, prepared)
            if work:
                key, pair, box = work.popleft()
                compatible = pixel_compatibility(pair[0][1], pair[1][1])
                file = CACHE/(task['id']+'-'+key+'.png')
                crop_sheet(pair, box, compatible).save(file)
                checkpoint(task, stage='waiting_model', message='Waiting for local model; '+str(task['reviewed'])+' exposures covered so far.',
                           active_exposures=[f['id'] for f, _ in pair], active_crop=list(box), pending_crop_batches=len(work)+1)
                deadline = time.monotonic()+120
                while not LOCK.acquire(timeout=.25):
                    if task.get('cancelled'):
                        raise ReviewCancelled('Review cancelled while waiting for the model.')
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Model busy for 120s; saved progress retained. Cancel the other review or resume later.')
                try:
                    note = ('Two chronological real SPHEREx crops; dates and exposure IDs shown. '+
                        'Same detector and compatible archive calibration, at least one day apart. Only pixels within 0.025 micrometers shown. '+
                        'Signed continuous -5..20 sigma asinh display; no faint-value cutoff. Masked pixels unknown. '+
                        '64 or fewer registered pixels across each 256px panel. Approximate wavelength map; '+
                        'PSF differences, astrometric errors, background estimation and correlated noise remain uncertain. '+
                        'Describe visual change only, not motion detection or chemical identification.')
                    result = infer(file, note, cancelled=lambda: task.get('cancelled', False),
                        progress=lambda stage: checkpoint(task, persist=False, stage=stage, last_progress_at=utc(), message='Local Laya: '+stage.replace('_', ' ')))
                finally:
                    LOCK.release()
                answer = result.get('answers', {}).get('change', {})
                if not isinstance(answer, dict) or not isinstance(answer.get('choice'), str):
                    raise ValueError('Laya returned no usable change choice; crop not counted as reviewed.')
                x0, y0, x1, y1 = box
                measured = change_masks(pair[1][1], pair[0][1])
                batch = dict(key=key, frames=[f['index'] for f, _ in pair], exposure_ids=[f['id'] for f, _ in pair],
                    dates=[f['date'] for f, _ in pair], crop=list(box), group='D'+str(pair[0][0]['detector']),
                    choice=answer['choice'], completed_at=utc(), scientific_assessment='uncertain',
                    measured_residual_pixels=int(measured['red'][y0:y1, x0:x1].sum()),
                    compatible_pixels=int(compatible[y0:y1, x0:x1].sum()),
                    note='Model suggestion separate from measured residuals; no calibrated detection probability.')
                task['batches'].append(batch)
                completed.add(key)
                for coverage, tile_id in coverage_by_batch[key]:
                    if tile_id not in coverage['reviewed_tiles']:
                        coverage['reviewed_tiles'].append(tile_id)
                summarize(task, job, prepared)
                checkpoint(task, last_progress_at=utc(), pending_crop_batches=len(work))
                continue
            pending = any(f.get('status') not in ('ready', 'error') for f in job['frames'])
            if pending and job.get('status') in ('querying', 'fetching') and time.monotonic()-last_input < IDLE_TIMEOUT:
                if task.get('stage') != 'waiting_images':
                    checkpoint(task, stage='waiting_images', message='No new compatible crop ready; archive is '+job['status']+'. Review resumes as images arrive.')
                time.sleep(.5)
                continue
            status = 'paused' if pending else ('complete' if task['reviewed'] == task['total'] else 'partial')
            checkpoint(task, status=status, stage='waiting_images' if pending else 'finished',
                message=f"{task['reviewed']} / {task['total']} exposures have all eligible crops reviewed. " +
                    ('Input is paused or stalled; resume image loading and review.' if pending else 'Unmatched exposures remain unassessed; see coverage.'),
                last_progress_at=task.get('last_progress_at'), pending_crop_batches=0)
            return
    except ReviewCancelled as exc:
        summarize(task, job, prepared)
        checkpoint(task, status='cancelled', stage='cancelled', message=str(exc))
    except Exception as exc:
        summarize(task, job, prepared)
        task['failed'].append(dict(stage=task.get('stage'), exposure_ids=task.get('active_exposures', []), error=type(exc).__name__+': '+str(exc)))
        checkpoint(task, status='error', stage='failed', failed_count=len(task['failed'])+task['failed_downloads'], message=type(exc).__name__+': '+str(exc))


def public_status(task, summary):
    if summary:
        excluded = ('batches', 'coverage', 'exposures', 'assignments', 'reviewed_ids', 'failed')
        return {k: v for k, v in task.items() if k not in excluded} | {'review_errors': len(task['failed'])}
    return json.loads(json.dumps(task))


def load_review(identity, summary=False):
    """Snapshot the active review or read its persisted receipt."""
    if not identity.startswith('laya-seq-') or not identity.removeprefix('laya-seq-').isalnum():
        raise HTTPException(404, 'Unknown review')
    with TASK_LOCK:
        task = TASKS.get(identity)
        if task is not None:
            return public_status(task, summary)
        receipt = CACHE/(identity+'.json')
        if not receipt.is_file():
            raise HTTPException(404, 'Unknown review')
        try:
            saved = json.loads(receipt.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            raise HTTPException(503, 'The saved review is temporarily unreadable.') from None
        if saved.get('status') == 'running':
            saved.update(status='interrupted', stage='interrupted',
                message='Server restarted. Repeat the same field search and press Review / resume; completed crops are retained.')
        return public_status(saved, True) if summary else saved


def install_sequence_routes(app, jobs, guard):
    @app.post('/api/jobs/{jobid}/laya-sequence')
    def start(jobid: str, summary: bool = False):
        model = availability()
        if not model['installed']:
            missing = ', '.join(model['missing']) or 'Laya package in the runtime environment'
            raise HTTPException(503, 'Local Laya is missing '+missing+'. Run scripts/setup_laya.py.')
        with guard:
            if jobid not in jobs:
                raise HTTPException(404, 'Observation session expired; repeat the coordinate search to resume saved review.')
            job = jobs[jobid]
            if not job['frames']:
                raise HTTPException(425, 'Archive discovery has not finished; no exposures are known yet.')
        identity = sequence_identity(job)
        with TASK_LOCK:
            if identity in TASKS and TASKS[identity]['status'] == 'running':
                return public_status(TASKS[identity], summary)
            if any(t['status'] == 'running' for t in TASKS.values()):
                raise HTTPException(429, 'Another sequence review is running. Cancel it or wait.')
            receipt = CACHE/(identity+'.json')
            saved = json.loads(receipt.read_text()) if receipt.exists() else {}
            task = dict(id=identity, version=VERSION, status='running', stage='preparing_images',
                ra=job['ra'], dec=job['dec'], fov=job['fov'],
                total=len(job['frames']), discovered=len(job['frames']), loaded=sum(f['status']=='ready' for f in job['frames']), prepared=0, reviewed=saved.get('reviewed',0),
                failed=[], failed_count=0, batches=saved.get('batches', []), batches_done=len(saved.get('batches', [])),
                coverage=saved.get('coverage', {}), exposures=saved.get('exposures', []), assignments=saved.get('assignments', {}), tracks=[],
                supported_motion_candidates=0, scientifically_comparable=0,
                started_at=utc(), last_progress_at=saved.get('last_progress_at'), cancelled=False,
                message='Reviewing available temporal crops while archive loading continues.',
                note='Reviewed counts unique exposures with every eligible tile reviewed, not all pixels or all dates. Coverage lists masked/unmatched pixels. Scientific motion suitability remains uncertain: precision bandpass calibration, PSF matching, field-star registration and systematics are unvalidated. Laya is a general visual model; suggestions are not detections or probabilities.')
            TASKS[identity] = task
            threading.Thread(target=run_sequence, args=(job, task), daemon=True).start()
            return public_status(task, summary)

    @app.get('/api/laya/sequence/{identity}')
    def poll(identity: str, summary: bool = False):
        return load_review(identity, summary)

    @app.get('/api/laya/sequence/{identity}/report')
    def report(identity: str, compact: bool = False):
        from .laya_report import build_report
        return build_report(load_review(identity), sample_limit=6 if compact else 0)

    @app.post('/api/laya/sequence/{identity}/cancel')
    def cancel(identity: str):
        with TASK_LOCK:
            if identity not in TASKS:
                raise HTTPException(404, 'Unknown review')
            task = TASKS[identity]
            task['cancelled'] = True
            return dict(id=identity, cancellation_requested=True, status=task['status'])
