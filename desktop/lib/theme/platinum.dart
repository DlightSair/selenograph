// Design system "Platinum": classic Mac OS 8/9 chrome (bevels, pinstripes,
// etched boxes, a beige-grey face colour) and the plain, information-dense
// layout of professional desktop software -- with the motion and polish of
// modern macOS on top (springy transitions, blue focus rings, a menu bar,
// a sliding sidebar selection).
//
// Rules the whole UI follows, so it stays readable:
//   * one corner radius (kRadius) for every box, button and field;
//   * one text size for body (12), one for secondary text (11), one for titles;
//   * labels in sentence case, never letter-spaced capitals;
//   * data lives on white "paper" surfaces; chrome is grey;
//   * system fonts only (Tahoma / Lucida Grande for text, Lucida Console / Monaco
//     for numbers), so nothing has to be downloaded or bundled.
import 'dart:math' as math;

import 'package:flutter/material.dart';

class Pt {
  Pt._();

  // Chrome (window faces, toolbars, buttons).
  static const desk = Color(0xFFBDBBB4);
  static const chrome = Color(0xFFDCDAD4);
  static const chromeHi = Color(0xFFEDEBE6);
  static const chromeLo = Color(0xFFC8C6BF);
  static const sidebar = Color(0xFFE5E4DF);

  // Data surfaces.
  static const paper = Color(0xFFFFFFFF);
  static const stripe = Color(0xFFF2F4F9);

  // Bevel + outline colours.
  static const hi = Color(0xFFFFFFFF);
  static const shade = Color(0xFF9A978F);
  static const edge = Color(0xFF4E4C47);
  static const rule = Color(0xFFB9B6AE); // hairlines between rows

  // Text.
  static const ink = Color(0xFF17161A);
  static const ink2 = Color(0xFF4F4D48); // secondary, still >5:1 on chrome
  static const ink3 = Color(0xFF8A8780); // disabled only

  // Selection / default action (Aqua-ish blue).
  static const accent = Color(0xFF2B6CD4);
  static const accentHi = Color(0xFF86B3F2);
  static const accentLo = Color(0xFF1D4FA6);
  static const accentWash = Color(0xFFDCE8FA);

  // Status.
  static const red = Color(0xFFBF2F26);
  static const redWash = Color(0xFFF8E1DE);
  static const green = Color(0xFF2B7A33);
  static const greenWash = Color(0xFFDDF0DF);
  static const amber = Color(0xFFA86A06);
  static const amberWash = Color(0xFFFBEFD3);

  // LCD readout (headline numbers).
  static const lcdBg = Color(0xFFCBD3B8);
  static const lcdInk = Color(0xFF1B2616);
  static const lcdDim = Color(0xFF55624A);

  static const tipBg = Color(0xFFFFFBD6);
}

/// The one corner radius.
const double kRadius = 4;

// ---- typography -------------------------------------------------------------

const String _uiFamily = 'Tahoma';
const List<String> _uiFallback = [
  'Lucida Grande',
  'Geneva',
  'Verdana',
  'Segoe UI',
  'DejaVu Sans',
  'Helvetica Neue',
  'Arial',
];
const String _monoFamily = 'Monaco';
const List<String> _monoFallback = [
  'Lucida Console',
  'Consolas',
  'Menlo',
  'DejaVu Sans Mono',
  'Courier New',
  'monospace',
];

/// Interface text. 12 px is the body size; 11 px for secondary lines.
TextStyle ui({
  double size = 12,
  FontWeight weight = FontWeight.w400,
  Color color = Pt.ink,
  double? height,
  FontStyle? style,
  double? letterSpacing,
}) =>
    TextStyle(
      fontFamily: _uiFamily,
      fontFamilyFallback: _uiFallback,
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height ?? 1.3,
      fontStyle: style,
      letterSpacing: letterSpacing,
    );

/// Numbers, coordinates, paths, matrices, run ids.
TextStyle mono({
  double size = 12,
  FontWeight weight = FontWeight.w400,
  Color color = Pt.ink,
  double? height,
}) =>
    TextStyle(
      fontFamily: _monoFamily,
      fontFamilyFallback: _monoFallback,
      fontSize: size,
      fontWeight: weight,
      color: color,
      height: height ?? 1.3,
    );

/// Screen / window titles.
TextStyle titleStyle({double size = 15, Color color = Pt.ink}) =>
    ui(size: size, weight: FontWeight.w700, color: color, height: 1.2);

