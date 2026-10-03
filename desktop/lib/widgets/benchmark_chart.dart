import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../models/benchmark_summary.dart';
import '../theme/platinum.dart';
import '../ui/panels.dart';

enum MarkerShape { square, circle, diamond, triangle, cross }

/// How one algorithm variant is drawn: a colour plus a marker shape, so lines
/// stay distinguishable without relying on colour alone.
class VariantStyle {
  final Color color;
  final MarkerShape shape;

  const VariantStyle(this.color, this.shape);
}

// Baseline is plain ink; the auto family is blue and the re-lit family green,
// each getting darker as options are added (+nr, +dem). Red stays reserved for
// the success threshold.
const Map<String, Color> _knownColors = {
  'baseline': Pt.ink,
  'auto': Color(0xFF6FA8EE),
  'auto+nr': Color(0xFF2B6CD4),
  'auto+nr+dem': Color(0xFF12337A),
  'relit': Color(0xFF63C27A),
  'relit+nr': Color(0xFF2B8A3A),
  'relit+nr+dem': Color(0xFF0E4A1E),
};
const List<Color> _fallbackColors = [Color(0xFF8A5A9E), Color(0xFFA0702A), Color(0xFF2A8C8F)];

/// Stable style per variant for a given (canonically ordered) variant list, so
/// a variant looks the same in every chart, table and legend.
Map<String, VariantStyle> variantStylesFor(List<String> variants) {
  final out = <String, VariantStyle>{};
  var fallback = 0;
  for (var i = 0; i < variants.length; i++) {
    final v = variants[i];
    final color = _knownColors[v] ?? _fallbackColors[fallback++ % _fallbackColors.length];
    out[v] = VariantStyle(color, MarkerShape.values[i % MarkerShape.values.length]);
  }
  return out;
}

/// Draws one marker centred on `c`; shared by the chart and the legend swatches.
void paintMarker(Canvas canvas, Offset c, VariantStyle style, {double r = 5}) {
  final fill = Paint()
    ..color = style.color
    ..style = PaintingStyle.fill;
  final halo = Paint()
    ..color = Pt.paper
    ..style = PaintingStyle.stroke
    ..strokeWidth = 1.5;
  switch (style.shape) {
    case MarkerShape.square:
      {
        final rect = Rect.fromCenter(center: c, width: r * 1.8, height: r * 1.8);
        canvas.drawRect(rect, fill);
        canvas.drawRect(rect, halo);
      }
    case MarkerShape.circle:
      {
        canvas.drawCircle(c, r, fill);
        canvas.drawCircle(c, r, halo);
      }
    case MarkerShape.diamond:
      {
        final d = r * 1.3;
        final path = Path()
          ..moveTo(c.dx, c.dy - d)
          ..lineTo(c.dx + d, c.dy)
          ..lineTo(c.dx, c.dy + d)
          ..lineTo(c.dx - d, c.dy)
          ..close();
        canvas.drawPath(path, fill);
        canvas.drawPath(path, halo);
      }
    case MarkerShape.triangle:
      {
        final path = Path()
          ..moveTo(c.dx, c.dy - r * 1.25)
          ..lineTo(c.dx + r * 1.2, c.dy + r * 0.9)
          ..lineTo(c.dx - r * 1.2, c.dy + r * 0.9)
          ..close();
        canvas.drawPath(path, fill);
        canvas.drawPath(path, halo);
      }
    case MarkerShape.cross:
      {
        final stroke = Paint()
          ..color = style.color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5;
        final d = r * 0.95;
        canvas.drawLine(c + Offset(-d, -d), c + Offset(d, d), stroke);
        canvas.drawLine(c + Offset(-d, d), c + Offset(d, -d), stroke);
      }
  }
}

/// A variant's marker as a small inline widget, for legends and table headers.
class VariantMarker extends StatelessWidget {
  final VariantStyle style;

  const VariantMarker({super.key, required this.style});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(size: const Size(14, 14), painter: _MarkerPainter(style));
  }
}

class _MarkerPainter extends CustomPainter {
  final VariantStyle style;

  _MarkerPainter(this.style);

  @override
  void paint(Canvas canvas, Size size) => paintMarker(canvas, size.center(Offset.zero), style, r: 4.5);

  @override
  bool shouldRepaint(_MarkerPainter old) => old.style.color != style.color || old.style.shape != style.shape;
}

/// Whether any plotted variant has a point where every case failed (no median
/// error to draw), so the screen can explain the "x" markers at the top.
bool panelHasFailures(BenchmarkPanel panel, List<String> visible) {
  for (final pt in panel.points) {
    for (final v in visible) {
      final s = pt.variants[v];
      if (s != null && s.medianRmsePx == null) return true;
    }
  }
  return false;
}

