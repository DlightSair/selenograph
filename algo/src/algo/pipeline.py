"""End-to-end orchestration of the registration pipeline. See docs/architecture.md.

Stage order in practice differs slightly from the original design sketch:
illumination normalization (Stage 1) runs lazily per pyramid level inside
the classical matcher rather than once upfront, since it's cheap only on
the much-smaller per-level tiles, not the full multi-hundred-megapixel
source crop.

Accuracy-improvement stages added after the first real end-to-end run (see
CLAUDE.md's "known quality ceiling" and "accuracy improvements" sections),
inserted between matching and the final evaluation:
  4.5a `geometry.consistency` -- pairwise geometric-consistency confidence boost.
  4.5b `preprocessing.relief` -- DTM-based relief-risk confidence weighting.
  5.5  `geometry.refine` -- sub-pixel refinement + guided densification.
Plus a third matcher, `matching.crater` (crater-constellation matching),
added alongside LoFTR/ORB rather than replacing either.
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import yaml

from algo.api._crops import find_source_label_and_grid, load_aoi_context
from algo.evaluation.metrics import evaluate
from algo.export import write_registered_geotiff, write_tiepoints_geo
from algo.geometry.consistency import boost_by_global_consistency
from algo.geometry.refine import refine_and_densify
from algo.geometry.robust_fit import fit_transform
from algo.matching.classical import enforce_uniform_distribution, match_classical
from algo.matching.crater import match_crater
from algo.matching.match import Match
from algo.matching.prior_guided import RefLayer, SourcePyramid
from algo.preprocessing.grid import (
    ControlGrid,
    crop_reference_to_window,
    crop_source_to_aoi,
    load_geometry_grid,
    reference_window_for_source_window,
)
from algo.preprocessing.metadata import load_metadata
from algo.preprocessing.relief import apply_relief_risk_weighting
from algo.pyramid.coarse_to_fine import align_coarse_to_fine
from algo.registration import register


def _find_source_label_and_grid(source_cfg: dict) -> tuple[Path, Path]:
    return find_source_label_and_grid(source_cfg)


def _run_prior_guided(config: dict, run_id: str | None, reg_cfg: dict) -> dict | None:
    """Dense tile matching around the control-grid prior (algo.matching.prior_guided), a robust
    homography, and a cross-validated non-rigid residual field (algo.registration). No fallback to
    blind matching on failure: a reported "no reliable fit" is more useful than a confident-looking
    wrong one (see CLAUDE.md, Copernicus). Returns None when the product has no usable control grid."""
    ctx = load_aoi_context(config, decimation="auto", with_relit=True, with_dem=True)
    prior = ctx.prior_local()
    if prior is None:
        return None
    reference_gsd = ctx.reference_meta.gsd
    layers = [RefLayer(ctx.reference_crop)]
    relit_w = float((reg_cfg.get("relit") or {}).get("weight", 1.0))
    if ctx.relit is not None:
        layers.append(RefLayer(ctx.relit, relit_w))
    pyramid = SourcePyramid(ctx.source_crop, ctx.source_to_full)

    from algo.geometry.parallax import expected_view_tangents

    result = register(pyramid, layers if len(layers) > 1 else ctx.reference_crop, prior, reference_gsd, reg_cfg,
                      dem=ctx.dem, expected_view=expected_view_tangents(ctx.source_meta) if ctx.source_meta else None)
    off_r, off_c = ctx.reference_row_offset, ctx.reference_col_offset
    matches = [Match(m.source_xy, (m.reference_xy[0] + off_c, m.reference_xy[1] + off_r), m.confidence) for m in result.matches]
    inliers = [Match(m.source_xy, (m.reference_xy[0] + off_c, m.reference_xy[1] + off_r), m.confidence) for m in result.inliers]

    extra = {
        "registration_mode": "prior_guided",
        "reference_gsd_m": reference_gsd,
        "source_gsd_m": ctx.source_meta.gsd if ctx.source_meta else None,
        "source_decimation": round(ctx.decimation, 3),
        "stages": result.info.get("stages"),
        "structure": result.info.get("structure_selected") or result.info.get("structure"),
        "capture_candidates": result.info.get("capture_candidates"),
        "relit_layer": ctx.relit is not None,
        "dem_available": ctx.dem is not None,
        "nonrigid": (result.model.info if result.model else None),
    }
    if result.info.get("failed"):
        extra["failure"] = result.info["failed"]

    transform = None
    if result.ok:
        absolute = result.model.with_reference_offset(off_r, off_c)  # source crop px -> reference raster px
        transform = absolute.H
        h, w = ctx.reference_crop.shape
        nr = result.model.to_dict(bounds=(0, 0, w, h))  # field lattice stays in reference-crop-local px
        extra["_transform_extra"] = {
            "reference_offset": {"row": off_r, "col": off_c},
            "source_decimation": ctx.decimation,
            "nonrigid": {k: v for k, v in nr.items() if k != "homography"},
        }
        info = result.model.info
        cv_px = info.get("cv_rmse_nonrigid_px") if result.model.field_fn is not None else info.get("cv_rmse_homography_px")
        if cv_px is not None and cv_px > 0:  # 0 means "no cell could be held out": no claim
            extra["heldout_rmse_px"] = cv_px
            extra["heldout_rmse_m"] = round(cv_px * reference_gsd, 3)
        if result.model.field_fn is not None:
            # how far everything the model adds beyond its homography (DEM parallax + smooth field) moves the inliers
            from algo.geometry.analysis import apply_homography

            src_in = np.array([m.source_xy for m in result.inliers])
            disp = result.model.displacement(apply_homography(result.model.H, src_in))
            extra["nonrigid_field_rms_m"] = round(float(np.sqrt(np.mean(np.sum(disp**2, axis=1)))) * reference_gsd, 3)
    run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    metrics = evaluate(matches, inliers, transform, config["evaluation"], run_id=run_id, extra=extra, rmse_px=result.rmse_px)
    if result.ok and config["evaluation"].get("write_registered", True):
        out_dir = Path(config["evaluation"]["output_dir"]) / run_id
        write_registered_geotiff(out_dir / "registered.tif", result.model, ctx.source_crop, ctx.source_to_full,
                                 ctx.reference_crop.shape, ctx.reference_transform, ctx.reference_crs, off_r, off_c)
        write_tiepoints_geo(out_dir / "tiepoints_geo.csv", inliers, ctx.reference_transform, ctx.reference_crs, ctx.source_window)
    return metrics


def run(config: dict, run_id: str | None = None) -> dict:
    reg_cfg = config.get("registration", {})
    if reg_cfg.get("mode", "prior_guided") == "prior_guided":
        result = _run_prior_guided(config, run_id, reg_cfg)
        if result is not None:
            return result
        # No usable control grid: fall through to blind global matching below.

    source_meta, reference_meta = load_metadata(config["source"], config["reference"])

    label_path, grid_csv = _find_source_label_and_grid(config["source"])
    aoi = config["aoi"]
    source_crop, source_window = crop_source_to_aoi(
        label_path, grid_csv, aoi["lat_min"], aoi["lat_max"], aoi["lon_min"], aoi["lon_max"]
    )

    # Shape-match the reference crop to the source swath's actual footprint,
    # not the whole exported reference tile -- a narrow push-broom strip
    # barely overlaps a square AOI export, which starves the matcher.
    grid = grid_csv if isinstance(grid_csv, ControlGrid) else load_geometry_grid(grid_csv)
    with rasterio.open(config["reference"]["path"]) as ds:
        reference_transform, reference_crs = ds.transform, ds.crs
    reference_window = reference_window_for_source_window(grid, source_window, reference_transform, reference_crs)
    reference_crop = crop_reference_to_window(config["reference"]["path"], reference_window)
    reference_row_offset, reference_col_offset = reference_window[0], reference_window[2]

    levels = align_coarse_to_fine(
        source_crop.astype(np.float64), reference_crop, source_meta.gsd, reference_meta.gsd, config["pyramid"]
    )

    matches = []
    for level in levels:
        # Blind fallback (no control grid): classical ORB matching plus crater constellations.
        level_matches = list(match_classical(level, config["matching"]))
        level_matches += match_crater(level, config["matching"])

        # Rescale from level-local pixel coords back to crop-native / full-reference-native coords.
        for m in level_matches:
            matches.append(
                Match(
                    (m.source_xy[0] * level.source_scale, m.source_xy[1] * level.source_scale),
                    (
                        m.reference_xy[0] * level.reference_scale + reference_col_offset,
                        m.reference_xy[1] * level.reference_scale + reference_row_offset,
                    ),
                    m.confidence,
                )
            )

    dem_cfg = config.get("dem", {})
    if dem_cfg.get("enabled"):
        matches = apply_relief_risk_weighting(matches, reference_transform, reference_crs, dem_cfg["path"])

    matches = boost_by_global_consistency(matches)
    matches = enforce_uniform_distribution(matches, config["anms"])
    transform, inliers = fit_transform(matches, config["geometry"])

    # Sub-pixel refine + guided densification (algo.geometry.refine), seeded by the first-pass
    # inliers. Only adopted if it doesn't make things worse -- matches/transform/inliers are
    # replaced together so inlier_ratio stays a meaningful <=1 fraction of its own candidate pool.
    if transform is not None and len(inliers) >= 4:
        refined_matches = refine_and_densify(
            inliers, source_crop, reference_crop, transform, source_meta.gsd, reference_meta.gsd,
            reference_row_offset, reference_col_offset,
        )
        refined_transform, refined_inliers = fit_transform(refined_matches, config["geometry"])
        if refined_transform is not None and len(refined_inliers) >= len(inliers):
            matches, transform, inliers = refined_matches, refined_transform, refined_inliers

    return evaluate(matches, inliers, transform, config["evaluation"], run_id=run_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", default=None, help="Pre-assign the output dir name (used by the API server).")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    results = run(config, run_id=args.run_id)
    print(results)


if __name__ == "__main__":
    main()
