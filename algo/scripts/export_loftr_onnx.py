"""Export kornia's LoFTR (outdoor weights) to two ONNX graphs and check them against torch.

    python scripts/export_loftr_onnx.py

kornia's LoFTR forward has data-dependent glue (mutual-NN selection, window gathering) that does
not trace, so the network is split at those points:

    loftr_coarse.onnx : image0, image1 -> feat_c0, feat_c1 (after coarse transformer), feat_f0, feat_f1
    loftr_fine.onnx   : fine windows + coarse features -> refined fine features
    (the selection / gathering / soft-argmax in between is plain numpy: algo/matching/loftr_onnx.py)

Downloads the official checkpoint first if models/loftr_outdoor.ckpt is missing (kornia's own URL is dead,
so it comes from the official kornia HuggingFace org). Needs torch + kornia + onnx (pip install -r
requirements-export.txt); the app itself needs only onnxruntime.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import torch
import kornia.feature as KF

ROOT = Path(__file__).resolve().parents[1]
CKPT = ROOT / "models" / "loftr_outdoor.ckpt"
OUT_DIR = ROOT / "models"


class Coarse(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, a, b):
        (c0, f0), (c1, f1) = self.m.backbone(a), self.m.backbone(b)
        c0 = self.m.pos_encoding(c0).permute(0, 2, 3, 1)
        c1 = self.m.pos_encoding(c1).permute(0, 2, 3, 1)
        n, h, w, c = c0.shape
        c0 = c0.reshape(n, -1, c)
        n1, h1, w1, c1_ = c1.shape
        c1 = c1.reshape(n1, -1, c1_)
        c0, c1 = self.m.loftr_coarse(c0, c1, None, None)
        return c0, c1, f0, f1


class Fine(torch.nn.Module):
    def __init__(self, m):
        super().__init__()
        self.m = m

    def forward(self, f0, f1, c0, c1):
        # f0, f1: [M, WW, 128]; c0, c1: [M, 256]
        fp = self.m.fine_preprocess
        M, WW, _ = f0.shape
        c_win = fp.down_proj(torch.cat([c0, c1], 0))  # [2M, 128]
        merged = fp.merge_feat(torch.cat([torch.cat([f0, f1], 0), c_win.unsqueeze(1).repeat(1, WW, 1)], -1))
        g0, g1 = torch.chunk(merged, 2, dim=0)
        g0, g1 = self.m.loftr_fine(g0, g1)
        return g0[:, WW // 2, :], g1  # only image0's centre feature is used by the fine matcher


def ensure_checkpoint():
    if CKPT.exists():
        return
    import urllib.request

    CKPT.parent.mkdir(parents=True, exist_ok=True)
    url = "https://huggingface.co/kornia/loftr/resolve/main/loftr_outdoor.ckpt"
    print("downloading", url)
    urllib.request.urlretrieve(url, CKPT)


def load():
    ensure_checkpoint()
    m = KF.LoFTR(pretrained=None)
    m.load_state_dict(torch.load(CKPT, map_location="cpu")["state_dict"])
    return m.eval()


def main():
    m = load()
    a, b = torch.rand(1, 1, 256, 320), torch.rand(1, 1, 288, 240)
    with torch.no_grad():
        torch.onnx.export(
            Coarse(m), (a, b), str(OUT_DIR / "loftr_coarse.onnx"), input_names=["image0", "image1"],
            output_names=["feat_c0", "feat_c1", "feat_f0", "feat_f1"],
            dynamic_axes={"image0": {2: "h0", 3: "w0"}, "image1": {2: "h1", 3: "w1"},
                          "feat_c0": {1: "l0"}, "feat_c1": {1: "l1"},
                          "feat_f0": {2: "fh0", 3: "fw0"}, "feat_f1": {2: "fh1", 3: "fw1"}},
            opset_version=17, dynamo=False)
        M = 50
        args = (torch.rand(M, 25, 128), torch.rand(M, 25, 128), torch.rand(M, 256), torch.rand(M, 256))
        torch.onnx.export(
            Fine(m), args, str(OUT_DIR / "loftr_fine.onnx"), input_names=["f0", "f1", "c0", "c1"],
            output_names=["g0", "g1"],
            dynamic_axes={k: {0: "m"} for k in ["f0", "f1", "c0", "c1", "g0", "g1"]},
            opset_version=17, dynamo=False)
    for n in ["loftr_coarse.onnx", "loftr_fine.onnx"]:
        print(n, round((OUT_DIR / n).stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    sys.exit(main())