/// Line chart of one benchmark panel: x = the swept difficulty, y = median RMS
/// error in reference pixels on a log scale, one line per visible variant, the
/// success rate printed at any point under 100%, and a dotted line at the
/// success threshold.
class BenchmarkChart extends StatelessWidget {
  final BenchmarkPanel panel;
  final List<String> visible;
  final Map<String, VariantStyle> styles;
  final double successPx;
  final double height;

  const BenchmarkChart({
    super.key,
    required this.panel,
    required this.visible,
    required this.styles,
    required this.successPx,
    this.height = 300,
  });

  @override
  Widget build(BuildContext context) {
    return Well(
      child: SizedBox(
        height: height,
        // Lines and markers sweep in left to right once, like the page sections fade in.
        child: TweenAnimationBuilder<double>(
          tween: Tween(begin: 0, end: 1),
          duration: const Duration(milliseconds: 800),
          curve: Curves.easeOutCubic,
          builder: (context, t, _) => CustomPaint(
            size: Size.infinite,
            painter: _ChartPainter(
              panel: panel,
              visible: visible,
              styles: styles,
              successPx: successPx,
              progress: t,
            ),
          ),
        ),
      ),
    );
  }
}

class _ChartPainter extends CustomPainter {
  final BenchmarkPanel panel;
  final List<String> visible;
  final Map<String, VariantStyle> styles;
  final double successPx;
  final double progress;

  _ChartPainter({
    required this.panel,
    required this.visible,
    required this.styles,
    required this.successPx,
    required this.progress,
  });

  static const double _left = 54;
  static const double _right = 24;
  static const double _top = 14;
  static const double _bottom = 30;
  static const double _xInset = 16;

  static const Color _failedBackdrop = Color.fromRGBO(255, 255, 255, 0.88);

  String _fmtX(double x) =>
      x == x.roundToDouble() ? x.toStringAsFixed(0) : double.parse(x.toStringAsFixed(2)).toString();

  String _fmtTick(int exp) =>
      exp >= 0 ? math.pow(10, exp).toStringAsFixed(0) : (1 / math.pow(10, -exp)).toStringAsFixed(-exp);

  TextPainter _text(String s, TextStyle style) =>
      TextPainter(text: TextSpan(text: s, style: style), textDirection: TextDirection.ltr)..layout();

