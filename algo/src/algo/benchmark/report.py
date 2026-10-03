"""Turn the raw benchmark rows (data/benchmark/<suite>.json) into the three things people read:
`summary.json` (served to the desktop app), `docs/benchmark.md` (tables) and one chart per suite.

    python -m algo.benchmark.report
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from algo.benchmark.scenes import REPO

BENCH = REPO / "data" / "benchmark"
DOCS = REPO / "docs"

# (suite, panel title, label regex with the sweep value in group 1, x-axis label)
PANELS = [
    ("illumination", "Sun azimuth difference (elevation 25° both)", r"^az(\d+)$", "Sun azimuth difference (°)"),
    ("illumination", "Source Sun elevation (reference at 25°, same azimuth)", r"^el(\d+)$", "Source Sun elevation (°)"),
    ("prior", "Control-grid prior error: shift", r"^shift(\d+)px$", "Prior shift (reference px)"),
    ("prior", "Control-grid prior error: rotation", r"^rot([\d.]+)deg$", "Prior rotation error (°)"),
    ("prior", "Control-grid prior error: scale", r"^scale([\d.]+)$", "Prior scale error (fraction)"),
    ("scale", "Reference coarser than the source (5 m source vs WAC-like reference)", r"^ref_coarser_x([\d.]+)$", "Scale ratio"),
    ("scale", "Source coarser than the reference (IIRS-like source)", r"^src_coarser_x([\d.]+)$", "Scale ratio"),
    ("viewpoint", "Smooth non-rigid distortion", r"^field([\d.]+)$", "Field RMS (base px = 5 m)"),
    ("viewpoint", "Terrain parallax from a DEM", r"^parallax(\d+)deg$", "Off-nadir view angle (°)"),
]
SUITE_TITLES = {
    "illumination": "Illumination variation",
    "prior": "Viewpoint / pointing error of the starting guess",
    "scale": "Scale variation",
    "viewpoint": "Viewpoint variation (non-rigid, parallax)",
    "combined": "All three at once (Sun azimuth + non-rigid + jitter + parallax)",
}
VARIANT_NOTES = {
    "baseline": "intensity correlation, homography only (behaviour before these improvements)",
    "auto": "representation chosen per scene by capture consensus",
    "auto+nr": "auto + cross-validated non-rigid field",
    "auto+nr+dem": "auto + non-rigid field + DEM parallax model",
    "relit": "auto + DEM re-lit with the source's Sun as a second reference layer",
    "relit+nr": "relit + non-rigid field",
    "relit+nr+dem": "relit + non-rigid field + DEM parallax model",
}


def _stats(rows: list[dict]) -> dict:
    errs = [r["rmse_px"] for r in rows if r.get("rmse_px") is not None]
    ms = [r["rmse_m"] for r in rows if r.get("rmse_m") is not None]
    return {
        "n": len(rows),
        "success": float(np.mean([bool(r.get("ok")) for r in rows])) if rows else 0.0,
        "median_rmse_px": float(np.median(errs)) if errs else None,
        "median_rmse_m": float(np.median(ms)) if ms else None,
        "p90_rmse_px": float(np.percentile(errs, 90)) if errs else None,
        "median_prior_rmse_px": float(np.median([r["prior_rmse_px"] for r in rows if r.get("prior_rmse_px") is not None] or [float("nan")])) if rows else None,
    }


def build_summary() -> dict:
    suites = []
    for path in sorted(BENCH.glob("*.json")):
        if path.name == "summary.json":
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        name = path.stem
        labels = list(dict.fromkeys(r["label"] for r in rows))
        variants = list(dict.fromkeys(r["variant"] for r in rows))
        groups = []
        for label in labels:
            sel = [r for r in rows if r["label"] == label]
            groups.append({"label": label, "variants": {v: _stats([r for r in sel if r["variant"] == v]) for v in variants}})
        suites.append({"name": name, "title": SUITE_TITLES.get(name, name), "variants": variants, "groups": groups})
    # chart-ready panels: one per swept variable, points ordered by the variable's value
    panels = []
    by_name = {s["name"]: s for s in suites}
    for suite, title, rx, xlabel in PANELS:
        if suite not in by_name:
            continue
        pts = []
        for g in by_name[suite]["groups"]:
            m = re.match(rx, g["label"])
            if m:
                pts.append({"x": float(m.group(1)), "label": g["label"], "variants": g["variants"]})
        if pts:
            pts.sort(key=lambda q: q["x"])
            panels.append({"suite": suite, "title": title, "x_label": xlabel, "variants": by_name[suite]["variants"], "points": pts})
    return {"generated": datetime.now(timezone.utc).isoformat(), "success_px": 1.5, "variant_notes": VARIANT_NOTES,
            "suites": suites, "panels": panels}


def _chart(summary: dict) -> list[str]:
    DOCS.mkdir(exist_ok=True)
    made = []
    by_suite = {s["name"]: s for s in summary["suites"]}
    panels = [(sn, t, rx, xl) for sn, t, rx, xl in PANELS if sn in by_suite]
    if not panels:
        return made
    cols = 2
    rows_n = int(np.ceil(len(panels) / cols))
    fig, axes = plt.subplots(rows_n, cols, figsize=(13, 3.9 * rows_n), squeeze=False)
    colours = {"baseline": "#c0392b", "auto": "#2e86c1", "auto+nr": "#1e8449", "auto+nr+dem": "#6c3483", "relit": "#d68910",
               "relit+nr": "#117a65", "relit+nr+dem": "#6c3483"}
    for ax, (sn, title, rx, xl) in zip(axes.ravel(), panels):
        pts = []
        for g in by_suite[sn]["groups"]:
            m = re.match(rx, g["label"])
            if m:
                pts.append((float(m.group(1)), g))
        pts.sort(key=lambda p: p[0])
        for v in by_suite[sn]["variants"]:
            xs = [x for x, g in pts]
            ys = [(g["variants"][v]["median_rmse_px"] if g["variants"][v]["median_rmse_px"] is not None else np.nan) for x, g in pts]
            ok = [g["variants"][v]["success"] * 100 for x, g in pts]
            ax.plot(xs, ys, marker="o", color=colours.get(v, "gray"), label=v)
            for x, y, o in zip(xs, ys, ok):
                if o < 100:
                    ax.annotate(f"{o:.0f}%", (x, y if np.isfinite(y) else 0), textcoords="offset points", xytext=(0, 6), fontsize=7,
                                color=colours.get(v, "gray"), ha="center")
        ax.axhline(1.5, color="black", lw=0.8, ls=":")
        ax.set_yscale("log")
        ax.set_title(title, fontsize=10)
        ax.set_xlabel(xl)
        ax.set_ylabel("median RMS error (reference px)")
        ax.legend(fontsize=7)
        ax.grid(alpha=0.3, which="both")
    for ax in axes.ravel()[len(panels):]:
        ax.axis("off")
    fig.tight_layout()
    out = DOCS / "benchmark.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    made.append(str(out))
    return made


def _markdown(summary: dict) -> str:
    out = ["# Synthetic ground-truth benchmark", "",
           "Every number below is measured against a *known* transform (see `algo/benchmark/`). "
           "A case counts as a success when its RMS error over the whole source frame is under "
           f"{summary['success_px']} reference pixels. Errors are medians over seeds, in reference pixels "
           "(5 m for the NAC-class scenes, 20-100 m when the reference is block-averaged).", "",
           "Variants: " + "; ".join(f"**{k}** — {v}" for k, v in summary["variant_notes"].items()), ""]
    for s in summary["suites"]:
        out += [f"## {s['title']}", "", "| case | prior error (px) | " + " | ".join(s["variants"]) + " |",
                "|---|---|" + "---|" * len(s["variants"])]
        for g in s["groups"]:
            first = next(iter(g["variants"].values()))
            cells = []
            for v in s["variants"]:
                st = g["variants"][v]
                err = "fail" if st["median_rmse_px"] is None else f"{st['median_rmse_px']:.2f} px"
                cells.append(f"{st['success'] * 100:.0f}% · {err}")
            pr = first["median_prior_rmse_px"]
            out.append(f"| {g['label']} | {'—' if pr is None or pr != pr else f'{pr:.0f}'} | " + " | ".join(cells) + " |")
        out.append("")
    return "\n".join(out)


def main():
    summary = build_summary()
    (BENCH / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    DOCS.mkdir(exist_ok=True)
    (DOCS / "benchmark.md").write_text(_markdown(summary), encoding="utf-8")
    charts = _chart(summary)
    print(f"wrote summary.json, docs/benchmark.md, {charts}")


if __name__ == "__main__":
    main()
