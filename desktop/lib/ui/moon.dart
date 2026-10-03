// The app's identity mark: the Moon drawn as a 1-bit ordered-dither bitmap,
// like a classic Mac icon. `phase` runs 0 (new) .. 0.5 (full) .. 1 (new).
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/platinum.dart';

class MoonIcon extends StatelessWidget {
  final double size;
  final double phase;
  final Color light;
  final Color dark;

  const MoonIcon({super.key, this.size = 24, this.phase = 0.62, this.light = const Color(0xFFF6F3E6), this.dark = Pt.ink});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(painter: MoonPainter(phase: phase, light: light, dark: dark, cells: size >= 56 ? 48 : (size >= 28 ? 32 : 20))),
    );
  }
}

/// Moon whose phase sweeps from new to a gibbous phase while it loads.
class AnimatedMoon extends StatefulWidget {
  final double size;
  const AnimatedMoon({super.key, this.size = 96});

  @override
  State<AnimatedMoon> createState() => _AnimatedMoonState();
}

class _AnimatedMoonState extends State<AnimatedMoon> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(seconds: 9), value: 0.3)..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _c,
      builder: (context, _) => MoonIcon(size: widget.size, phase: _c.value),
    );
  }
}

class MoonPainter extends CustomPainter {
  final double phase;
  final Color light;
  final Color dark;
  final int cells;

  const MoonPainter({required this.phase, required this.light, required this.dark, this.cells = 32});

  static const _bayer = [
    [0, 8, 2, 10],
    [12, 4, 14, 6],
    [3, 11, 1, 9],
    [15, 7, 13, 5],
  ];

  // A few fixed craters: (x, y, radius) in unit-disc coordinates.
  static const _craters = [
    [-0.35, -0.30, 0.20],
    [0.30, -0.45, 0.14],
    [0.10, 0.20, 0.24],
    [-0.45, 0.35, 0.13],
    [0.52, 0.18, 0.11],
    [-0.05, -0.65, 0.09],
    [0.38, 0.58, 0.10],
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final cell = size.width / cells;
    final a = phase * 2 * math.pi;
    final lx = math.sin(a), lz = -math.cos(a);
    final onPaint = Paint()
      ..color = light
      ..isAntiAlias = false;
    final offPaint = Paint()
      ..color = dark
      ..isAntiAlias = false;
    for (var j = 0; j < cells; j++) {
      for (var i = 0; i < cells; i++) {
        final x = (i + 0.5) / cells * 2 - 1;
        final y = (j + 0.5) / cells * 2 - 1;
        final r2 = x * x + y * y;
        if (r2 > 1) continue;
        final z = math.sqrt(1 - r2);
        var v = math.max(0.0, x * lx + z * lz) * 0.95 + 0.03;
        for (final c in _craters) {
          final dx = x - c[0], dy = y - c[1];
          final d = math.sqrt(dx * dx + dy * dy) / c[2];
          if (d < 1) {
            v *= 0.55 + 0.35 * d * d; // dark floor
          } else if (d < 1.25) {
            v *= 1.12; // brighter rim
          }
        }
        final threshold = (_bayer[j % 4][i % 4] + 0.5) / 16;
        final rect = Rect.fromLTWH(i * cell, j * cell, cell + 0.4, cell + 0.4);
        canvas.drawRect(rect, v > threshold ? onPaint : offPaint);
      }
    }
  }

  @override
  bool shouldRepaint(MoonPainter old) => old.phase != phase || old.light != light || old.dark != dark || old.cells != cells;
}