  @override
  void paint(Canvas canvas, Size size) {
    final plot = Rect.fromLTRB(_left, _top, size.width - _right, size.height - _bottom);
    if (plot.width < 80 || plot.height < 60 || panel.points.isEmpty) return;

    // ---- y axis: log scale spanning every variant in the panel, so toggling
    // variants never rescales the chart ----
    final values = <double>[if (successPx > 0) successPx];
    for (final pt in panel.points) {
      for (final s in pt.variants.values) {
        final v = s.medianRmsePx;
        if (v != null && v > 0) values.add(v);
      }
    }
    if (values.isEmpty) values.add(1);
    final lo = values.reduce(math.min);
    final hi = values.reduce(math.max);
    final minExp = (math.log(lo / 1.2) / math.ln10).floor();
    var maxExp = (math.log(hi * 1.2) / math.ln10).ceil();
    if (maxExp <= minExp) maxExp = minExp + 1;
    final lowValue = math.pow(10, minExp).toDouble();

    double yOf(double v) {
      final t = (math.log(math.max(v, lowValue)) / math.ln10 - minExp) / (maxExp - minExp);
      return plot.bottom - t.clamp(0.0, 1.0) * plot.height;
    }

    final tickStyle = mono(size: 10.5, color: Pt.ink2);
    final minorPaint = Paint()
      ..color = Pt.rule.withValues(alpha: 0.35)
      ..strokeWidth = 1;
    final majorPaint = Paint()
      ..color = Pt.rule
      ..strokeWidth = 1;
    for (var e = minExp; e <= maxExp; e++) {
      final base = math.pow(10, e).toDouble();
      final y = yOf(base);
      canvas.drawLine(Offset(plot.left, y), Offset(plot.right, y), majorPaint);
      final label = _text(_fmtTick(e), tickStyle);
      label.paint(canvas, Offset(plot.left - 8 - label.width, y - label.height / 2));
      if (e < maxExp) {
        for (var m = 2; m <= 9; m++) {
          final ym = yOf(base * m);
          canvas.drawLine(Offset(plot.left, ym), Offset(plot.right, ym), minorPaint);
        }
      }
    }

    // ---- x axis: true numeric positions when the sweep is evenly spaced,
    // otherwise equal spacing (geometric sweeps would pile up at one end) ----
    final n = panel.points.length;
    final xMin = panel.points.first.x;
    final xMax = panel.points.last.x;
    var uniform = false;
    if (n > 2 && xMax > xMin) {
      final gaps = [for (var i = 1; i < n; i++) panel.points[i].x - panel.points[i - 1].x];
      final minGap = gaps.reduce(math.min);
      uniform = minGap > 0 && gaps.reduce(math.max) / minGap <= 4;
    }
    final xLeft = plot.left + _xInset;
    final xRight = plot.right - _xInset;
    double xOf(int i) {
      if (n == 1) return (xLeft + xRight) / 2;
      final t = uniform ? (panel.points[i].x - xMin) / (xMax - xMin) : i / (n - 1);
      return xLeft + t * (xRight - xLeft);
    }

    final axis = Paint()
      ..color = Pt.edge
      ..strokeWidth = 1;
    canvas.drawLine(plot.bottomLeft, plot.bottomRight, axis);
    canvas.drawLine(plot.topLeft, plot.bottomLeft, axis);

    final xTickStyle = mono(size: 10.5, color: Pt.ink2);
    var lastRight = double.negativeInfinity;
    for (var i = 0; i < n; i++) {
      final x = xOf(i);
      canvas.drawLine(Offset(x, plot.bottom), Offset(x, plot.bottom + 4), axis);
      final label = _text(_fmtX(panel.points[i].x), xTickStyle);
      final left = x - label.width / 2;
      if (left < lastRight + 8) continue; // would overlap the previous label
      label.paint(canvas, Offset(left, plot.bottom + 8));
      lastRight = left + label.width;
    }

    // ---- success threshold: dotted red line ----
    if (successPx > 0) {
      final y = yOf(successPx);
      final dot = Paint()
        ..color = Pt.red
        ..strokeWidth = 1.5;
      for (var x = plot.left; x < plot.right; x += 8) {
        canvas.drawLine(Offset(x, y), Offset(math.min(x + 4, plot.right), y), dot);
      }
      final label = _text('Success below ${_fmtX(successPx)} px', mono(size: 10.5, weight: FontWeight.w700, color: Pt.red));
      label.paint(canvas, Offset(plot.right - 6 - label.width, y - label.height - 3));
    }

    // ---- data: lines, then markers, then success-rate annotations. Revealed
    // left to right by `progress`. ----
    canvas.save();
    canvas.clipRect(Rect.fromLTRB(0, 0, plot.left + (size.width - plot.left) * progress, size.height));

    for (final v in visible) {
      final st = styles[v];
      if (st == null) continue;
      final path = Path();
      var penDown = false;
      for (var i = 0; i < n; i++) {
        final median = panel.points[i].variants[v]?.medianRmsePx;
        if (median == null) {
          penDown = false; // gap: nothing to plot where every case failed
          continue;
        }
        final o = Offset(xOf(i), yOf(median));
        if (penDown) {
          path.lineTo(o.dx, o.dy);
        } else {
          path.moveTo(o.dx, o.dy);
          penDown = true;
        }
      }
      canvas.drawPath(
        path,
        Paint()
          ..color = st.color
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5
          ..strokeJoin = StrokeJoin.round,
      );
    }

    final annotations = <_Annotation>[];
    for (var vi = 0; vi < visible.length; vi++) {
      final v = visible[vi];
      final st = styles[v];
      if (st == null) continue;
      for (var i = 0; i < n; i++) {
        final s = panel.points[i].variants[v];
        if (s == null) continue;
        final x = xOf(i);
        final pct = '${(s.success * 100).round()}%';
        if (s.medianRmsePx == null) {
          // Every case failed: a cross stacked near the top, one row per variant.
          final c = Offset(x, plot.top + 9 + 11.0 * vi);
          paintMarker(canvas, c, VariantStyle(st.color, MarkerShape.cross), r: 4);
          annotations.add(_Annotation(pct, Offset(x + 9, c.dy), st.color, centered: false));
          continue;
        }
        final c = Offset(x, yOf(s.medianRmsePx!));
        paintMarker(canvas, c, st);
        if (s.success < 1.0) {
          final above = c.dy - 16 >= plot.top;
          annotations.add(_Annotation(pct, Offset(x, above ? c.dy - 14 : c.dy + 14), st.color));
        }
      }
    }
    for (final a in annotations) {
      final tp = _text(a.text, mono(size: 10.5, weight: FontWeight.w700, color: a.color));
      final origin = a.centered ? Offset(a.at.dx - tp.width / 2, a.at.dy - tp.height / 2) : Offset(a.at.dx, a.at.dy - tp.height / 2);
      canvas.drawRect(origin & tp.size, Paint()..color = _failedBackdrop);
      tp.paint(canvas, origin);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_ChartPainter old) =>
      old.panel != panel ||
      old.progress != progress ||
      old.successPx != successPx ||
      !mapEquals(old.styles, styles) ||
      !listEquals(old.visible, visible);
}

class _Annotation {
  final String text;
  final Offset at;
  final Color color;
  final bool centered;

  _Annotation(this.text, this.at, this.color, {this.centered = true});
}
