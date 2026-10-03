import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../models/benchmark_summary.dart';
import '../services/api_client.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';
import '../widgets/benchmark_chart.dart';
import '../widgets/benchmark_table.dart';

/// Sidebar page: the synthetic ground-truth benchmark (`GET /benchmarks`),
/// one chart + table per swept difficulty, with a legend that doubles as a
/// show/hide toggle for each algorithm variant.
class BenchmarkScreen extends StatefulWidget {
  final ApiClient api;

  const BenchmarkScreen({super.key, required this.api});

  @override
  State<BenchmarkScreen> createState() => _BenchmarkScreenState();
}

class _BenchmarkScreenState extends State<BenchmarkScreen> {
  BenchmarkSummary? _data; // null while loading, or when the server has no benchmark yet
  Map<String, VariantStyle> _styles = const {};
  bool _loading = true;
  String? _error;
  final Set<String> _hidden = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await widget.api.getBenchmarks();
      if (!mounted) return;
      setState(() {
        _data = data;
        _styles = data == null ? const {} : variantStylesFor(data.variants);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _toggle(String variant) {
    setState(() {
      if (!_hidden.remove(variant)) _hidden.add(variant);
    });
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;
    final subtitle = data == null
        ? 'Synthetic scenes with a known ground truth'
        : 'Generated ${_generated(data.generated)} · ${data.panels.length} ${data.panels.length == 1 ? 'chart' : 'charts'}';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          title: 'Benchmark',
          subtitle: subtitle,
          actions: [
            ToolButton(
              icon: Icons.refresh,
              label: 'Refresh',
              tooltip: 'Reload the benchmark results',
              onPressed: _loading ? null : _load,
            ),
          ],
        ),
        Expanded(child: _content()),
      ],
    );
  }

  Widget _content() {
    final data = _data;
    if (data != null) return _results(data);
    if (_loading) return const Center(child: Spinner(size: 22));
    if (_error != null) {
      return _stateBox(
        Callout(
          kind: CalloutKind.error,
          title: 'Could not load the benchmark',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              SelectableText(_error!, style: mono(size: 11.5, color: Pt.red)),
              const SizedBox(height: 12),
              PushButton(label: 'Retry', onPressed: _load),
            ],
          ),
        ),
      );
    }
    return _emptyState();
  }

  /// Top-left, width-capped box for the error and empty states.
  Widget _stateBox(Widget callout) {
    return ScreenBody(
      child: Align(
        alignment: Alignment.topLeft,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: Entrance(child: callout),
        ),
      ),
    );
  }

  Widget _emptyState() {
    return _stateBox(
      Callout(
        kind: CalloutKind.info,
        title: 'No benchmark yet',
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'The benchmark scores each registration variant on synthetic scenes with a known '
              'ground truth. It is generated offline and the server has no results for it yet, so '
              'there is nothing to chart.',
              style: ui(height: 1.4),
            ),
            const SizedBox(height: 10),
            Text('To produce it, run these inside the algo environment, then check again:', style: ui(height: 1.4)),
            const SizedBox(height: 8),
            Well(
              padding: const EdgeInsets.all(8),
              child: SelectableText(
                'python -m algo.benchmark.suites <suite>\npython -m algo.benchmark.report',
                style: mono(size: 11.5),
              ),
            ),
            const SizedBox(height: 12),
            PushButton(label: 'Check again', isDefault: true, onPressed: _load),
          ],
        ),
      ),
    );
  }

  // ---- results ---------------------------------------------------------------

  Widget _results(BenchmarkSummary data) {
    // Panels grouped by suite, in order of first appearance.
    final suiteOrder = <String>[];
    for (final p in data.panels) {
      if (!suiteOrder.contains(p.suite)) suiteOrder.add(p.suite);
    }

    return ScreenBody(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth;
          final wide = width >= 900;
          final twoColumns = width >= 1000;

          final sections = <Widget>[
            if (_error != null)
              Callout(
                kind: CalloutKind.error,
                title: 'Could not refresh the benchmark',
                child: SelectableText(_error!, style: mono(size: 11.5, color: Pt.red)),
              ),
            _introPanel(data, wide),
            _legendPanel(data, wide),
            if (data.panels.isEmpty)
              Panel(title: 'No charts', child: Text('The benchmark file contains no panels to chart.', style: ui())),
            for (final suite in suiteOrder) _suiteGroup(data, suite, twoColumns),
          ];

          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < sections.length; i++) ...[
                if (i > 0) const SizedBox(height: 14),
                Entrance(delay: Duration(milliseconds: 40 * i.clamp(0, 6)), child: sections[i]),
              ],
            ],
          );
        },
      ),
    );
  }

  Widget _suiteGroup(BenchmarkSummary data, String suite, bool twoColumns) {
    final panels = data.panels.where((q) => q.suite == suite).toList();
    final charts = [for (final p in panels) _chartPanel(data, p)];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text(data.suiteTitle(suite), style: titleStyle(size: 13)),
            const SizedBox(width: 10),
            const Expanded(child: Hairline()),
          ],
        ),
        const SizedBox(height: 10),
        Masonry(
          columns: twoColumns ? 2 : 1,
          gap: 14,
          weights: List<double>.filled(charts.length, 1),
          children: charts,
        ),
      ],
    );
  }

  String _generated(String? iso) {
    if (iso == null) return '—';
    try {
      return DateFormat('yyyy-MM-dd HH:mm').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }

  String _px(double v) => double.parse(v.toStringAsFixed(2)).toString();

  Widget _introPanel(BenchmarkSummary data, bool wide) {
    final text = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Every scene here has a known ground truth: synthetic imagery built from real lunar terrain, '
          'warped by a transform the benchmark chose, then degraded along one axis at a time (a different '
          'Sun angle, a worse starting guess, a different scale, non-rigid distortion, terrain parallax). '
          'The pipeline never sees the truth, so the error it reports is the real one.',
          style: ui(height: 1.4),
        ),
        const SizedBox(height: 8),
        Text(
          'Each chart plots the median RMS error against the known truth, in reference pixels on a log scale '
          '(lower is better). A case counts as a success when its error is under ${_px(data.successPx)} px, '
          'the dotted red line. Where a variant succeeded on fewer than all cases its success rate is printed '
          'at the point.',
          style: ui(height: 1.4),
        ),
      ],
    );
    final facts = PropertyTable(
      labelWidth: 124,
      rows: [
        Prop('Generated', _generated(data.generated)),
        Prop('Success threshold', '${_px(data.successPx)} px'),
        Prop('Charts', '${data.panels.length}'),
      ],
    );
    return Panel(
      title: 'What this measures',
      child: wide
          ? Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: text),
                const SizedBox(width: 24),
                SizedBox(width: 320, child: facts),
              ],
            )
          : Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [text, const SizedBox(height: 10), const Hairline(), const SizedBox(height: 6), facts],
            ),
    );
  }

  Widget _legendPanel(BenchmarkSummary data, bool wide) {
    final variants = data.variants;
    return Panel(
      title: 'Variants',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Click a variant to show or hide it in every chart and table below.', style: captionStyle()),
          const SizedBox(height: 8),
          LayoutBuilder(
            builder: (context, constraints) {
              const gap = 12.0;
              final cols = wide ? 2 : 1;
              final itemWidth = (constraints.maxWidth - gap * (cols - 1)) / cols;
              return Wrap(
                spacing: gap,
                runSpacing: 2,
                children: [
                  for (final v in variants)
                    SizedBox(
                      width: itemWidth,
                      child: _VariantToggle(
                        name: v,
                        note: data.variantNotes[v] ?? '',
                        style: _styles[v],
                        shown: !_hidden.contains(v),
                        onTap: () => _toggle(v),
                      ),
                    ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _chartPanel(BenchmarkSummary data, BenchmarkPanel p) {
    // Canonical variant order, restricted to what this panel measured and the user hasn't hidden.
    final visible = [
      for (final v in data.variants)
        if (p.variants.contains(v) && !_hidden.contains(v)) v,
    ];
    return Panel(
      title: p.title,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('Median RMS error in reference pixels, log scale · lower is better', style: captionStyle()),
          const SizedBox(height: 8),
          if (visible.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 32),
              child: Text(
                'No variants selected. Turn one on in the Variants panel above to plot it.',
                textAlign: TextAlign.center,
                style: ui(color: Pt.ink2),
              ),
            )
          else ...[
            Wrap(
              spacing: 16,
              runSpacing: 4,
              children: [
                for (final v in visible)
                  if (_styles[v] != null)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        VariantMarker(style: _styles[v]!),
                        const SizedBox(width: 5),
                        Text(v, style: mono(size: 11)),
                      ],
                    ),
              ],
            ),
            const SizedBox(height: 8),
            // Wide enough: chart and table side by side, so the table never
            // stretches across the whole screen; otherwise stacked.
            LayoutBuilder(builder: (context, box) {
              final chart = Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  BenchmarkChart(panel: p, visible: visible, styles: _styles, successPx: data.successPx),
                  if (p.xLabel.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Center(child: Text(p.xLabel, style: captionStyle())),
                  ],
                  if (panelHasFailures(p, visible)) ...[
                    const SizedBox(height: 4),
                    Text(
                      'A cross near the top means every case failed there, so there is no error to plot.',
                      style: captionStyle(),
                    ),
                  ],
                ],
              );
              final table = BenchmarkTable(panel: p, visible: visible, styles: _styles);
              if (box.maxWidth >= 720 && visible.length <= 3) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(flex: 11, child: chart),
                    const SizedBox(width: 14),
                    Expanded(flex: 9, child: table),
                  ],
                );
              }
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [chart, const SizedBox(height: 12), table],
              );
            }),
          ],
        ],
      ),
    );
  }
}

