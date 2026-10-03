"""Compare the ONNX LoFTR path with kornia/torch on real tiles (reference crop vs a shifted copy)."""
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from algo.matching import learned, loftr_onnx
from algo.api._crops import load_aoi_context
import yaml

cfg = yaml.safe_load(open(Path(__file__).resolve().parents[1] / "configs" / (sys.argv[1] if len(sys.argv) > 1 else "copernicus.yaml")))
ctx = load_aoi_context(cfg, decimation="auto")
ref, src = ctx.reference_crop.astype(np.float32), ctx.source_crop.astype(np.float32)
print("ref", ref.shape, "src", src.shape)
rng = np.random.default_rng(1)


def norm(a):
    a = a[: a.shape[0] // 8 * 8, : a.shape[1] // 8 * 8]
    s = a.max() - a.min()
    return ((a - a.min()) / (s if s > 0 else 1)).astype(np.float32)


matcher = learned._get_matcher()
for size in (128, 256, 384):
    for trial in range(2):
        ry = rng.integers(0, ref.shape[0] - size); rx = rng.integers(0, ref.shape[1] - size)
        sy = rng.integers(0, src.shape[0] - size); sx = rng.integers(0, src.shape[1] - size)
        a, b = norm(src[sy:sy + size, sx:sx + size]), norm(ref[ry:ry + size, rx:rx + size])
        t = time.perf_counter()
        with torch.no_grad():
            o = matcher({"image0": torch.from_numpy(a)[None, None], "image1": torch.from_numpy(b)[None, None]})
        tt = time.perf_counter() - t
        k0t, k1t, ct = o["keypoints0"].numpy(), o["keypoints1"].numpy(), o["confidence"].numpy()
        t = time.perf_counter()
        k0o, k1o, co = loftr_onnx.match(a, b)
        to = time.perf_counter() - t
        d = {tuple(np.round(p, 1)): (q, c) for p, q, c in zip(k0t, k1t, ct)}
        common = [(q, c, d[tuple(np.round(p, 1))]) for p, q, c in zip(k0o, k1o, co) if tuple(np.round(p, 1)) in d]
        err = max((np.abs(q - r[0]).max() for q, c, r in common), default=float("nan"))
        cerr = max((abs(c - r[1]) for q, c, r in common), default=float("nan"))
        print(f"{size}px: torch {len(ct)} matches {tt:.2f}s | onnx {len(co)} matches {to:.2f}s | shared {len(common)} "
              f"max kp diff {err:.3f}px, max conf diff {cerr:.4f}")
