import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/config_details.dart';
import '../models/config_summary.dart';
import '../models/run_summary.dart';
import '../services/api_client.dart';
import '../shell/app_controller.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';
import '../widgets/zoomable_image.dart';
import 'results_screen.dart';

/// One project: the input imagery, the latest run, and every fact about the
/// products arranged in a grid of equal panels so it fits on one screen
/// instead of one long column.
class ProjectDetailScreen extends StatefulWidget {
  final ApiClient api;
  final ConfigSummary config;

  const ProjectDetailScreen({super.key, required this.api, required this.config});

  @override
  State<ProjectDetailScreen> createState() => _ProjectDetailScreenState();
}

class _ProjectDetailScreenState extends State<ProjectDetailScreen> {
  List<RunSummary> _runs = [];
  ConfigDetails? _details;
  bool _starting = false;
  String? _error;
  Timer? _poll;
  int _previewRetryToken = 0;
  AppController? _app;

  // Mean lunar radius 1737.4 km -> km per degree of latitude.
  static const double _kmPerDegree = 1737.4 * math.pi / 180;

  @override
  void initState() {
    super.initState();
    _load();
    _loadDetails();
    _poll = Timer.periodic(const Duration(seconds: 3), (_) => _load());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _app ??= AppScope.maybeRead(context);
    _publishActions();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _app?.registerProject(null);
    super.dispose();
  }

  void _publishActions() {
    final latest = _mostRecentRun;
    _app?.registerProject(ProjectActions(
      run: (_starting || _anyRunInProgress) ? null : _execute,
      openLatest: latest != null && !latest.isRunning ? () => _openRun(latest.runId) : null,
    ));
  }

  Future<void> _load() async {
    try {
      final all = await widget.api.listRuns(limit: 500, config: widget.config.name);
      final mine = all;
      if (!mounted) return;
      setState(() => _runs = mine);
      _publishActions();
    } catch (_) {
      // transient — the next poll tick will retry.
    }
  }

  Future<void> _loadDetails() async {
    try {
      final details = await widget.api.getConfigDetails(widget.config.name);
      if (!mounted) return;
      setState(() => _details = details);
    } catch (_) {
      // Product facts are a nicety; the panels fall back to "—" without them.
    }
  }

  bool get _anyRunInProgress => _runs.any((r) => r.isRunning);

  /// The server returns runs newest-first, so the first entry is the latest.
  RunSummary? get _mostRecentRun => _runs.isEmpty ? null : _runs.first;

