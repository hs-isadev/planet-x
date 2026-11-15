"""Build an evidence report from actual Laya crop receipts."""
from collections import Counter
import math

CHOICES = {
    "shifted position": "possible_position_shift",
    "appeared or brightened": "appeared_or_brightened",
    "disappeared or faded": "disappeared_or_faded",
    "artifact or missing data": "artifact_or_missing_data",
    "stable or no convincing change": "no_convincing_change",
    "uncertain": "uncertain",
}
LIMITATIONS = [
    "Counts describe overlapping crop comparisons. Multiple crops can describe the same signal.",
    "Brightness suggestions are visual comparisons. Laya does not measure flux, a variability period, or intrinsic variability.",
    "A suggested shift does not establish source identity or motion. Check calibrated displacement, masks and registration, then compare independent dates.",
    "Wavelength and detector checks are preliminary. PSF, bandpass, blending, and calibration systematics can mimic changes.",
    "Unassessed exposures and masked pixels provide no evidence for stability or disappearance.",
]

def build_report(task, *, sample_limit=0):
    """Keep full counts even when sending a bounded evidence sample to the guide."""
    exposures = {row["id"]: row for row in task.get("exposures", [])}
    counts = Counter(dict.fromkeys(CHOICES.values(), 0))
    by_category = {category: [] for category in CHOICES.values()}
    rows = []
    seen = set()
    for batch in list(task.get("batches", [])):
        key = batch.get("key")
        ids = batch.get("exposure_ids") or []
        dates = batch.get("dates") or []
        if not key or key in seen or len(ids) != 2 or len(set(ids)) != 2 or len(dates) != 2:
            continue
        seen.add(key)
        category = CHOICES.get(batch.get("choice"), "uncertain")
        frames = [exposures.get(exposure_id, {}) for exposure_id in ids]
        mjds = [f.get("mjd") for f in frames]
        baseline = round(abs(mjds[1] - mjds[0]), 3) if all(
            isinstance(m, (int, float)) and math.isfinite(m) for m in mjds
        ) else None
        row = {
            "comparison_id": key,
            "classification": category,
            "exposure_ids": ids,
            "dates_utc": dates,
            "baseline_days": baseline,
            "detector_group": batch.get("group"),
            "field_center_wavelength_um": [f.get("wavelength_um") for f in frames],
            "registered_crop_xyxy": batch.get("crop"),
            "compatible_pixels": batch.get("compatible_pixels"),
            "significant_residual_pixels": batch.get("measured_residual_pixels"),
            "scientific_assessment": "unvalidated_visual_suggestion",
        }
        counts[category] += 1
        rows.append(row)
        by_category[category].append(row)

    if sample_limit:
        # Show every available class before repeating one; overlapping examples
        # need not be independent even when their comparison IDs differ.
        examples = []
        for offset in range(sample_limit):
            for category in CHOICES.values():
                candidates = by_category[category]
                if offset < len(candidates):
                    examples.append(candidates[offset])
                if len(examples) == sample_limit:
                    break
            if len(examples) == sample_limit:
                break
    loaded = task.get("loaded", 0)
    reviewed = task.get("reviewed", 0)
    return {
        "schema_version": 1,
        "review_id": task["id"],
        "status": task.get("status"),
        "last_progress_at": task.get("last_progress_at"),
        "field": {k: task.get(k) for k in ("ra", "dec", "fov")},
        "coverage": {
            "discovered_exposures": task.get("discovered", task.get("total", 0)),
            "loaded_exposures": loaded,
            "exposures_with_all_eligible_crops_reviewed": reviewed,
            "loaded_exposures_without_a_full_review_of_eligible_crops": max(0, loaded - reviewed),
            "unavailable_cutouts": task.get("failed_downloads", 0),
            "review_errors": len(task.get("failed", [])),
        },
        "completed_comparisons": len(rows),
        "classification_counts": dict(counts),
        "scientific_assessment": "No calibrated displacement or aperture photometry is included in this report.",
        "limitations": LIMITATIONS,
        **({"example_comparisons": examples, "example_count": len(examples)}
           if sample_limit else {"comparisons": rows}),
    }
