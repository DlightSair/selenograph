"""LoFTR (outdoor) on ONNX Runtime + numpy: no torch or kornia at run time.

Reproduces kornia.feature.LoFTR's forward for inference (batch 1, dual-softmax coarse matching,
5x5 fine windows). The two network parts are exported by scripts/export_loftr_onnx.py to
models/loftr_coarse.onnx and models/loftr_fine.onnx; this file does the data-dependent glue
between them (mutual-nearest-neighbour selection, window gathering, soft-argmax refinement).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

import sys

_MODELS = Path(getattr(sys, "_MEIPASS", "")) / "models" if getattr(sys, "frozen", False) else Path(__file__).parents[3] / "models"
_THR, _BORDER, _TEMP = 0.2, 2, 0.1
_W, _STRIDE_C, _SCALE_F = 5, 4, 2.0  # fine window, fine px per coarse cell, image px per fine px

_sessions: tuple | None = None


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except ImportError:
        return False
    return (_MODELS / "loftr_coarse.onnx").exists() and (_MODELS / "loftr_fine.onnx").exists()


def _load():
    global _sessions
    if _sessions is None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.log_severity_level = 3
        _sessions = tuple(
            ort.InferenceSession(str(_MODELS / n), so, providers=["CPUExecutionProvider"])
            for n in ("loftr_coarse.onnx", "loftr_fine.onnx")
        )
    return _sessions


def _softmax(x, axis):
    e = np.exp(x - x.max(axis=axis, keepdims=True))
    return e / e.sum(axis=axis, keepdims=True)


def _windows(feat, ids, wc):
    """feat [1, C, Hf, Wf] -> [M, W*W, C] windows centred on the fine pixel of each coarse cell."""
    pad = _W // 2
    f = np.pad(feat[0], ((0, 0), (pad, pad), (pad, pad)))
    rows, cols = ids // wc, ids % wc
    out = np.empty((len(ids), _W * _W, f.shape[0]), np.float32)
    for k, (r, c) in enumerate(zip(rows, cols)):
        win = f[:, r * _STRIDE_C:r * _STRIDE_C + _W, c * _STRIDE_C:c * _STRIDE_C + _W]  # [C, W, W]
        out[k] = win.reshape(f.shape[0], -1).T
    return out


def match(image0: np.ndarray, image1: np.ndarray):
    """image0/1: float32 [H, W] in [0, 1], H and W multiples of 8.
    Returns (keypoints0 [N,2], keypoints1 [N,2], confidence [N]) like kornia's LoFTR."""
    coarse, fine = _load()
    h0, w0 = image0.shape
    h1, w1 = image1.shape
    c0, c1, f0, f1 = coarse.run(None, {"image0": image0[None, None], "image1": image1[None, None]})
    hc0, wc0, hc1, wc1 = h0 // 8, w0 // 8, h1 // 8, w1 // 8

    d = c0.shape[-1] ** 0.5  # kornia normalises both feature maps by sqrt(C) before the similarity
    sim = np.einsum("nlc,nsc->nls", c0 / d, c1 / d) / _TEMP
    conf = _softmax(sim, 1) * _softmax(sim, 2)  # [1, L, S]
    mask = (conf > _THR).reshape(1, hc0, wc0, hc1, wc1)
    b = _BORDER
    mask[:, :b] = mask[:, :, :b] = mask[:, :, :, :b] = mask[:, :, :, :, :b] = False
    mask[:, -b:] = mask[:, :, -b:] = mask[:, :, :, -b:] = mask[:, :, :, :, -b:] = False
    mask = mask.reshape(1, hc0 * wc0, hc1 * wc1)
    mask &= conf == conf.max(axis=2, keepdims=True)
    mask &= conf == conf.max(axis=1, keepdims=True)

    i_ids = np.nonzero(mask[0].any(axis=1))[0]
    if len(i_ids) == 0:
        return np.zeros((0, 2), np.float32), np.zeros((0, 2), np.float32), np.zeros((0,), np.float32)
    j_ids = mask[0].argmax(axis=1)[i_ids]
    mconf = conf[0, i_ids, j_ids].astype(np.float32)
    k0 = np.stack([i_ids % wc0, i_ids // wc0], 1).astype(np.float32) * 8.0
    k1 = np.stack([j_ids % wc1, j_ids // wc1], 1).astype(np.float32) * 8.0

    fw0, fw1 = _windows(f0, i_ids, wc0), _windows(f1, j_ids, wc1)
    g0, g1 = fine.run(None, {"f0": fw0, "f1": fw1, "c0": c0[0, i_ids], "c1": c1[0, j_ids]})
    cdim = g0.shape[1]
    heat = _softmax(np.einsum("mc,mrc->mr", g0, g1) / np.sqrt(cdim), 1).reshape(-1, _W, _W)
    grid = np.linspace(-1.0, 1.0, _W, dtype=np.float32)
    ex = (heat.sum(axis=1) * grid).sum(axis=1)  # expectation over x (columns)
    ey = (heat.sum(axis=2) * grid).sum(axis=1)
    k1 = k1 + np.stack([ex, ey], 1) * (_W // 2) * _SCALE_F
    return k0, k1.astype(np.float32), mconf
