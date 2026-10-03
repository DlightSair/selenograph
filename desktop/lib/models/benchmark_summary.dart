import 'json_util.dart';

/// One variant's results at one difficulty level (`points[].variants[name]`).
class VariantStats {
  final int? n; // synthetic cases run
  final double success; // 0..1: share of cases under the success threshold
  final double? medianRmsePx; // null when every case failed
  final double? medianRmseM;
  final double? p90RmsePx;
  final double? medianPriorRmsePx; // error of the starting guess, for context

  VariantStats({
    this.n,
    required this.success,
    this.medianRmsePx,
    this.medianRmseM,
    this.p90RmsePx,
    this.medianPriorRmsePx,
  });

  factory VariantStats.fromJson(Map<String, dynamic> json) => VariantStats(
        n: asInt(json['n']),
        success: (asDouble(json['success']) ?? 0.0).clamp(0.0, 1.0),
        medianRmsePx: asDouble(json['median_rmse_px']),
        medianRmseM: asDouble(json['median_rmse_m']),
        p90RmsePx: asDouble(json['p90_rmse_px']),
        medianPriorRmsePx: asDouble(json['median_prior_rmse_px']),
      );
}

/// One x position of a panel: the swept value and every variant's result there.
class BenchmarkPoint {
  final double x;
  final String label;
  final Map<String, VariantStats> variants;

  BenchmarkPoint({required this.x, required this.label, required this.variants});

  factory BenchmarkPoint.fromJson(Map<String, dynamic> json) {
    final variants = <String, VariantStats>{};
    final raw = asMap(json['variants']);
    if (raw != null) {
      for (final e in raw.entries) {
        final stats = asMap(e.value);
        if (stats != null) variants[e.key] = VariantStats.fromJson(stats);
      }
    }
    return BenchmarkPoint(
      x: asDouble(json['x']) ?? 0,
      label: asString(json['label']) ?? '',
      variants: variants,
    );
  }
}

/// A chart-ready panel: one swept difficulty, points ordered by x.
class BenchmarkPanel {
  final String suite;
  final String title;
  final String xLabel;
  final List<String> variants;
  final List<BenchmarkPoint> points;

  BenchmarkPanel({
    required this.suite,
    required this.title,
    required this.xLabel,
    required this.variants,
    required this.points,
  });

  factory BenchmarkPanel.fromJson(Map<String, dynamic> json) {
    final points = asMapList(json['points']).map(BenchmarkPoint.fromJson).toList()
      ..sort((a, b) => a.x.compareTo(b.x));
    final rawVariants = json['variants'];
    var variants = rawVariants is List ? [for (final v in rawVariants) if (v is String) v] : <String>[];
    if (variants.isEmpty) {
      // No explicit list: use whatever the points report.
      final seen = <String>{};
      for (final pt in points) {
        seen.addAll(pt.variants.keys);
      }
      variants = seen.toList();
    }
    return BenchmarkPanel(
      suite: asString(json['suite']) ?? '',
      title: asString(json['title']) ?? '',
      xLabel: asString(json['x_label']) ?? '',
      variants: variants,
      points: points,
    );
  }
}

/// A group of related panels (`suites[]`); only its display title is used.
class BenchmarkSuite {
  final String name;
  final String title;

  BenchmarkSuite({required this.name, required this.title});

  factory BenchmarkSuite.fromJson(Map<String, dynamic> json) => BenchmarkSuite(
        name: asString(json['name']) ?? '',
        title: asString(json['title']) ?? asString(json['name']) ?? '',
      );
}

/// Mirrors `GET /benchmarks`: the synthetic ground-truth benchmark, summarised
/// per swept difficulty and algorithm variant.
class BenchmarkSummary {
  final String? generated; // ISO timestamp
  final double successPx; // a case succeeds when its RMS error is under this
  final Map<String, String> variantNotes;
  final List<BenchmarkSuite> suites;
  final List<BenchmarkPanel> panels;

  BenchmarkSummary({
    required this.generated,
    required this.successPx,
    required this.variantNotes,
    required this.suites,
    required this.panels,
  });

  /// Variants in canonical order (the pipeline's progression from the
  /// baseline to the full model), then any unknown ones in first-seen order.
  /// Variants appearing in notes but in no panel are left out.
  List<String> get variants {
    const canonical = ['baseline', 'auto', 'auto+nr', 'auto+nr+dem', 'relit', 'relit+nr', 'relit+nr+dem'];
    final seen = <String>{};
    for (final p in panels) {
      seen.addAll(p.variants);
      for (final pt in p.points) {
        seen.addAll(pt.variants.keys);
      }
    }
    return [
      for (final v in canonical)
        if (seen.contains(v)) v,
      for (final v in seen)
        if (!canonical.contains(v)) v,
    ];
  }

  String suiteTitle(String name) {
    for (final s in suites) {
      if (s.name == name) return s.title;
    }
    return name;
  }

  factory BenchmarkSummary.fromJson(Map<String, dynamic> json) {
    final notes = <String, String>{};
    final rawNotes = asMap(json['variant_notes']);
    if (rawNotes != null) {
      for (final e in rawNotes.entries) {
        if (e.value is String) notes[e.key] = e.value as String;
      }
    }
    return BenchmarkSummary(
      generated: asString(json['generated']),
      successPx: asDouble(json['success_px']) ?? 1.5,
      variantNotes: notes,
      suites: asMapList(json['suites']).map(BenchmarkSuite.fromJson).toList(),
      panels: asMapList(json['panels']).map(BenchmarkPanel.fromJson).toList(),
    );
  }
}
