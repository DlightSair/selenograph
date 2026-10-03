import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/run_summary.dart';
import '../models/viz_manifest.dart';
import '../services/api_client.dart';
import '../shell/app_controller.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';
import '../widgets/how_matched_panel.dart';
import '../widgets/no_fit_panel.dart';
import '../widgets/zoomable_image.dart';

/// Results of one run, laid out like a document window with an inspector: the
/// rendered images in the main area (two side by side), and every number,
/// check and explanation in a fixed-width inspector on the right that scrolls
/// on its own — so the figures never stretch across the screen and stay
/// visible while you look through the images.
class ResultsScreen extends StatefulWidget {
  final String runId;
  final ApiClient api;

  const ResultsScreen({super.key, required this.runId, required this.api});

  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  RunSummary? _run;
  String? _loadError;
  VizManifest? _viz;
  String? _vizError;
  bool _vizLoading = false;
  int _imageRetryToken = 0;
  bool _showInspector = true;
  final ScrollController _inspectorScroll = ScrollController();
  AppController? _app;

  static const double _inspectorWidth = 380;

  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _load();
    // A run opened right after starting is still "running": keep checking until it finishes.
    _poll = Timer.periodic(const Duration(seconds: 2), (_) {
      if (_run == null || _run!.isRunning) _load();
      if (mounted && _run?.isRunning == true) setState(() {}); // elapsed time
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _app ??= AppScope.maybeRead(context);
    _app?.registerRefresh(_load);
  }

  @override
  void dispose() {
    _poll?.cancel();
    _app?.registerRefresh(null);
    _inspectorScroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final run = await widget.api.getRun(widget.runId);
      if (!mounted) return;
      setState(() {
        _run = run;
        _loadError = null;
      });
      if (_hasFit(run)) _loadViz();
    } catch (e) {
      if (!mounted) return;
      setState(() => _loadError = e.toString());
    }
  }

  Future<void> _loadViz() async {
    if (_vizLoading || _viz != null) return;
    setState(() {
      _vizLoading = true;
      _vizError = null;
    });
    try {
      final viz = await widget.api.getVisualizations(widget.runId);
      if (!mounted) return;
      setState(() => _viz = viz);
    } catch (e) {
      if (!mounted) return;
      setState(() => _vizError = e.toString());
    } finally {
      if (mounted) setState(() => _vizLoading = false);
    }
  }

  /// A finished run with a transform and no failure note. Runs without a fit
  /// have nothing for the visualizations to draw (`/runs/{id}/viz` fails).
  bool _hasFit(RunSummary run) => run.isDone && run.transform != null && !run.isNoFit;

  String _fmt(double? v, {int decimals = 2}) => v == null ? '—' : v.toStringAsFixed(decimals);

  /// Metres with more precision when small: 6.4, 0.31.
  String _metres(double v) => v.toStringAsFixed(v >= 10 ? 1 : 2);

  /// 3.86 -> "3.86", 5.0 -> "5.0": two decimals without trailing noise.
  String _gsd(double v) => double.parse(v.toStringAsFixed(2)).toString();