/// One row of the Variants legend: a checkbox, the variant's marker, its name
/// and a one-line note. Clicking anywhere on the row toggles it.
class _VariantToggle extends StatelessWidget {
  final String name;
  final String note;
  final VariantStyle? style;
  final bool shown;
  final VoidCallback onTap;

  const _VariantToggle({required this.name, required this.note, required this.style, required this.shown, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return PtPressable(
      onPressed: onTap,
      builder: (context, hover, down, focus) {
        return FocusRing(
          show: focus,
          child: AnimatedContainer(
            duration: kFast,
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
            decoration: BoxDecoration(
              color: hover ? Pt.accentWash : Colors.transparent,
              borderRadius: BorderRadius.circular(kRadius),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: SizedBox(
                    width: 15,
                    height: 15,
                    child: Stack(
                      children: [
                        Positioned.fill(
                          child: CustomPaint(
                            painter: BevelPainter(
                              style: BevelStyle.sunken,
                              radius: 2,
                              top: down ? Pt.chromeLo : Pt.paper,
                              bottom: down ? Pt.chromeLo : Pt.paper,
                            ),
                          ),
                        ),
                        Center(
                          child: AnimatedScale(
                            duration: kMedium,
                            curve: kSpring,
                            scale: shown ? 1 : 0,
                            child: const Icon(Icons.check, size: 13, color: Pt.accentLo),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                if (style != null) ...[
                  Padding(
                    padding: const EdgeInsets.only(top: 0.5),
                    child: AnimatedOpacity(
                      duration: kFast,
                      opacity: shown ? 1 : 0.4,
                      child: VariantMarker(style: style!),
                    ),
                  ),
                  const SizedBox(width: 6),
                ],
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(name, style: mono(size: 12, weight: FontWeight.w700)),
                      if (note.isNotEmpty) Text(note, style: captionStyle()),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
