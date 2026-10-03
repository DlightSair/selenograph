import 'json_util.dart';

/// One coarse-to-fine matching stage (`metrics.stages[]`).
class StageInfo {
  final double? down; // working-resolution downsample factor, relative to the reference
  final double? sourceDown;
  final int? tile; // tile size in px
  final int? attempted;
  final int? matched;
  final int? agreeingTiles; // capture stage: tiles agreeing on one global shift
  final int? fitInliers; // later stages: measurements the fit kept
  final double? bar;
  final double? tileNoisePx;
  final List<double>? globalShiftPx;

  StageInfo({
    this.down,
    this.sourceDown,
    this.tile,
    this.attempted,
    this.matched,
    this.agreeingTiles,
    this.fitInliers,
    this.bar,
    this.tileNoisePx,
    this.globalShiftPx,
  });

  /// What the stage table calls "inliers": the fit's inliers, or for the
  /// capture stage the number of tiles that agree on one global shift.
  int? get inliers => fitInliers ?? agreeingTiles;

  factory StageInfo.fromJson(Map<String, dynamic> json) {
    final shift = json['global_shift_px'];
    return StageInfo(
      down: asDouble(json['down']),
      sourceDown: asDouble(json['source_down']),
      tile: asInt(json['tile']),
      attempted: asInt(json['attempted']),
      matched: asInt(json['matched']),
      agreeingTiles: asInt(json['agreeing_tiles']),
      fitInliers: asInt(json['fit_inliers']),
      bar: asDouble(json['bar']),
      tileNoisePx: asDouble(json['tile_noise_px']),
      globalShiftPx: shift is List ? [for (final v in shift) if (asDouble(v) != null) asDouble(v)!] : null,
    );
  }
}

/// One representation's score in the capture-stage vote
/// (`metrics.capture_candidates[name]`).
class CaptureCandidate {
  final int? tiles; // tiles that produced any peak
  final int? attempted;
  final int? agree; // tiles agreeing with the consensus shift
  final double? medianNcc;

  CaptureCandidate({this.tiles, this.attempted, this.agree, this.medianNcc});

  /// Share of attempted tiles that agree with the consensus, 0..1.
  double get agreement {
    final a = attempted;
    final g = agree;
    if (a == null || a <= 0 || g == null) return 0;
    return (g / a).clamp(0.0, 1.0);
  }

  factory CaptureCandidate.fromJson(Map<String, dynamic> json) => CaptureCandidate(
        tiles: asInt(json['tiles']),
        attempted: asInt(json['attempted']),
        agree: asInt(json['agree']),
        medianNcc: asDouble(json['median_ncc']),
      );
}

/// The DEM-parallax coefficients the non-rigid model fitted
/// (`metrics.nonrigid.parallax`).
class ParallaxInfo {
  final double? alphaAlong;
  final double? alphaCross;
  final double? explainedVariance;
  final double? expectedAbsAlphaAlong;
  final double? expectedAbsAlphaCross;
  final double? demReliefM;

  ParallaxInfo({
    this.alphaAlong,
    this.alphaCross,
    this.explainedVariance,
    this.expectedAbsAlphaAlong,
    this.expectedAbsAlphaCross,
    this.demReliefM,
  });

  factory ParallaxInfo.fromJson(Map<String, dynamic> json) => ParallaxInfo(
        alphaAlong: asDouble(json['alpha_along']),
        alphaCross: asDouble(json['alpha_cross']),
        explainedVariance: asDouble(json['explained_variance']),
        expectedAbsAlphaAlong: asDouble(json['expected_abs_alpha_along']),
        expectedAbsAlphaCross: asDouble(json['expected_abs_alpha_cross']),
        demReliefM: asDouble(json['dem_relief_m']),
      );
}

/// The non-rigid residual model's report (`metrics.nonrigid`). A homography
/// alone can't model push-broom jitter or terrain parallax; the field is only
/// adopted when it predicts held-out tiles better.
class NonRigidInfo {
  /// "adopted", "rejected: ..." or "skipped: ..." (the server's `nonrigid` key).
  final String? status;
  final double? cvGainPct;
  final double? fieldRmsPx;
  final double? fieldMaxPx;
  final double? cvRmseHomographyPx;
  final double? cvRmseNonrigidPx;
  final ParallaxInfo? parallax;

  NonRigidInfo({
    this.status,
    this.cvGainPct,
    this.fieldRmsPx,
    this.fieldMaxPx,
    this.cvRmseHomographyPx,
    this.cvRmseNonrigidPx,
    this.parallax,
  });

  bool get adopted => status != null && status!.startsWith('adopted');
  bool get skipped => status != null && status!.startsWith('skipped');

  /// The text after "rejected:" / "skipped:", if any.
  String? get reason {
    final s = status;
    if (s == null) return null;
    final i = s.indexOf(':');
    if (i < 0) return null;
    final r = s.substring(i + 1).trim();
    return r.isEmpty ? null : r;
  }

  factory NonRigidInfo.fromJson(Map<String, dynamic> json) {
    final parallax = asMap(json['parallax']);
    return NonRigidInfo(
      status: asString(json['nonrigid']),
      cvGainPct: asDouble(json['cv_gain_pct']),
      fieldRmsPx: asDouble(json['field_rms_px']),
      fieldMaxPx: asDouble(json['field_max_px']),
      cvRmseHomographyPx: asDouble(json['cv_rmse_homography_px']),
      cvRmseNonrigidPx: asDouble(json['cv_rmse_nonrigid_px']),
      parallax: parallax == null ? null : ParallaxInfo.fromJson(parallax),
    );
  }
}