  String _formatTime(String? iso) {
    if (iso == null) return '—';
    try {
      return DateFormat('yyyy-MM-dd HH:mm:ss').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }

  static const _acronyms = {'DEM', 'GSD', 'RMS', 'RMSE', 'NCC', 'CoV'};

  /// The server sends some labels in capitals ("AXIS SCALES"); show them as
  /// ordinary sentences, keeping acronyms.
  String _sentence(String label) {
    if (label != label.toUpperCase()) return label;
    final words = label.toLowerCase().split(' ');
    return [
      for (var i = 0; i < words.length; i++)
        _acronyms.contains(words[i].toUpperCase())
            ? words[i].toUpperCase()
            : (i == 0 && words[i].isNotEmpty ? words[i][0].toUpperCase() + words[i].substring(1) : words[i]),
    ].join(' ');
  }

  String _prettyConfig(String? c) => (c ?? 'Run').replaceAll('.yaml', '').replaceAll('_', ' ').toUpperCase();

  // ---- build -----------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    final run = _run;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          title: 'Results · ${_prettyConfig(run?.config)}',
          subtitle: 'Run ${widget.runId}${run?.finishedAt != null ? ' · finished ${_formatTime(run!.finishedAt)}' : ''}',
          showBack: true,
          actions: [
            if (run != null) StatusBadge(status: run.displayStatus),
            ToolButton(
              icon: CupertinoIcons.sidebar_right,
              label: 'Inspector',
              tooltip: 'Show or hide the numbers and checks',
              active: _showInspector,
              onPressed: () => setState(() => _showInspector = !_showInspector),
            ),
            ToolButton(icon: CupertinoIcons.refresh, label: 'Refresh', onPressed: _load),
          ],
        ),
        Expanded(child: run == null ? _loadingOrError() : _body(run)),
      ],
    );
  }

  Widget _loadingOrError() {
    if (_loadError != null) {
      return Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Callout(kind: CalloutKind.error, title: 'Failed to load the run', child: SelectableText(_loadError!, style: ui(size: 11.5))),
        ),
      );
    }
    return const Center(child: Row(mainAxisSize: MainAxisSize.min, children: [Spinner(), SizedBox(width: 10), Text('Loading run…')]));
  }

  Widget _body(RunSummary run) {
    return LayoutBuilder(builder: (context, box) {
      final wide = box.maxWidth >= 860;
      final panels = _inspectorPanels(run);
      final main = _mainArea(run);
      if (!wide) {
        // Narrow window: the inspector panels become equal columns above the
        // images instead of one stretched stack.
        return ScreenBody(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AnimatedSize(
                duration: const Duration(milliseconds: 260),
                curve: Curves.easeOutCubic,
                alignment: Alignment.topCenter,
                child: _showInspector
                    ? Padding(
                        padding: const EdgeInsets.only(bottom: 14),
                        child: Masonry(
                          columns: box.maxWidth >= 560 ? 2 : 1,
                          weights: [for (final p in panels) p.$2],
                          children: [for (var i = 0; i < panels.length; i++) Entrance(delay: Duration(milliseconds: 40 * i.clamp(0, 8)), child: panels[i].$1)],
                        ),
                      )
                    : const SizedBox(width: double.infinity),
              ),
              main,
            ],
          ),
        );
      }
      return Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(child: ScreenBody(maxWidth: 1100, child: main)),
          AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOutCubic,
            width: _showInspector ? _inspectorWidth : 0,
            child: ClipRect(
              child: OverflowBox(
                alignment: Alignment.centerLeft,
                minWidth: _inspectorWidth,
                maxWidth: _inspectorWidth,
                child: Container(
                  decoration: const BoxDecoration(
                    color: Pt.chrome,
                    border: Border(left: BorderSide(color: Pt.edge)),
                  ),
                  child: Scrollbar(
                    controller: _inspectorScroll,
                    child: SingleChildScrollView(
                      controller: _inspectorScroll,
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          for (var i = 0; i < panels.length; i++) ...[
                            if (i > 0) const SizedBox(height: 10),
                            Entrance(delay: Duration(milliseconds: 40 * i.clamp(0, 8)), child: panels[i].$1),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      );
    });
  }

  // ---- main area: images -------------------------------------------------------

  Widget _mainArea(RunSummary run) {
    if (run.isError) {
      return Panel(
        title: 'Error',
        accent: Pt.red,
        icon: Icons.error,
        child: SelectableText(run.stderrTail ?? 'Run failed with no captured output.', style: mono(size: 11, color: Pt.red)),
      );
    }
    if (run.isRunning) {
      final started = DateTime.tryParse(run.startedAt ?? '');
      final secs = started == null ? 0 : DateTime.now().toUtc().difference(started.toUtc()).inSeconds.clamp(0, 1 << 30);
      final elapsed = '${secs ~/ 60}:${(secs % 60).toString().padLeft(2, '0')}';
      return Panel(
        title: 'Running',
        child: Row(children: [
          const Spinner(),
          const SizedBox(width: 8),
          Text('${run.stage ?? 'Running'}...  '),
          Text(elapsed, style: mono(size: 12)),
        ]),
      );
    }
    final m = run.metrics;
    if (m != null && m.failed) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [Entrance(child: NoFitPanel(failure: m.failure!))],
      );
    }
    if (!_hasFit(run)) {
      return const Callout(kind: CalloutKind.info, title: 'No images for this run', child: Note('The run has no transform to draw.'));
    }
    final viz = _viz;
    if (viz == null) {
      return Panel(
        title: 'Result visualization',
        icon: CupertinoIcons.photo_on_rectangle,
        child: _vizError != null
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Could not render the visualizations.', style: ui(color: Pt.red, weight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  SelectableText(_vizError!, style: ui(size: 11.5, color: Pt.red)),
                  const SizedBox(height: 10),
                  PushButton(label: 'Retry', onPressed: _loadViz, compact: true),
                ],
              )
            : const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [Spinner(), SizedBox(width: 10), Text('Rendering from the full-resolution imagery…')]),
                  SizedBox(height: 8),
                  BarberPole(width: 260),
                  SizedBox(height: 8),
                  Note('The first view of a run takes a few seconds; after that it is cached.'),
                ],
              ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final group in viz.groups) ...[
          _groupHeading(group),
          const SizedBox(height: 8),
          _tileGrid(run, viz.items.where((i) => i.group == group).toList()),
          const SizedBox(height: 16),
        ],
      ],
    );
  }

  Widget _groupHeading(String group) {
    return Row(
      children: [
        Text(group, style: titleStyle(size: 13)),
        const SizedBox(width: 10),
        const Expanded(child: Hairline()),
      ],
    );
  }

  /// One tile per image, each with its own zoom window: two side by side when
  /// there is room, one when narrow.
  Widget _tileGrid(RunSummary run, List<VizItem> items) {
    return LayoutBuilder(builder: (context, constraints) {
      const gap = 12.0;
      final columns = constraints.maxWidth >= 640 ? 2 : 1;
      final width = (constraints.maxWidth - gap * (columns - 1)) / columns;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (var i = 0; i < items.length; i++)
            SizedBox(
              width: width,
              child: Entrance(
                delay: Duration(milliseconds: 50 * i.clamp(0, 6)),
                child: Panel(
                  title: items[i].title,
                  padding: const EdgeInsets.all(8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ZoomableImage(
                        url: '${widget.api.vizImageUrl(run.runId, items[i].name)}?v=$_imageRetryToken',
                        title: '${items[i].title} — run ${run.runId}',
                        height: columns == 2 ? 340 : 420,
                        onRetry: () => setState(() => _imageRetryToken++),
                      ),
                      const SizedBox(height: 8),
                      Text(items[i].caption, style: captionStyle()),
                    ],
                  ),
                ),
              ),
            ),
        ],
      );
    });
  }

  // ---- inspector ----------------------------------------------------------------

  /// The inspector's panels with a rough height weight each, used to balance
  /// the columns in the narrow layout.
  List<(Widget, double)> _inspectorPanels(RunSummary run) {
    final m = run.metrics;
    final out = <(Widget, double)>[];
    if (m != null && !m.failed && !run.isError) {
      out.add((_verdict(), 2.5));
      out.add((_accuracy(m), 8));
      final checks = _checks();
      if (checks != null) out.add((checks, 8));
      out.add((_metricsPanel(m), 10));
    }
    if (m != null) {
      for (final w in HowMatched.panels(m, failed: m.failed)) {
        out.add((w, 6));
      }
    }
    if (_hasFit(run)) {
      final params = _parametersPanel();
      if (params != null) out.add((params, 1));
      out.add((_transformPanel(run), 1));
    }
    out.add((_runPanel(run), 4));
    return out;
  }

  Widget _verdict() {
    final viz = _viz;
    if (viz == null) {
      return Panel(
        title: 'Is this fit reliable?',
        icon: CupertinoIcons.question_circle,
        child: _vizError != null
            ? const Note('Could not be checked: the visualization failed to render.', color: Pt.red)
            : const Row(children: [Spinner(size: 14), SizedBox(width: 8), Expanded(child: Note('Checking against the imagery…'))]),
      );
    }
    final suspect = viz.suspect;
    return Callout(
      kind: suspect ? CalloutKind.error : CalloutKind.ok,
      title: suspect ? 'This fit looks suspect' : 'This fit looks reliable',
      child: Text(viz.summary, style: ui(size: 11.5, color: Pt.ink, height: 1.4)),
    );
  }

  Widget _accuracy(RunMetrics m) {
    final rmse = m.rmseM != null ? _metres(m.rmseM!) : _fmt(m.rmse);
    return Panel(
      title: 'Accuracy',
      icon: CupertinoIcons.scope,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ReadoutBar(items: [
            LcdReadout(label: 'RMSE', value: rmse, unit: m.rmseM != null ? 'm' : 'px'),
            LcdReadout(
              label: 'Held-out',
              value: m.heldoutRmseM != null ? _metres(m.heldoutRmseM!) : '—',
              unit: m.heldoutRmseM != null ? 'm' : null,
            ),
          ]),
          const SizedBox(height: 10),
          ReadoutBar(items: [
            LcdReadout(label: 'Inliers', value: '${m.inlierCount}'),
            LcdReadout(
              label: 'Inlier ratio',
              value: (m.inlierRatio * 100).toStringAsFixed(0),
              unit: '%',
              tone: m.inlierRatio >= 0.5 ? Tone.good : Tone.warn,
            ),
          ]),
          const SizedBox(height: 8),
          const Note(
            'RMSE is the error on the matches the fit kept; held-out is the error on tiles it never saw, so it is the '
            'honest accuracy figure. Lower is better.',
          ),
        ],
      ),
    );
  }

  Widget? _checks() {
    final viz = _viz;
    if (viz == null || viz.checks.isEmpty) return null;
    return Panel(
      title: 'Reliability checks',
      icon: CupertinoIcons.checkmark_shield,
      collapsible: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < viz.checks.length; i++)
            Padding(
              padding: EdgeInsets.only(bottom: i == viz.checks.length - 1 ? 0 : 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    viz.checks[i].ok == null ? Icons.remove_circle_outline : (viz.checks[i].ok! ? Icons.check_circle : Icons.cancel),
                    size: 16,
                    color: viz.checks[i].ok == null ? Pt.ink3 : (viz.checks[i].ok! ? Pt.green : Pt.red),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(viz.checks[i].label, style: ui(weight: FontWeight.w700)),
                        SelectableText(viz.checks[i].detail, style: captionStyle()),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _metricsPanel(RunMetrics m) {
    final rows = <Prop>[
      Prop('RMSE', m.rmseM != null ? '${_fmt(m.rmseM, decimals: 2)} m · ${_fmt(m.rmse)} px' : '${_fmt(m.rmse)} px',
          note: 'Alignment error on the matches the fit kept.'),
      if (m.heldoutRmseM != null)
        Prop('Held-out error', '${_fmt(m.heldoutRmseM, decimals: 2)} m${m.heldoutRmsePx != null ? ' · ${_fmt(m.heldoutRmsePx)} px' : ''}',
            note: 'Accuracy on tiles the fit never saw.'),
      Prop('Matches', '${m.matchCount}', note: 'Candidate correspondences found before outlier rejection.'),
      Prop('Inliers', '${m.inlierCount} (${(m.inlierRatio * 100).toStringAsFixed(0)}%)', note: 'Kept as geometrically consistent.'),
      Prop('Uniformity', _fmt(m.uniformityCov), hint: 'Coefficient of variation', note: 'Spread of matches across the frame; lower is more even.'),
      if (m.structure != null)
        Prop('Matched on', m.structure!, monospace: false, note: _structureHint(m.structure!)),
      if (m.scaleRatio != null) _scaleProp(m),
      if (m.nonrigid != null) _nonRigidProp(m, m.nonrigid!),
    ];
    return Panel(
      title: 'Metrics',
      icon: CupertinoIcons.number,
      collapsible: true,
      child: PropertyTable(labelWidth: 92, rows: rows),
    );
  }

  Prop _nonRigidProp(RunMetrics m, NonRigidInfo nr) {
    final gain = nr.cvGainPct;
    if (!nr.adopted) {
      final note = nr.skipped
          ? 'Not attempted${nr.reason != null ? ' (${nr.reason})' : ''}; the plain homography stands.'
          : 'The extra correction did not predict held-out tiles better${gain != null ? ' (gain ${gain.toStringAsFixed(1)}%)' : ''}, so a plain homography was kept.';
      return Prop('Non-rigid', 'not needed', monospace: false, note: note);
    }
    final refGsd = m.referenceGsdM;
    final rmsM = m.nonrigidFieldRmsM ?? (nr.fieldRmsPx != null && refGsd != null ? nr.fieldRmsPx! * refGsd : null);
    final before = nr.cvRmseHomographyPx;
    final after = nr.cvRmseNonrigidPx;
    final improved = gain != null
        ? ' Held-out error improved ${gain.toStringAsFixed(0)}%${before != null && after != null ? ' (${_fmt(before)} → ${_fmt(after)} px)' : ''}.'
        : '';
    return Prop(
      'Non-rigid',
      rmsM != null ? '${_metres(rmsM)} m RMS' : '${_fmt(nr.fieldRmsPx)} px RMS',
      note: 'Shift beyond a plain homography (platform jitter, terrain parallax).$improved',
    );
  }

  Prop _scaleProp(RunMetrics m) {
    final ratio = m.scaleRatio!;
    final decimation = m.sourceDecimation != null && m.sourceDecimation! > 1.0 ? m.sourceDecimation : null;
    return Prop(
      'Scale',
      '${ratio.toStringAsFixed(2)} ×',
      note: 'Source ${_gsd(m.sourceGsdM!)} m/px against reference ${_gsd(m.referenceGsdM!)} m/px.'
          '${decimation != null ? ' Block-averaged ${_gsd(decimation)}× on read; matching worked at ${_gsd(m.sourceGsdM! * decimation)} m/px.' : ''}',
    );
  }

  String _structureHint(String structure) {
    switch (structure.split('@').first) {
      case 'intensity':
        return 'Plain brightness: the lighting is similar enough that shading still lines up.';
      case 'edges':
      case 'gmag':
        return 'Edge strength: brightness differs between the lightings, but where edges run still lines up.';
      case 'cfog':
      case 'orient':
        return 'Edge directions: shading flips with the Sun angle, but the direction of edges survives.';
      case 'fused':
        return 'A blend of plain brightness and edge directions.';
      default:
        return 'Representation picked for this scene by a self-consistency vote.';
    }
  }

  Widget? _parametersPanel() {
    final viz = _viz;
    if (viz == null || viz.params.isEmpty) return null;
    return Panel(
      title: 'Fit parameters',
      icon: CupertinoIcons.slider_horizontal_3,
      collapsible: true,
      initiallyOpen: false,
      child: PropertyTable(labelWidth: 150, rows: [for (final p in viz.params) Prop(_sentence(p.label), p.value, maxLines: 4)]),
    );
  }

  Widget _transformPanel(RunSummary run) {
    final h = run.transform!.homography;
    final nonRigid = run.metrics?.nonrigid?.adopted ?? false;
    return Panel(
      title: 'Homography',
      icon: CupertinoIcons.square_grid_3x2,
      collapsible: true,
      initiallyOpen: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Well(
            color: Pt.stripe,
            padding: const EdgeInsets.all(8),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SelectableText(
                h.map((row) => row.map((v) => v.toStringAsExponential(3).padLeft(11)).join('  ')).join('\n'),
                style: mono(size: 11),
              ),
            ),
          ),
          if (nonRigid) ...[
            const SizedBox(height: 6),
            const Note('This is the homography part only; the non-rigid correction is applied on top of it.'),
          ],
        ],
      ),
    );
  }

  Widget _runPanel(RunSummary run) {
    return Panel(
      title: 'Run',
      icon: CupertinoIcons.info,
      collapsible: true,
      child: PropertyTable(labelWidth: 70, rows: [
        Prop('Status', run.displayStatus, monospace: false),
        Prop('Project', run.config ?? '—'),
        Prop('Started', _formatTime(run.startedAt)),
        if (run.finishedAt != null) Prop('Finished', _formatTime(run.finishedAt)),
      ]),
    );
  }
}
