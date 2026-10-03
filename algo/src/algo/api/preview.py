"""Renders a quick-look preview of a project's source/reference imagery,
cropped to its AOI -- independent of running the full pipeline, so the UI
can show what will actually be registered before committing to a run (and,
just as usefully, why re-running an unchanged project gives the same output
every time: it's the same two crops and the same deterministic fit).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

import cv2
import numpy as np

from algo.api._crops import load_aoi_context

PREVIEW_DIR = Path("../data/previews")


def generate_preview(config: dict, config_name: str, force: bool = False) -> Path:
    out_path = PREVIEW_DIR / f"{config_name}.png"
    if out_path.exists() and not force:
        return out_path

    ctx = load_aoi_context(config, decimation="auto")  # huge strips (OHRC) are block-averaged on read
    source_crop, reference_crop = ctx.source_crop, ctx.reference_crop
    full_h = source_crop.shape[0] * ctx.source_to_full[1, 1]
    full_w = source_crop.shape[1] * ctx.source_to_full[0, 0]

    def shown(a: np.ndarray, long_side: int = 1800) -> np.ndarray:
        a = a.astype(np.float32)
        f = long_side / max(a.shape)
        if f < 1:
            a = cv2.resize(a, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
        valid = a[a > 0]
        lo, hi = np.percentile(valid if valid.size else a, [1, 99.5])
        return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1) ** 0.7

    fig, (ax_s, ax_r) = plt.subplots(1, 2, figsize=(12, 7))
    ax_s.imshow(shown(source_crop), cmap="gray")
    ax_s.set_title(f"Source (Chandrayaan-2) — {int(full_w)}x{int(full_h)}px")
    ax_s.axis("off")
    ax_r.imshow(shown(reference_crop), cmap="gray")
    ax_r.set_title(f"Reference (LRO) — {reference_crop.shape[1]}x{reference_crop.shape[0]}px")
    ax_r.axis("off")

    plt.tight_layout()
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=110)
    plt.close(fig)
    return out_path