/// Small secondary text under titles, captions, hints.
TextStyle captionStyle({Color color = Pt.ink2, double size = 11}) => ui(size: size, color: color, height: 1.35);

// ---- bevelled surfaces ------------------------------------------------------

enum BevelStyle { raised, sunken, flat }

/// Paints a classic bevelled box: a 1 px outline, an inner highlight on the lit
/// edges and an inner shade on the others, over a soft vertical gradient.
class BevelPainter extends CustomPainter {
  final BevelStyle style;
  final Color? top;
  final Color? bottom;
  final Color outline;
  final double radius;
  final bool bevel;

  const BevelPainter({
    this.style = BevelStyle.raised,
    this.top,
    this.bottom,
    this.outline = Pt.edge,
    this.radius = kRadius,
    this.bevel = true,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final outer = RRect.fromRectAndRadius(rect.deflate(0.5), Radius.circular(radius));
    final t = top ??
        (style == BevelStyle.sunken ? Pt.paper : Pt.chromeHi);
    final b = bottom ??
        (style == BevelStyle.sunken ? Pt.paper : Pt.chromeLo);
    canvas.drawRRect(
      outer,
      Paint()
        ..shader = LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [t, b])
            .createShader(rect),
    );
    if (bevel && style != BevelStyle.flat) {
      final light = Paint()
        ..color = Pt.hi.withValues(alpha: style == BevelStyle.raised ? 0.95 : 0.9)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1;
      final dark = Paint()
        ..color = Pt.shade.withValues(alpha: style == BevelStyle.raised ? 0.55 : 0.75)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1;
      final l = 1.5, tp = 1.5, r = size.width - 1.5, bt = size.height - 1.5;
      final k = math.max(radius - 1, 1.0);
      final tl = Path()
        ..moveTo(l, bt - k)
        ..lineTo(l, tp + k)
        ..quadraticBezierTo(l, tp, l + k, tp)
        ..lineTo(r - k, tp);
      final br = Path()
        ..moveTo(r, tp + k)
        ..lineTo(r, bt - k)
        ..quadraticBezierTo(r, bt, r - k, bt)
        ..lineTo(l + k, bt);
      canvas.drawPath(tl, style == BevelStyle.raised ? light : dark);
      canvas.drawPath(br, style == BevelStyle.raised ? dark : light);
    }
    canvas.drawRRect(
      outer,
      Paint()
        ..color = outline
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
  }

  @override
  bool shouldRepaint(BevelPainter old) =>
      old.style != style || old.top != top || old.bottom != bottom || old.outline != outline || old.radius != radius || old.bevel != bevel;
}

/// A child on a bevelled face.
class Bevel extends StatelessWidget {
  final Widget? child;
  final BevelStyle style;
  final Color? top;
  final Color? bottom;
  final Color outline;
  final double radius;
  final EdgeInsetsGeometry padding;
  final bool bevel;

  const Bevel({
    super.key,
    this.child,
    this.style = BevelStyle.raised,
    this.top,
    this.bottom,
    this.outline = Pt.edge,
    this.radius = kRadius,
    this.padding = EdgeInsets.zero,
    this.bevel = true,
  });

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: BevelPainter(style: style, top: top, bottom: bottom, outline: outline, radius: radius, bevel: bevel),
      child: Padding(padding: padding, child: child),
    );
  }
}

/// Horizontal pinstripes, as on a Mac OS 8/9 title bar.
class PinstripePainter extends CustomPainter {
  final Color base;
  final Color line;
  const PinstripePainter({this.base = Pt.chrome, this.line = const Color(0x22000000)});

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = base);
    final p = Paint()
      ..color = line
      ..strokeWidth = 1;
    for (double y = 1; y < size.height; y += 3) {
      canvas.drawLine(Offset(0, y + 0.5), Offset(size.width, y + 0.5), p);
    }
    final w = Paint()
      ..color = Pt.hi.withValues(alpha: 0.7)
      ..strokeWidth = 1;
    for (double y = 2; y < size.height; y += 3) {
      canvas.drawLine(Offset(0, y + 0.5), Offset(size.width, y + 0.5), w);
    }
  }

  @override
  bool shouldRepaint(PinstripePainter old) => old.base != base || old.line != line;
}

// ---- motion -----------------------------------------------------------------

/// A lightly under-damped spring: settles like a macOS window, overshoots ~7%.
class SpringCurve extends Curve {
  const SpringCurve();