  Future<void> _execute() async {
    setState(() {
      _starting = true;
      _error = null;
    });
    _publishActions();
    try {
      final runId = await widget.api.startRun(widget.config.name);
      await _load();
      if (!mounted) return;
      _openRun(runId);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _starting = false);
      _publishActions();
    }
  }

  void _openRun(String runId) {
    Navigator.of(context)
        .push(ptRoute((_) => ResultsScreen(runId: runId, api: widget.api), label: 'Run ${_shortId(runId)}'))
        .then((_) => _load());
  }

  String _shortId(String id) => id.length > 11 ? id.substring(0, 11) : id;

  // ---- formatting ------------------------------------------------------------

  String _num(num? v, {int decimals = 0, String suffix = ''}) {
    if (v == null) return '—';
    return '${NumberFormat.decimalPatternDigits(decimalDigits: decimals).format(v)}$suffix';
  }

  String _size(int? w, int? h) => (w == null || h == null) ? '—' : '${_num(w)} × ${_num(h)} px';

  String _formatTime(String? iso, {bool seconds = false}) {
    if (iso == null) return '—';
    try {
      return DateFormat(seconds ? 'yyyy-MM-dd HH:mm:ss' : 'yyyy-MM-dd HH:mm').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }

  // ---- build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final config = widget.config;
    final latest = _mostRecentRun;
    final busy = _starting || _anyRunInProgress;
    final canOpen = latest != null && !latest.isRunning;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          title: config.displayName,
          subtitle: '${config.sourceInstrument} → reference · ${config.latMin.toStringAsFixed(1)}…${config.latMax.toStringAsFixed(1)}° lat, '
              '${config.lonMin.toStringAsFixed(1)}…${config.lonMax.toStringAsFixed(1)}° lon',
          showBack: true,
          actions: [
            PushButton(
              label: 'View results',
              icon: CupertinoIcons.doc_text_search,
              compact: true,
              onPressed: canOpen ? () => _openRun(latest.runId) : null,
            ),
            PushButton(
              label: _starting ? 'Starting…' : (_anyRunInProgress ? 'Running…' : (latest == null ? 'Run' : 'Run again')),
              icon: CupertinoIcons.play_fill,
              compact: true,
              isDefault: true,
              onPressed: busy ? null : _execute,
            ),
          ],
        ),
        if (_anyRunInProgress) _RunningStrip(run: _runs.firstWhere((r) => r.isRunning)),
        Expanded(
          child: ScreenBody(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (_error != null) ...[
                  Callout(kind: CalloutKind.error, title: 'Run failed to start', child: SelectableText(_error!, style: ui(size: 11.5))),
                  const SizedBox(height: 12),
                ],
                LayoutBuilder(builder: (context, box) {
                  final wide = box.maxWidth >= 860;
                  final imagery = Entrance(child: _imageryPanel());
                  final run = Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Entrance(delay: const Duration(milliseconds: 50), child: _latestRunPanel()),
                      if (_runs.length > 1) ...[
                        const SizedBox(height: 12),
                        Entrance(delay: const Duration(milliseconds: 90), child: _historyPanel()),
                      ],
                    ],
                  );
                  if (!wide) {
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [run, const SizedBox(height: 12), imagery],
                    );
                  }
                  return Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: imagery),
                      const SizedBox(width: 12),
                      SizedBox(width: 340, child: run),
                    ],
                  );
                }),
                const SizedBox(height: 12),
                Entrance(
                  delay: const Duration(milliseconds: 90),
                  child: Panel(
                    title: 'Project information',
                    icon: CupertinoIcons.info,
                    child: LayoutBuilder(builder: (context, box) {
                      final panels = _factPanels(config);
                      return Masonry(
                        columns: Masonry.columnsFor(box.maxWidth, minColumn: 260),
                        weights: [for (final p in panels) p.$2],
                        children: [for (final p in panels) p.$1],
                      );
                    }),
                  ),
                ),
],
            ),
          ),
        ),
      ],
    );
  }

  Widget _imageryPanel() {
    return Panel(
      title: 'Images',
      icon: CupertinoIcons.photo,
      padding: const EdgeInsets.all(8),
      trailing: Text('source · reference', style: captionStyle()),
      child: ZoomableImage(
        url: '${widget.api.previewUrl(widget.config.name)}?retry=$_previewRetryToken',
        title: '${widget.config.displayName} — source & reference',
        height: 372,
        onRetry: () => setState(() => _previewRetryToken++),
      ),
    );
  }

  // ---- latest run --------------------------------------------------------------

  Widget _latestRunPanel() {
    final run = _mostRecentRun;
    if (run == null) {
      return Panel(
        title: 'Last run',
        icon: CupertinoIcons.waveform_path,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('No runs', style: ui(size: 13, weight: FontWeight.w700)),
            const SizedBox(height: 4),
            const Note('No results. Use Run to start registration.'),
          ],
        ),
      );
    }
    final m = run.metrics;
    final children = <Widget>[];
    if (m != null && m.failed) {
      children.add(Callout(
        kind: CalloutKind.warn,
        title: 'No fit',
        child: Text(m.failure!, style: ui(size: 11.5, color: Pt.ink, height: 1.4)),
      ));
    } else if (m != null) {
      children.add(ReadoutBar(items: [
        LcdReadout(
          label: 'RMSE',
          value: m.rmseM != null ? m.rmseM!.toStringAsFixed(m.rmseM! >= 10 ? 1 : 2) : (m.rmse?.toStringAsFixed(2) ?? '—'),
          unit: m.rmseM != null ? 'm' : 'px',
        ),
        LcdReadout(
          label: 'Held-out RMSE',
          value: m.heldoutRmseM != null ? m.heldoutRmseM!.toStringAsFixed(m.heldoutRmseM! >= 10 ? 1 : 2) : '—',
          unit: m.heldoutRmseM != null ? 'm' : null,
        ),
      ]));
      children.add(const SizedBox(height: 10));
      children.add(PropertyTable(labelWidth: 90, rows: [
        Prop('Inliers', '${m.inlierCount} of ${m.matchCount} (${(m.inlierRatio * 100).toStringAsFixed(0)}%)'),
        if (m.structure != null) Prop('Representation', m.structure!, monospace: false),
      ]));
    } else if (run.isRunning) {
      children.add(const Row(children: [Spinner(), SizedBox(width: 8), Text('Registration is running…')]));
    }
    if (run.isError) {
      children.add(Callout(
        kind: CalloutKind.error,
        title: 'Run failed',
        child: Text(
          run.stderrTail?.contains('interrupted') == true
              ? 'Server restarted during run.'
              : 'See run output.',
          style: ui(size: 11.5, height: 1.4),
        ),
      ));
    }
    children.add(const SizedBox(height: 10));
    children.add(PropertyTable(labelWidth: 90, rows: [
      Prop('Run ID', run.runId),
      Prop('Completed', _formatTime(run.finishedAt ?? run.startedAt, seconds: true)),
    ]));
    return Panel(
      title: 'Last run',
      icon: CupertinoIcons.waveform_path,
      trailing: StatusBadge(status: run.displayStatus),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, mainAxisSize: MainAxisSize.min, children: children),
    );
  }

  Widget _historyPanel() {
    final shown = _runs.take(6).toList();
    return Panel(
      title: 'Runs',
      icon: CupertinoIcons.clock,
      trailing: Text('${_runs.length} total', style: captionStyle()),
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < shown.length; i++)
            _HistoryRow(
              run: shown[i],
              when: _formatTime(shown[i].finishedAt ?? shown[i].startedAt),
              odd: i.isOdd,
              onTap: shown[i].isRunning ? null : () => _openRun(shown[i].runId),
            ),
          if (_runs.length > shown.length)
            Padding(
              padding: const EdgeInsets.all(6),
              child: Text('… and ${_runs.length - shown.length} older runs', style: captionStyle()),
            ),
        ],
      ),
    );
  }

  // ---- fact panels -------------------------------------------------------------

  /// (panel, estimated height weight) pairs for the masonry grid.
  List<(Widget, double)> _factPanels(ConfigSummary config) {
    final d = _details;
    final reg = d?.registration;
    final heightKm = (config.latMax - config.latMin) * _kmPerDegree;
    final midLat = (config.latMin + config.latMax) / 2;
    final widthKm = (config.lonMax - config.lonMin) * _kmPerDegree * math.cos(midLat * math.pi / 180);
    final done = _runs.where((r) => r.isDone).length;
    final failed = _runs.where((r) => r.isError).length;
    final lastFinished = _runs.map((r) => r.finishedAt).whereType<String>().fold<String?>(
          null,
          (best, t) => best == null || t.compareTo(best) > 0 ? t : best,
        );
    final sunElevation = d?.sourceSunElevation;
    final lowSun = sunElevation != null && sunElevation < 5;

    final geometry = <Prop>[
      if (d?.cameraLabel != null) Prop('Camera', d!.cameraLabel!, monospace: false),
      if (d?.sourceRoll != null) Prop('Roll', _num(d!.sourceRoll, decimals: 2, suffix: '°')),
      if (d?.sourcePitch != null) Prop('Pitch', _num(d!.sourcePitch, decimals: 2, suffix: '°')),
      if (d?.sourceYaw != null) Prop('Yaw', _num(d!.sourceYaw, decimals: 2, suffix: '°')),
      if (d?.sourceAltitudeKm != null) Prop('Altitude', _num(d!.sourceAltitudeKm, decimals: 1, suffix: ' km')),
    ];

    Widget panel(String title, IconData icon, List<Prop> rows, {Widget? footer}) => GroupBox(
          title: title,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            mainAxisSize: MainAxisSize.min,
            children: [
              PropertyTable(rows: rows),
              if (footer != null) ...[const SizedBox(height: 8), footer],
            ],
          ),
        );

    return [
      (
        panel('AOI', CupertinoIcons.location_solid, [
          Prop('Lat', '${config.latMin.toStringAsFixed(2)} … ${config.latMax.toStringAsFixed(2)} °'),
          Prop('Lon', '${config.lonMin.toStringAsFixed(2)} … ${config.lonMax.toStringAsFixed(2)} °'),
          Prop('Center', '${midLat.toStringAsFixed(2)}, ${((config.lonMin + config.lonMax) / 2).toStringAsFixed(2)} °'),
          Prop('Extent', '≈ ${widthKm.toStringAsFixed(0)} × ${heightKm.toStringAsFixed(0)} km'),
          Prop('Area', '≈ ${_num(widthKm * heightKm)} km²'),
        ]),
        6.0
      ),
      (
        panel('Source', CupertinoIcons.camera_fill, [
          Prop('Instrument', config.sourceInstrument, monospace: false),
          Prop('GSD', _num(d?.sourceGsd, decimals: 2, suffix: ' m/px')),
          Prop('Size', _size(d?.sourceSamples, d?.sourceLines)),
          Prop('Path', config.sourcePath),
        ]),
        6.5
      ),
      (
        panel('Reference', CupertinoIcons.globe, [
          if (d?.referenceProvider != null) Prop('Provider', d!.referenceProvider!, monospace: false),
          if (d?.referenceLayer != null) Prop('Layer', d!.referenceLayer!),
          Prop('GSD', _num(d?.referenceGsd, decimals: 2, suffix: ' m/px')),
          Prop('Size', _size(d?.referenceCols, d?.referenceRows)),
          Prop('Path', config.referencePath),
        ]),
        6.5
      ),
      if (geometry.isNotEmpty) (panel('Geometry', CupertinoIcons.scope, geometry), 1.0 + geometry.length),
      (
        panel(
          'Illumination',
          CupertinoIcons.sun_max_fill,
          [
            Prop('Sun elevation', _num(d?.sourceSunElevation, decimals: 1, suffix: '°')),
            Prop('Sun azimuth', _num(d?.sourceSunAzimuth, decimals: 1, suffix: '°')),
          ],
          footer: lowSun
              ? const Callout(
                  kind: CalloutKind.warn,
                  title: 'Low sun angle',
                  child: Note('Sun elevation below 5 deg. Matching is least reliable.', color: Pt.ink),
                )
              : null,
        ),
        lowSun ? 6.5 : 3.0
      ),
      (
        panel(
          'Settings',
          CupertinoIcons.slider_horizontal_3,
          [
            Prop('Scale ratio', d?.expectedScale != null ? '${d!.expectedScale!.toStringAsFixed(2)} ref px/src px' : '—'),
            if (reg?.mode != null) Prop('Mode', reg!.mode!),
            Prop('DEM', config.demEnabled ? 'enabled' : 'disabled', monospace: false),
          ],
          footer: reg == null || (reg.relit == null && reg.dem == null && reg.nonrigid == null)
              ? null
              : Wrap(
                  spacing: 6,
                  runSpacing: 6,
                  children: [
                    if (reg.relit != null)
                      FlagTag(label: 'Relit DEM', on: reg.relit!, tooltip: 'A DEM re-lit with the source image’s own Sun angle as an extra reference layer.'),
                    if (reg.dem != null) FlagTag(label: 'Parallax', on: reg.dem!, tooltip: 'Terrain-height parallax modelled from the DEM.'),
                    if (reg.nonrigid != null)
                      FlagTag(
                        label: 'Nonrigid',
                        on: reg.nonrigid!,
                        tooltip: 'Cross-validated residual field on top of the homography; only kept if it predicts held-out tiles better.',
                      ),
                  ],
                ),
        ),
        6.0
      ),
      (
        panel('Statistics', CupertinoIcons.chart_bar_square, [
          Prop('Runs', '${_runs.length} total · $done done · $failed failed'),
          Prop('Last completed', _formatTime(lastFinished)),
        ]),
        3.0
      ),
    ];
  }
}

