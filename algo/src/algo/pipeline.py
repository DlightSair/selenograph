"""End-to-end registration of one project.

`run(config)` loads the AOI crops, builds the control-grid prior, runs the staged tile matcher and the
full model fit (`algo.registration`), writes the metrics and the registered GeoTIFF, and returns the metrics
dict. The configuration format is documented in `configs/default.yaml`.

Command line:  python -m algo.pipeline --config configs/<project>.yaml
"""

import argparse
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import yaml

from algo.api._crops import load_aoi_context
from algo.evaluation.metrics import evaluate
from algo.export import write_registered_geotiff, write_tiepoints_geo
from algo.matching.match import Match
from algo.matching.prior_guided import RefLayer, SourcePyramid
from algo.registration import register


def _register_project(config: dict, run_id: str | None, reg_cfg: dict) -> dict:
    """Dense tile matching around the control-grid prior, a robust homography, and a cross-validated
    non-rigid residual field. A run that finds no reliable fit reports it instead of guessing."""
    ctx = load_aoi_context(config, decimation="auto", with_relit=True, with_dem=True)
    prior = ctx.prior_local()
    if prior is None:
        raise ValueError("the source product has no usable control grid inside the AOI")
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
    """Registers the source to the reference for one project and returns the metrics dict."""
    return _register_project(config, run_id, config.get("registration", {}))


def main():
    parser = argparse.ArgumentParser(description="Register a Chandrayaan-2 source product to its reference.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", default=None, help="Pre-assign the output dir name (used by the API server).")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    results = run(config, run_id=args.run_id)
    print(results)


if __name__ == "__main__":
    main()