  @override
  double transformInternal(double t) => 1 - math.exp(-6.5 * t) * math.cos(7.5 * t);
}

const Curve kSpring = SpringCurve();
const Duration kFast = Duration(milliseconds: 120);
const Duration kMedium = Duration(milliseconds: 220);

/// Screen push/pop: fade plus a small springy zoom, like a window opening.
Route<T> ptRoute<T>(WidgetBuilder builder, {String? label}) {
  return PageRouteBuilder<T>(
    settings: RouteSettings(name: label),
    pageBuilder: (context, _, __) => builder(context),
    transitionDuration: const Duration(milliseconds: 360),
    reverseTransitionDuration: const Duration(milliseconds: 180),
    transitionsBuilder: (context, animation, secondary, child) {
      final fade = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic, reverseCurve: Curves.easeIn);
      final zoom = CurvedAnimation(parent: animation, curve: kSpring, reverseCurve: Curves.easeIn);
      return FadeTransition(
        opacity: fade,
        child: ScaleTransition(scale: Tween<double>(begin: 0.965, end: 1).animate(zoom), child: child),
      );
    },
  );
}

/// Switching between top-level sections: a plain quick cross-fade.
Route<T> fadeRoute<T>(WidgetBuilder builder, {String? label}) {
  return PageRouteBuilder<T>(
    settings: RouteSettings(name: label),
    pageBuilder: (context, _, __) => builder(context),
    transitionDuration: const Duration(milliseconds: 200),
    reverseTransitionDuration: const Duration(milliseconds: 120),
    transitionsBuilder: (context, animation, secondary, child) =>
        FadeTransition(opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut), child: child),
  );
}

// ---- theme ------------------------------------------------------------------

ThemeData buildPlatinumTheme() {
  final base = ThemeData.light(useMaterial3: false);
  return base.copyWith(
    scaffoldBackgroundColor: Pt.chrome,
    canvasColor: Pt.chrome,
    primaryColor: Pt.accent,
    colorScheme: base.colorScheme.copyWith(
      primary: Pt.accent,
      onPrimary: Colors.white,
      surface: Pt.chrome,
      onSurface: Pt.ink,
      error: Pt.red,
    ),
    textTheme: base.textTheme.apply(
      fontFamily: _uiFamily,
      fontFamilyFallback: _uiFallback,
      bodyColor: Pt.ink,
      displayColor: Pt.ink,
    ),
    dividerColor: Pt.rule,
    splashFactory: NoSplash.splashFactory,
    highlightColor: Colors.transparent,
    hoverColor: Colors.transparent,
    visualDensity: VisualDensity.compact,
    textSelectionTheme: const TextSelectionThemeData(
      cursorColor: Pt.ink,
      selectionColor: Color(0x662B6CD4),
    ),
    tooltipTheme: TooltipThemeData(
      waitDuration: const Duration(milliseconds: 450),
      decoration: BoxDecoration(
        color: Pt.tipBg,
        border: Border.all(color: Pt.edge, width: 1),
        boxShadow: const [BoxShadow(color: Color(0x40000000), offset: Offset(2, 2))],
      ),
      textStyle: ui(size: 11),
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
      margin: const EdgeInsets.all(6),
    ),
    scrollbarTheme: ScrollbarThemeData(
      thumbVisibility: const WidgetStatePropertyAll(true),
      trackVisibility: const WidgetStatePropertyAll(true),
      thickness: const WidgetStatePropertyAll(13),
      radius: const Radius.circular(kRadius),
      thumbColor: WidgetStateProperty.resolveWith((s) =>
          s.contains(WidgetState.hovered) || s.contains(WidgetState.dragged) ? const Color(0xFF8F8C84) : const Color(0xFFAAA79F)),
      trackColor: const WidgetStatePropertyAll(Color(0xFFE9E7E2)),
      trackBorderColor: const WidgetStatePropertyAll(Pt.rule),
      crossAxisMargin: 0,
      mainAxisMargin: 0,
    ),
    pageTransitionsTheme: PageTransitionsTheme(
      builders: {
        for (final p in TargetPlatform.values) p: const _PtTransitions(),
      },
    ),
  );
}

class _PtTransitions extends PageTransitionsBuilder {
  const _PtTransitions();

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    final fade = CurvedAnimation(parent: animation, curve: Curves.easeOutCubic);
    return FadeTransition(opacity: fade, child: child);
  }
}
