"""Stage 4.5a -- global pairwise geometric-consistency confidence boost, run
before ANMS/MAGSAC.

On repetitive cratered terrain, several *locally* plausible but *globally*
inconsistent correspondences crowd the candidate pool (CLAUDE.md's "known
quality ceiling": ~5-6 of ~32 high-confidence matches are mutually
consistent under any transform). A genuinely correct set of matches must
imply roughly the same scale and rotation between the two images for every
pair of points, since they describe the same rigid-ish scene; a false match
will disagree with most other matches on that implied scale/rotation. This
is the pre-RANSAC voting idea behind PSO-SIFT's "enhanced matching" step
(Ma et al. 2017, IEEE TGRS), adapted here to a generic match list -- source
descriptor-agnostic, so it helps LoFTR, ORB, and crater-constellation
matches alike -- rather than PSO-SIFT's own gradient descriptor.

This boosts confidence rather than filtering outright -- an earlier version
of this module hard-dropped unsupported matches, which measured well on
paper but empirically regressed the real Tycho run from a well-tested
5-inlier homography down to a *different*, degenerate 4-point fit (a
homography has 8 degrees of freedom, so exactly 4 points fit with ~0
residual by construction -- not a validated result, a coincidence). With
only ~5-10% of candidates genuinely correct here, the pairwise-agreement
signal is real (see the module's own diagnostic trace) but too sparse and
too coarse (a 2-parameter scale+rotation proxy for an 8-parameter
homography, which can vary locally across a true projective transform) to
trust as a hard veto. Boosting confidence instead means it can only help
ANMS's per-cell ranking prefer globally-consistent matches, and MAGSAC
still sees the full candidate pool so it can't be starved down to a
degenerate fit by this stage alone.
"""

from __future__ import annotations

import numpy as np

_MIN_BASELINE_PX = 5.0  # ignore pairs too close together to estimate scale/rotation reliably
_SCALE_BIN = 0.05  # log-scale bin width (~5%)
_ANGLE_BIN_DEG = 4.0  # rotation bin width, degrees
_MAX_BOOST = 0.5  # confidence multiplier at full (peak) support, linearly scaled down to 0


def boost_by_global_consistency(matches: list) -> list:
    """Scales each match's confidence up by how many other candidates agree
    with it on implied scale+rotation, relative to the best-supported
    match's agreement count. Never removes a match; a degenerate/too-small
    pool (fewer than 4 matches, or no valid pairs) is returned unchanged."""
    n = len(matches)
    if n < 4:
        return matches

    src = np.array([m.source_xy for m in matches], dtype=np.float64)
    ref = np.array([m.reference_xy for m in matches], dtype=np.float64)

    votes: dict[tuple[int, int], int] = {}
    pair_bins: dict[tuple[int, int], tuple[int, int]] = {}
    for i in range(n):
        src_vec = src - src[i]
        ref_vec = ref - ref[i]
        src_len = np.linalg.norm(src_vec, axis=1)
        ref_len = np.linalg.norm(ref_vec, axis=1)
        src_ang = np.arctan2(src_vec[:, 1], src_vec[:, 0])
        ref_ang = np.arctan2(ref_vec[:, 1], ref_vec[:, 0])

        for j in range(i + 1, n):
            # Two points coinciding on either side give a degenerate (zero-length) baseline
            # that can't imply a scale/rotation -- skip rather than let log(0) reach the bins.
            if src_len[j] <= _MIN_BASELINE_PX or ref_len[j] <= _MIN_BASELINE_PX:
                continue
            log_scale = np.log(ref_len[j] / src_len[j])
            angle_deg = (np.degrees(ref_ang[j] - src_ang[j]) + 180) % 360 - 180

            key = (int(round(log_scale / _SCALE_BIN)), int(round(angle_deg / _ANGLE_BIN_DEG)))
            votes[key] = votes.get(key, 0) + 1
            pair_bins[(i, j)] = key

    if not votes:
        return matches

    # Pick the bin whose 3x3 neighbourhood holds the most total votes (a basin, not a single
    # cell) -- two adjacent bins can split one true cluster right at a quantization edge, and
    # comparing raw per-cell maxima would pick between them arbitrarily.
    def _neighborhood_total(key: tuple[int, int]) -> int:
        return sum(votes.get((key[0] + ds, key[1] + da), 0) for ds in (-1, 0, 1) for da in (-1, 0, 1))

    dominant = max(votes, key=_neighborhood_total)
    neighbor_bins = {(dominant[0] + ds, dominant[1] + da) for ds in (-1, 0, 1) for da in (-1, 0, 1)}

    support = np.zeros(n)
    for (i, j), key in pair_bins.items():
        if key in neighbor_bins:
            support[i] += 1
            support[j] += 1

    peak = support.max()
    if peak <= 0:
        return matches

    for m, s in zip(matches, support):
        m.confidence *= 1.0 + _MAX_BOOST * (s / peak)
    return matches
