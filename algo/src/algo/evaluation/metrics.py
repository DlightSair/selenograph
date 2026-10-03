"""Evaluation metrics: RMSE, inlier count/ratio, spatial uniformity.
Writes metrics.json, matches.csv, transform.json, and a match-overlay PNG to
evaluation_cfg['output_dir']/run_id/.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np


def evaluate(
    matches: list, inliers: list, transform, evaluation_cfg: dict, run_id: str | None = None, extra: dict | None = None,
    rmse_px: float | None = None,
) -> dict:
    """`extra` is merged into metrics.json (e.g. which registration mode ran); if it holds
    `reference_gsd_m`, the RMSE is also reported in metres as `rmse_m`. `rmse_px` overrides the
    homography-only residual when a richer model (homography + non-rigid field) produced the fit.
    A `_transform_extra` entry of `extra` is written into transform.json, not metrics.json."""
    extra = dict(extra or {})
    transform_extra = extra.pop("_transform_extra", {})
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(evaluation_cfg["output_dir"]) / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if transform is None or not inliers:
        results = {
            "rmse": None,
            "inlier_count": 0,
            "inlier_ratio": 0.0,
            "uniformity_cov": None,
            "match_count": len(matches),
            **extra,
        }
        (output_dir / "metrics.json").write_text(json.dumps(results, indent=2))
        return results

    src = np.array([m.source_xy for m in inliers], dtype=np.float64)
    dst = np.array([m.reference_xy for m in inliers], dtype=np.float64)

    projected = cv2.perspectiveTransform(src.reshape(-1, 1, 2).astype(np.float32), transform).reshape(-1, 2)
    residuals = np.linalg.norm(projected - dst, axis=1)
    rmse = float(np.sqrt(np.mean(residuals**2))) if rmse_px is None else float(rmse_px)

    results = {
        "rmse": rmse,
        "inlier_count": len(inliers),
        "inlier_ratio": len(inliers) / len(matches) if matches else 0.0,
        "uniformity_cov": _spatial_uniformity(dst, grid_size=4),
        "match_count": len(matches),
        **extra,
    }
    if extra and "reference_gsd_m" in extra:
        results["rmse_m"] = rmse * extra["reference_gsd_m"]

    (output_dir / "metrics.json").write_text(json.dumps(results, indent=2))
    _write_matches_csv(output_dir / "matches.csv", inliers)
    _write_transform_json(output_dir / "transform.json", transform, transform_extra)

    return results


def _spatial_uniformity(points: np.ndarray, grid_size: int) -> float:
    """Coefficient of variation of inlier counts across a grid_size x grid_size
    grid over the reference frame -- low CoV means matches are spread evenly
    rather than clustered (the "uniform distribution" requirement)."""
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)
    cell_w = (x_max - x_min) / grid_size or 1.0
    cell_h = (y_max - y_min) / grid_size or 1.0

    counts = np.zeros((grid_size, grid_size))
    for x, y in points:
        cx = min(int((x - x_min) / cell_w), grid_size - 1)
        cy = min(int((y - y_min) / cell_h), grid_size - 1)
        counts[cy, cx] += 1

    mean = counts.mean()
    return float(counts.std() / mean) if mean > 0 else float("inf")


def _write_matches_csv(path: Path, matches: list) -> None:
    lines = ["source_x,source_y,reference_x,reference_y,confidence"]
    for m in matches:
        lines.append(f"{m.source_xy[0]},{m.source_xy[1]},{m.reference_xy[0]},{m.reference_xy[1]},{m.confidence}")
    path.write_text("\n".join(lines))


def _write_transform_json(path: Path, transform: np.ndarray, extra: dict | None = None) -> None:
    path.write_text(json.dumps({"homography": transform.tolist(), **(extra or {})}))