/// Present when the normal capture failed and the wide search over rotation /
/// scale recovered a badly wrong starting guess (`metrics.rescue`).
class RescueInfo {
  final double? rotationDeg;
  final double? scale;
  final int? hypothesesTried;

  RescueInfo({this.rotationDeg, this.scale, this.hypothesesTried});

  factory RescueInfo.fromJson(Map<String, dynamic> json) => RescueInfo(
        rotationDeg: asDouble(json['rotation_deg']),
        scale: asDouble(json['scale']),
        hypothesesTried: asInt(json['hypotheses_tried']),
      );
}

/// Mirrors a run's `metrics.json`. Everything beyond the original six keys is
/// optional: older runs lack it, and a run that completed without a reliable
/// fit has `failure` set with rmse null and zero inliers/matches.
class RunMetrics {
  final double? rmse;
  final double? rmseM; // RMSE in metres, when the server reports the reference pixel size
  final int inlierCount;
  final double inlierRatio;
  final double? uniformityCov;
  final int matchCount;

  /// Set when the run finished but produced no reliable fit.
  final String? failure;

  /// Image representation the matcher selected ("intensity", "edges", "cfog", ...).
  final String? structure;
  final Map<String, CaptureCandidate> captureCandidates;
  final List<String> structureSwitched;

  final bool? relitLayer; // DEM re-lit with the source's own Sun used as an extra reference layer
  final bool? demAvailable;

  final double? sourceGsdM;
  final double? referenceGsdM;
  final double? sourceDecimation;

  final NonRigidInfo? nonrigid;
  final double? heldoutRmsePx;
  final double? heldoutRmseM; // accuracy on tiles held out by blocked cross-validation
  final double? nonrigidFieldRmsM;

  final List<StageInfo> stages;
  final RescueInfo? rescue;

  RunMetrics({
    required this.rmse,
    this.rmseM,
    this.inlierCount = 0,
    this.inlierRatio = 0,
    required this.uniformityCov,
    this.matchCount = 0,
    this.failure,
    this.structure,
    this.captureCandidates = const {},
    this.structureSwitched = const [],
    this.relitLayer,
    this.demAvailable,
    this.sourceGsdM,
    this.referenceGsdM,
    this.sourceDecimation,
    this.nonrigid,
    this.heldoutRmsePx,
    this.heldoutRmseM,
    this.nonrigidFieldRmsM,
    this.stages = const [],
    this.rescue,
  });

  bool get failed => failure != null && failure!.trim().isNotEmpty;

  /// Source pixel size over reference pixel size (reference px per source px).
  double? get scaleRatio {
    final s = sourceGsdM;
    final r = referenceGsdM;
    return (s != null && r != null && r > 0) ? s / r : null;
  }

  factory RunMetrics.fromJson(Map<String, dynamic> json) {
    final candidates = <String, CaptureCandidate>{};
    final rawCandidates = asMap(json['capture_candidates']);
    if (rawCandidates != null) {
      for (final e in rawCandidates.entries) {
        final c = asMap(e.value);
        if (c != null) candidates[e.key] = CaptureCandidate.fromJson(c);
      }
    }

    final switched = <String>[];
    final rawSwitched = json['structure_switched'];
    if (rawSwitched is List) {
      for (final e in rawSwitched) {
        if (e is Map) {
          final stage = e['stage'];
          final to = e['to'];
          switched.add(stage != null && to != null ? 'stage $stage → $to' : e.toString());
        } else if (e != null) {
          switched.add(e.toString());
        }
      }
    }

    final nonrigid = asMap(json['nonrigid']);
    final rescue = asMap(json['rescue']);
    final rawStructure = json['structure'];
    final failure = json['failure'];

    return RunMetrics(
      rmse: asDouble(json['rmse']),
      rmseM: asDouble(json['rmse_m']),
      inlierCount: asInt(json['inlier_count']) ?? 0,
      inlierRatio: asDouble(json['inlier_ratio']) ?? 0,
      uniformityCov: asDouble(json['uniformity_cov']),
      matchCount: asInt(json['match_count']) ?? 0,
      failure: failure?.toString(),
      structure: rawStructure?.toString(),
      captureCandidates: candidates,
      structureSwitched: switched,
      relitLayer: asBool(json['relit_layer']),
      demAvailable: asBool(json['dem_available']),
      sourceGsdM: asDouble(json['source_gsd_m']),
      referenceGsdM: asDouble(json['reference_gsd_m']),
      sourceDecimation: asDouble(json['source_decimation']),
      nonrigid: nonrigid == null ? null : NonRigidInfo.fromJson(nonrigid),
      heldoutRmsePx: asDouble(json['heldout_rmse_px']),
      heldoutRmseM: asDouble(json['heldout_rmse_m']),
      nonrigidFieldRmsM: asDouble(json['nonrigid_field_rms_m']),
      stages: asMapList(json['stages']).map(StageInfo.fromJson).toList(),
      rescue: rescue == null ? null : RescueInfo.fromJson(rescue),
    );
  }
}
