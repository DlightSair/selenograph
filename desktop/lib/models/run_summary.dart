import 'json_util.dart';
import 'run_metrics.dart';

// RunMetrics and its sub-models live in run_metrics.dart; re-exported so
// screens that already import this file keep seeing them.
export 'run_metrics.dart';

class RunTransform {
  final List<List<double>> homography;

  RunTransform({required this.homography});

  factory RunTransform.fromJson(Map<String, dynamic> json) {
    final raw = json['homography'] as List;
    return RunTransform(
      homography: raw
          .map((row) => (row as List).map((v) => (v as num).toDouble()).toList())
          .toList(),
    );
  }
}

/// Mirrors the server's `_load_run` response: a run's own `meta.json` merged
/// with `metrics.json`/`transform.json` if the run has reached that stage.
class RunSummary {
  final String runId;
  final String status; // running | done | error | unknown
  final String? config;
  final String? startedAt;
  final String? finishedAt;
  final String? stderrTail;
  final String? stage;
  final RunMetrics? metrics;
  final RunTransform? transform;

  RunSummary({
    required this.runId,
    required this.status,
    required this.config,
    required this.startedAt,
    required this.finishedAt,
    required this.stderrTail,
    this.stage,
    required this.metrics,
    required this.transform,
  });

  factory RunSummary.fromJson(Map<String, dynamic> json) {
    return RunSummary(
      runId: json['run_id'] as String,
      status: json['status'] as String? ?? 'unknown',
      config: json['config'] as String?,
      startedAt: json['started_at'] as String?,
      finishedAt: json['finished_at'] as String?,
      stderrTail: json['stderr_tail'] as String?,
      stage: json['stage'] as String?,
      metrics: asMap(json['metrics']) != null ? RunMetrics.fromJson(asMap(json['metrics'])!) : null,
      transform: json['transform'] != null
          ? RunTransform.fromJson(json['transform'] as Map<String, dynamic>)
          : null,
    );
  }

  bool get isRunning => status == 'running';
  bool get isDone => status == 'done';
  bool get isError => status == 'error';

  /// The run completed but the matcher reported no reliable fit.
  bool get isNoFit => isDone && (metrics?.failed ?? false);

  /// Status word for the pill: a completed run with no reliable fit reads
  /// "no fit" rather than a green "done".
  String get displayStatus => isNoFit ? 'no fit' : status;
}
