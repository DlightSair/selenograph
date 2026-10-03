import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models/benchmark_summary.dart';
import '../theme/platinum.dart';
import '../ui/panels.dart';
import 'benchmark_chart.dart';

/// Compact list-view table under a benchmark chart: one row per swept value,
/// one column per visible variant, each cell "success rate · median error"
/// (e.g. "100% · 0.12 px"). Scrolls sideways instead of squeezing when narrow.
class BenchmarkTable extends StatelessWidget {
  final BenchmarkPanel panel;
  final List<String> visible;
  final Map<String, VariantStyle> styles;

  const BenchmarkTable({super.key, required this.panel, required this.visible, required this.styles});

  static const double _firstWidth = 120;
  static const double _columnWidth = 124;
  static const Color _rowDivider = Color(0xFFE3E1DB);

  String _fmtX(double x) =>
      x == x.roundToDouble() ? x.toStringAsFixed(0) : double.parse(x.toStringAsFixed(2)).toString();

  String _fmtPx(double v) => v.toStringAsFixed(v < 10 ? 2 : (v < 100 ? 1 : 0));

  String _cell(VariantStats? s) {
    if (s == null) return '—';
    final pct = '${(s.success * 100).round()}%';
    final err = s.medianRmsePx == null ? '—' : '${_fmtPx(s.medianRmsePx!)} px';
    return '$pct · $err';
  }

  Color _cellColor(VariantStats? s) {
    if (s == null) return Pt.ink2;
    if (s.success >= 1.0) return Pt.ink;
    return s.success <= 0 ? Pt.red : Pt.amber;
  }

  String _tooltip(BenchmarkPoint pt, String variant, VariantStats s) {
    final parts = <String>[
      '$variant at ${_fmtX(pt.x)}',
      if (s.n != null) '${s.n} cases',
      if (s.medianRmseM != null) 'median ${s.medianRmseM!.toStringAsFixed(1)} m',
      if (s.p90RmsePx != null) '90th percentile ${_fmtPx(s.p90RmsePx!)} px',
      if (s.medianPriorRmsePx != null) 'starting guess off by ${_fmtPx(s.medianPriorRmsePx!)} px',
    ];
    return parts.join('\n');
  }

  @override
  Widget build(BuildContext context) {
    Widget cell(Widget child, double? width) {
      final padded = Padding(padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 7), child: child);
      return width == null ? Expanded(child: padded) : SizedBox(width: width, child: padded);
    }

    final head = Container(
      constraints: const BoxConstraints(minHeight: 24),
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.chromeHi, Pt.chromeLo]),
        border: Border(bottom: BorderSide(color: Pt.shade)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          cell(
            Text(
              panel.xLabel,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: ui(size: 11.5, weight: FontWeight.w700),
            ),
            _firstWidth,
          ),
          for (final v in visible)
            cell(
              Row(
                children: [
                  if (styles[v] != null) ...[VariantMarker(style: styles[v]!), const SizedBox(width: 5)],
                  Flexible(
                    child: Text(
                      v,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: ui(size: 11.5, weight: FontWeight.w700),
                    ),
                  ),
                ],
              ),
              null,
            ),
        ],
      ),
    );

    final rows = [
      for (var r = 0; r < panel.points.length; r++)
        _HoverRow(
          zebra: r.isOdd,
          last: r == panel.points.length - 1,
          divider: _rowDivider,
          child: Row(
            children: [
              cell(
                Text(_fmtX(panel.points[r].x), style: mono(size: 11.5, weight: FontWeight.w700)),
                _firstWidth,
              ),
              for (final v in visible) cell(_cellWidget(panel.points[r], v), null),
            ],
          ),
        ),
    ];

    return Well(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final natural = _firstWidth + _columnWidth * visible.length;
          final width = math.max(natural, constraints.maxWidth);
          return SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: SizedBox(
              width: width,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [head, ...rows]),
            ),
          );
        },
      ),
    );
  }

  Widget _cellWidget(BenchmarkPoint pt, String v) {
    final s = pt.variants[v];
    final text = Text(_cell(s), style: mono(size: 11.5, color: _cellColor(s)));
    return s == null
        ? text
        : Tooltip(message: _tooltip(pt, v, s), waitDuration: const Duration(milliseconds: 400), child: text);
  }
}

/// One table row: zebra background, hairline divider, accent wash on hover.
class _HoverRow extends StatefulWidget {
  final Widget child;
  final bool zebra;
  final bool last;
  final Color divider;

  const _HoverRow({required this.child, required this.zebra, required this.last, required this.divider});

  @override
  State<_HoverRow> createState() => _HoverRowState();
}

class _HoverRowState extends State<_HoverRow> {
  bool _hover = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: AnimatedContainer(
        duration: kFast,
        decoration: BoxDecoration(
          color: _hover ? Pt.accentWash : (widget.zebra ? Pt.stripe : Pt.paper),
          border: widget.last ? null : Border(bottom: BorderSide(color: widget.divider)),
        ),
        child: widget.child,
      ),
    );
  }
}