class _RunningStrip extends StatefulWidget {
  final RunSummary run;
  const _RunningStrip({required this.run});

  @override
  State<_RunningStrip> createState() => _RunningStripState();
}

class _RunningStripState extends State<_RunningStrip> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) => mounted ? setState(() {}) : null);
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  String get _elapsed {
    final s = DateTime.tryParse(widget.run.startedAt ?? '');
    if (s == null) return '';
    final d = DateTime.now().toUtc().difference(s.toUtc());
    final sec = d.inSeconds < 0 ? 0 : d.inSeconds;
    return '${sec ~/ 60}:${(sec % 60).toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 28,
      padding: const EdgeInsets.symmetric(horizontal: 14),
      decoration: const BoxDecoration(
        color: Pt.amberWash,
        border: Border(bottom: BorderSide(color: Pt.amber)),
      ),
      child: Row(
        children: [
          const BarberPole(width: 120, height: 10),
          const SizedBox(width: 10),
          Text('${widget.run.stage ?? 'Running'}...  ', style: ui(size: 11.5)),
          Text(_elapsed, style: mono(size: 11.5)),
        ],
      ),
    );
  }
}

class _HistoryRow extends StatelessWidget {
  final RunSummary run;
  final String when;
  final bool odd;
  final VoidCallback? onTap;

  const _HistoryRow({required this.run, required this.when, required this.odd, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final m = run.metrics;
    final result = run.isNoFit
        ? 'no reliable fit'
        : (m?.rmseM != null ? '${m!.rmseM!.toStringAsFixed(m.rmseM! >= 10 ? 1 : 2)} m' : (run.isRunning ? 'running…' : '—'));
    return PtPressable(
      onPressed: onTap,
      builder: (context, hover, down, focus) => Container(
        height: 24,
        padding: const EdgeInsets.symmetric(horizontal: 8),
        color: hover ? Pt.accentWash : (odd ? Pt.stripe : Pt.paper),
        child: Row(
          children: [
            StatusBadge(status: run.displayStatus, showText: false),
            const SizedBox(width: 8),
            Expanded(child: Text(when, style: mono(size: 11.5))),
            Text(result, style: mono(size: 11.5, color: Pt.ink2)),
          ],
        ),
      ),
    );
  }
}
