// Containers and data displays in the Platinum style: titled panels (optionally
// collapsible), etched group boxes for forms, property tables, grid tables with
// zebra rows, LCD readouts, meters, progress bars, callouts and status badges.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/platinum.dart';

// ---- panels ----------------------------------------------------------------

/// The basic unit of every screen: a titled box with a white body. Every panel
/// has the same header height, radius, outline and padding, so columns of
/// panels always line up. `collapsible` adds a Mac disclosure triangle and an
/// animated windowshade collapse.
class Panel extends StatefulWidget {
  final String title;
  final Widget child;
  final Widget? trailing;
  final bool collapsible;
  final bool initiallyOpen;
  final EdgeInsetsGeometry padding;
  final Color? bodyColor;
  final Color? accent; // tints the header (alerts)
  final IconData? icon;

  const Panel({
    super.key,
    required this.title,
    required this.child,
    this.trailing,
    this.collapsible = false,
    this.initiallyOpen = true,
    this.padding = const EdgeInsets.all(10),
    this.bodyColor,
    this.accent,
    this.icon,
  });

  @override
  State<Panel> createState() => _PanelState();
}

class _PanelState extends State<Panel> {
  late bool _open = widget.initiallyOpen;

  @override
  Widget build(BuildContext context) {
    final accent = widget.accent;
    final headTop = accent == null ? Pt.chromeHi : Color.lerp(Pt.chromeHi, accent, 0.18)!;
    final headBottom = accent == null ? Pt.chromeLo : Color.lerp(Pt.chromeLo, accent, 0.30)!;
    final outline = accent ?? Pt.edge;

    final header = SizedBox(
      height: 24,
      child: Stack(
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [headTop, headBottom]),
                border: Border(bottom: BorderSide(color: accent ?? Pt.shade)),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Row(
              children: [
                if (widget.collapsible)
                  AnimatedRotation(
                    duration: kMedium,
                    curve: kSpring,
                    turns: _open ? 0.25 : 0,
                    child: const Icon(Icons.arrow_right, size: 18, color: Pt.ink),
                  ),
                if (widget.icon != null) ...[
                  Icon(widget.icon, size: 14, color: accent ?? Pt.ink),
                  const SizedBox(width: 5),
                ],
                Expanded(
                  child: Text(
                    widget.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: ui(weight: FontWeight.w700, color: accent ?? Pt.ink),
                  ),
                ),
                if (widget.trailing != null) widget.trailing!,
              ],
            ),
          ),
        ],
      ),
    );

    final body = Container(
      color: widget.bodyColor ?? Pt.paper,
      padding: widget.padding,
      child: widget.child,
    );

    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(kRadius),
        border: Border.all(color: outline),
        boxShadow: const [BoxShadow(color: Color(0x33000000), offset: Offset(1, 1))],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(kRadius - 1),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            widget.collapsible
                ? MouseRegion(
                    cursor: SystemMouseCursors.click,
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => setState(() => _open = !_open),
                      child: header,
                    ),
                  )
                : header,
            AnimatedSize(
              duration: const Duration(milliseconds: 260),
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: _open ? body : const SizedBox(width: double.infinity),
            ),
          ],
        ),
      ),
    );
  }
}

/// Etched group box for forms: a thin engraved outline with the title sitting
/// on the line, as in classic dialogs.
class GroupBox extends StatelessWidget {
  final String title;
  final Widget child;
  final EdgeInsetsGeometry padding;

  const GroupBox({super.key, required this.title, required this.child, this.padding = const EdgeInsets.fromLTRB(12, 14, 12, 12)});

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: CustomPaint(
            foregroundPainter: _EtchedPainter(),
            child: Padding(padding: padding, child: child),
          ),
        ),
        Positioned(
          left: 10,
          top: 0,
          child: Container(
            color: Pt.chrome,
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(title, style: ui(weight: FontWeight.w700)),
          ),
        ),
      ],
    );
  }
}

class _EtchedPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final dark = Paint()
      ..color = Pt.shade
      ..style = PaintingStyle.stroke;
    final light = Paint()
      ..color = Pt.hi
      ..style = PaintingStyle.stroke;
    const r = Radius.circular(kRadius);
    canvas.drawRRect(RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5), r), dark);
    canvas.drawRRect(RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5).shift(const Offset(1, 1)), r), light);
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

/// A recessed area (list wells, image wells).
class Well extends StatelessWidget {
  final Widget child;
  final Color color;
  final EdgeInsetsGeometry padding;

  const Well({super.key, required this.child, this.color = Pt.paper, this.padding = EdgeInsets.zero});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      foregroundPainter: const _WellBorder(),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(kRadius),
        child: Container(color: color, padding: padding, child: child),
      ),
    );
  }
}

class _WellBorder extends CustomPainter {
  const _WellBorder();
  @override
  void paint(Canvas canvas, Size size) {
    final rr = RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5), const Radius.circular(kRadius));
    canvas.drawRRect(
      rr,
      Paint()
        ..color = Pt.edge
        ..style = PaintingStyle.stroke,
    );
    // inner shade on the top-left, like a sunken well
    canvas.save();
    canvas.clipRRect(rr);
    canvas.drawLine(const Offset(1, 1.5), Offset(size.width - 1, 1.5), Paint()..color = const Color(0x33000000));
    canvas.drawLine(const Offset(1.5, 1), Offset(1.5, size.height - 1), Paint()..color = const Color(0x22000000));
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

/// A horizontal hairline.
class Hairline extends StatelessWidget {
  final EdgeInsetsGeometry margin;
  const Hairline({super.key, this.margin = EdgeInsets.zero});

  @override
  Widget build(BuildContext context) =>
      Container(margin: margin, height: 1, color: Pt.rule);
}

// ---- property table --------------------------------------------------------

class Prop {
  final String label;
  final String value;
  final bool monospace;
  final String? hint; // tooltip on the label
  final Color? color;
  final bool bold;
  final String? note; // plain-language explanation shown under the value
  final int maxLines;
  const Prop(this.label, this.value, {this.monospace = true, this.hint, this.color, this.bold = false, this.note, this.maxLines = 2});
}

/// Label | value rows with hairlines between them, label column at a fixed
/// width so values of neighbouring panels line up. Long values are ellipsised
/// in the middle-ish (end) and show the full text in a tooltip.
class PropertyTable extends StatelessWidget {
  final List<Prop> rows;
  final double labelWidth;
  final bool zebra;

  const PropertyTable({super.key, required this.rows, this.labelWidth = 104, this.zebra = false});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < rows.length; i++)
          Container(
            constraints: const BoxConstraints(minHeight: 22),
            decoration: BoxDecoration(
              color: zebra && i.isOdd ? Pt.stripe : null,
              border: i == rows.length - 1 ? null : const Border(bottom: BorderSide(color: Color(0xFFE3E1DB))),
            ),
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: labelWidth,
                  child: rows[i].hint == null
                      ? Text(rows[i].label, style: ui(color: Pt.ink2))
                      : Tooltip(
                          message: rows[i].hint!,
                          child: Text(rows[i].label, style: ui(color: Pt.ink2)),
                        ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Tooltip(
                        message: rows[i].value,
                        waitDuration: const Duration(milliseconds: 700),
                        child: Text(
                          rows[i].value,
                          maxLines: rows[i].maxLines,
                          overflow: TextOverflow.ellipsis,
                          style: (rows[i].monospace ? mono(size: 11.5) : ui()).copyWith(
                            color: rows[i].color ?? Pt.ink,
                            fontWeight: rows[i].bold ? FontWeight.w700 : null,
                          ),
                        ),
                      ),
                      if (rows[i].note != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 2),
                          child: Text(rows[i].note!, style: captionStyle()),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

// ---- grid table ------------------------------------------------------------

class GridColumn {
  final String label;
  final double? width; // fixed; null = flex
  final int flex;
  final TextAlign align;
  final String? tooltip;
  const GridColumn(this.label, {this.width, this.flex = 1, this.align = TextAlign.left, this.tooltip});
}

/// Classic list-view table: bevelled header cells, zebra rows, hairline column
/// dividers. Cells are strings (monospace) or arbitrary widgets.
class GridTable extends StatelessWidget {
  final List<GridColumn> columns;
  final List<List<Object>> rows; // each cell: String or Widget
  final bool monospace;
  final int? selected;
  final double rowHeight;
  final double cellPadding;

  const GridTable({
    super.key,
    required this.columns,
    required this.rows,
    this.monospace = true,
    this.selected,
    this.rowHeight = 22,
    this.cellPadding = 7,
  });

  Widget _cell(GridColumn c, Widget child) {
    final padded = Padding(padding: EdgeInsets.symmetric(horizontal: cellPadding), child: child);
    return c.width != null ? SizedBox(width: c.width, child: padded) : Expanded(flex: c.flex, child: padded);
  }

  Alignment _alignment(TextAlign a) =>
      a == TextAlign.right ? Alignment.centerRight : (a == TextAlign.center ? Alignment.center : Alignment.centerLeft);

  @override
  Widget build(BuildContext context) {
    return Well(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            height: 22,
            decoration: const BoxDecoration(
              gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.chromeHi, Pt.chromeLo]),
              border: Border(bottom: BorderSide(color: Pt.shade)),
            ),
            child: Row(
              children: [
                for (var i = 0; i < columns.length; i++)
                  _cell(
                    columns[i],
                    Container(
                      alignment: _alignment(columns[i].align),
                      decoration: i == 0 ? null : const BoxDecoration(),
                      child: Tooltip(
                        message: columns[i].tooltip ?? '',
                        child: Text(
                          columns[i].label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: ui(weight: FontWeight.w700, size: 11.5),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          for (var r = 0; r < rows.length; r++)
            Container(
              constraints: BoxConstraints(minHeight: rowHeight),
              color: selected == r ? Pt.accentWash : (r.isOdd ? Pt.stripe : Pt.paper),
              child: Row(
                children: [
                  for (var i = 0; i < columns.length; i++)
                    _cell(
                      columns[i],
                      Container(
                        alignment: _alignment(columns[i].align),
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: rows[r][i] is Widget
                            ? rows[r][i] as Widget
                            : Text(
                                rows[r][i] as String,
                                textAlign: columns[i].align,
                                style: monospace ? mono(size: 11.5) : ui(),
                              ),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

// ---- LCD readouts ----------------------------------------------------------

enum Tone { normal, good, warn, bad }

Color toneColor(Tone t) => switch (t) {
      Tone.good => Pt.green,
      Tone.warn => Pt.amber,
      Tone.bad => Pt.red,
      Tone.normal => Pt.ink,
    };

/// One headline number on a pale-green LCD, with a caption below. The value
/// counts up when it first appears.
class LcdReadout extends StatelessWidget {
  final String label;
  final String value;
  final String? unit;
  final String? caption;
  final Tone tone;

  const LcdReadout({super.key, required this.label, required this.value, this.unit, this.caption, this.tone = Tone.normal});

  @override
  Widget build(BuildContext context) {
    final numeric = double.tryParse(value);
    final decimals = value.contains('.') ? value.split('.').last.length : 0;
    final color = tone == Tone.normal ? Pt.lcdInk : Color.lerp(Pt.lcdInk, toneColor(tone), 0.75)!;
    Widget text(String s) => Text(s, style: mono(size: 26, weight: FontWeight.w700, color: color, height: 1.1), maxLines: 1);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: ui(weight: FontWeight.w700), maxLines: 1, overflow: TextOverflow.ellipsis),
        const SizedBox(height: 4),
        CustomPaint(
          foregroundPainter: const _LcdFrame(),
          child: Container(
            height: 48,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(3),
              gradient: const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFFC3CBB0), Pt.lcdBg]),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Expanded(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      alignment: Alignment.centerLeft,
                      child: numeric == null
                          ? text(value)
                          : TweenAnimationBuilder<double>(
                              tween: Tween(begin: 0, end: numeric),
                              duration: const Duration(milliseconds: 700),
                              curve: Curves.easeOutCubic,
                              builder: (context, v, _) => text(v.toStringAsFixed(decimals)),
                            ),
                    ),
                  ),
                ),
                if (unit != null) ...[
                  const SizedBox(width: 5),
                  Text(unit!, style: mono(size: 12, color: Pt.lcdDim, weight: FontWeight.w700)),
                ],
              ],
            ),
          ),
        ),
        if (caption != null) ...[
          const SizedBox(height: 4),
          Text(caption!, style: captionStyle(), maxLines: 3, overflow: TextOverflow.ellipsis),
        ],
      ],
    );
  }
}

class _LcdFrame extends CustomPainter {
  const _LcdFrame();
  @override
  void paint(Canvas canvas, Size size) {
    final rr = RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5), const Radius.circular(3));
    canvas.drawRRect(
      rr,
      Paint()
        ..color = const Color(0xFF3A3F32)
        ..style = PaintingStyle.stroke,
    );
    canvas.save();
    canvas.clipRRect(rr);
    canvas.drawLine(const Offset(1, 1.5), Offset(size.width - 1, 1.5), Paint()..color = const Color(0x55000000));
    canvas.drawLine(const Offset(1.5, 1), Offset(1.5, size.height - 1), Paint()..color = const Color(0x33000000));
    canvas.drawLine(Offset(1, size.height - 1.5), Offset(size.width - 1, size.height - 1.5), Paint()..color = const Color(0x55FFFFFF));
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

/// A row of equal-width LCD readouts: the headline of a screen.
class ReadoutBar extends StatelessWidget {
  final List<LcdReadout> items;
  const ReadoutBar({super.key, required this.items});

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < items.length; i++) ...[
          if (i > 0) const SizedBox(width: 14),
          Expanded(child: items[i]),
        ],
      ],
    );
  }
}

// ---- meters and progress ---------------------------------------------------

/// A sunken horizontal meter filled to `value` (0..1), segmented like a
/// level meter. The fill animates from empty.
class Meter extends StatelessWidget {
  final double value;
  final bool highlight;
  final double height;

  const Meter({super.key, required this.value, this.highlight = true, this.height = 14});

  @override
  Widget build(BuildContext context) {
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: value.clamp(0.0, 1.0)),
      duration: const Duration(milliseconds: 600),
      curve: Curves.easeOutCubic,
      builder: (context, v, _) => SizedBox(
        height: height,
        child: CustomPaint(painter: _MeterPainter(v, highlight)),
      ),
    );
  }
}

class _MeterPainter extends CustomPainter {
  final double value;
  final bool highlight;
  _MeterPainter(this.value, this.highlight);

  @override
  void paint(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final rr = RRect.fromRectAndRadius(rect.deflate(0.5), const Radius.circular(3));
    canvas.drawRRect(rr, Paint()..color = const Color(0xFFEDEBE6));
    final fillW = (size.width - 4) * value;
    if (fillW > 0) {
      final fill = RRect.fromRectAndRadius(Rect.fromLTWH(2, 2, fillW, size.height - 4), const Radius.circular(2));
      canvas.drawRRect(
        fill,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: highlight ? const [Pt.accentHi, Pt.accent] : const [Color(0xFFC9C7C0), Color(0xFF9A978F)],
          ).createShader(fill.outerRect),
      );
      canvas.drawLine(
        const Offset(3, 3.5),
        Offset(2 + fillW - 1, 3.5),
        Paint()..color = Colors.white.withValues(alpha: 0.5),
      );
    }
    // level-meter ticks
    final tick = Paint()..color = Pt.shade.withValues(alpha: 0.35);
    for (var i = 1; i < 10; i++) {
      final x = size.width * i / 10;
      canvas.drawLine(Offset(x, size.height - 4), Offset(x, size.height - 1.5), tick);
    }
    canvas.drawRRect(
      rr,
      Paint()
        ..color = Pt.edge
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(_MeterPainter old) => old.value != value || old.highlight != highlight;
}

/// Aqua barber-pole progress bar (indeterminate).
class BarberPole extends StatefulWidget {
  final double width;
  final double height;
  const BarberPole({super.key, this.width = 220, this.height = 14});

  @override
  State<BarberPole> createState() => _BarberPoleState();
}

class _BarberPoleState extends State<BarberPole> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 700))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.width,
      height: widget.height,
      child: AnimatedBuilder(
        animation: _c,
        builder: (context, _) => CustomPaint(painter: _PolePainter(_c.value)),
      ),
    );
  }
}

class _PolePainter extends CustomPainter {
  final double phase;
  _PolePainter(this.phase);

  @override
  void paint(Canvas canvas, Size size) {
    final rr = RRect.fromRectAndRadius((Offset.zero & size).deflate(0.5), Radius.circular(size.height / 2));
    canvas.save();
    canvas.clipRRect(rr);
    canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFFEDEBE6));
    const stripe = 16.0;
    final p = Paint()..color = Pt.accent;
    final light = Paint()..color = Pt.accentHi;
    for (double x = -stripe * 2 + phase * stripe * 2; x < size.width + stripe; x += stripe * 2) {
      final path = Path()
        ..moveTo(x, size.height)
        ..lineTo(x + stripe, size.height)
        ..lineTo(x + stripe + size.height, 0)
        ..lineTo(x + size.height, 0)
        ..close();
      canvas.drawPath(path, p);
      final path2 = Path()
        ..moveTo(x + stripe, size.height)
        ..lineTo(x + stripe * 2, size.height)
        ..lineTo(x + stripe * 2 + size.height, 0)
        ..lineTo(x + stripe + size.height, 0)
        ..close();
      canvas.drawPath(path2, light);
    }
    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height / 2),
      Paint()..color = Colors.white.withValues(alpha: 0.28),
    );
    canvas.restore();
    canvas.drawRRect(
      rr,
      Paint()
        ..color = Pt.edge
        ..style = PaintingStyle.stroke,
    );
  }

  @override
  bool shouldRepaint(_PolePainter old) => old.phase != phase;
}

/// Small spinning "wait" indicator: a thin ring with a moving arc.
class Spinner extends StatelessWidget {
  final double size;
  const Spinner({super.key, this.size = 16});

  @override
  Widget build(BuildContext context) => SizedBox(
        width: size,
        height: size,
        child: const CircularProgressIndicator(strokeWidth: 2, color: Pt.accent),
      );
}

// ---- callouts and status ---------------------------------------------------

enum CalloutKind { info, warn, error, ok }

/// Alert-style message box: a coloured edge, an icon and a short body. Used
/// for verdicts, errors and explanations that must not be missed.
class Callout extends StatelessWidget {
  final CalloutKind kind;
  final String title;
  final Widget? child;

  const Callout({super.key, required this.kind, required this.title, this.child});

  @override
  Widget build(BuildContext context) {
    final (Color c, Color wash, IconData icon) = switch (kind) {
      CalloutKind.error => (Pt.red, Pt.redWash, Icons.error),
      CalloutKind.warn => (Pt.amber, Pt.amberWash, Icons.warning_amber_rounded),
      CalloutKind.ok => (Pt.green, Pt.greenWash, Icons.check_circle),
      CalloutKind.info => (Pt.accent, Pt.accentWash, Icons.info),
    };
    return Container(
      decoration: BoxDecoration(
        color: wash,
        borderRadius: BorderRadius.circular(kRadius),
        border: Border.all(color: c.withValues(alpha: 0.7)),
      ),
      padding: const EdgeInsets.all(10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 20, color: c),
          const SizedBox(width: 9),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: ui(weight: FontWeight.w700, color: Pt.ink, size: 12.5)),
                if (child != null) ...[const SizedBox(height: 3), child!],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

Color statusColor(String status) {
  switch (status) {
    case 'done':
      return Pt.green;
    case 'running':
    case 'no fit':
      return Pt.amber;
    case 'error':
      return Pt.red;
    default:
      return Pt.ink3;
  }
}

/// A round LED plus a status word. Running pulses.
class StatusBadge extends StatefulWidget {
  final String status;
  final bool showText;

  const StatusBadge({super.key, required this.status, this.showText = true});

  @override
  State<StatusBadge> createState() => _StatusBadgeState();
}

class _StatusBadgeState extends State<StatusBadge> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));

  @override
  void initState() {
    super.initState();
    if (widget.status == 'running') _c.repeat(reverse: true);
  }

  @override
  void didUpdateWidget(StatusBadge old) {
    super.didUpdateWidget(old);
    if (widget.status == 'running' && !_c.isAnimating) {
      _c.repeat(reverse: true);
    } else if (widget.status != 'running' && _c.isAnimating) {
      _c.stop();
      _c.value = 0;
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = statusColor(widget.status);
    final led = AnimatedBuilder(
      animation: _c,
      builder: (context, _) => Container(
        width: 10,
        height: 10,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            center: const Alignment(-0.3, -0.4),
            colors: [Color.lerp(color, Colors.white, 0.65)!, color],
          ),
          border: Border.all(color: Color.lerp(color, Colors.black, 0.45)!, width: 1),
          boxShadow: widget.status == 'running'
              ? [BoxShadow(color: color.withValues(alpha: 0.2 + 0.5 * _c.value), blurRadius: 5, spreadRadius: 1)]
              : null,
        ),
      ),
    );
    if (!widget.showText) return led;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        led,
        const SizedBox(width: 6),
        Text(widget.status, style: ui(weight: FontWeight.w700, color: Color.lerp(color, Colors.black, 0.2)!)),
      ],
    );
  }
}

/// A small on/off tag: tick or dash, then a label. Used for "options in use".
class FlagTag extends StatelessWidget {
  final String label;
  final bool on;
  final String? tooltip;
  const FlagTag({super.key, required this.label, required this.on, this.tooltip});

  @override
  Widget build(BuildContext context) {
    final w = Container(
      padding: const EdgeInsets.fromLTRB(5, 2, 8, 2),
      decoration: BoxDecoration(
        color: on ? Pt.greenWash : Pt.chromeHi,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: on ? Pt.green.withValues(alpha: 0.7) : Pt.shade),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(on ? Icons.check : Icons.remove, size: 12, color: on ? Pt.green : Pt.ink3),
          const SizedBox(width: 3),
          Text(label, style: ui(size: 11, color: on ? Pt.ink : Pt.ink2)),
        ],
      ),
    );
    return tooltip == null ? w : Tooltip(message: tooltip!, child: w);
  }
}

// ---- layout helpers --------------------------------------------------------

/// Lays children out in `columns` equal columns, each child going to the
/// currently shortest column (by the supplied weights). Symmetric gutters; each
/// panel keeps its natural height, so there are no stretched or ragged boxes.
class Masonry extends StatelessWidget {
  final List<Widget> children;
  final List<double> weights;
  final int columns;
  final double gap;

  const Masonry({super.key, required this.children, required this.weights, required this.columns, this.gap = 12})
      : assert(children.length == weights.length);

  /// Column count for a given width and minimum column width.
  static int columnsFor(double width, {double minColumn = 300, int max = 3, double gap = 12}) {
    final n = ((width + gap) / (minColumn + gap)).floor();
    return n.clamp(1, max);
  }

  @override
  Widget build(BuildContext context) {
    final n = math.max(1, columns);
    final cols = List.generate(n, (_) => <Widget>[]);
    final heights = List<double>.filled(n, 0);
    for (var i = 0; i < children.length; i++) {
      var k = 0;
      for (var j = 1; j < n; j++) {
        if (heights[j] < heights[k]) k = j;
      }
      cols[k].add(children[i]);
      heights[k] += weights[i];
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var c = 0; c < n; c++) ...[
          if (c > 0) SizedBox(width: gap),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (var i = 0; i < cols[c].length; i++) ...[
                  if (i > 0) SizedBox(height: gap),
                  cols[c][i],
                ],
              ],
            ),
          ),
        ],
      ],
    );
  }
}

/// Entrance animation: fades in and rises a few pixels; stagger with `delay`.
class Entrance extends StatefulWidget {
  final Widget child;
  final Duration delay;
  const Entrance({super.key, required this.child, this.delay = Duration.zero});

  @override
  State<Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<Entrance> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 420));
  bool _disposed = false;

  @override
  void initState() {
    super.initState();
    if (widget.delay == Duration.zero) {
      _c.forward();
    } else {
      Future.delayed(widget.delay, () {
        if (!_disposed && mounted) _c.forward();
      });
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final fade = CurvedAnimation(parent: _c, curve: Curves.easeOut);
    final move = CurvedAnimation(parent: _c, curve: kSpring);
    return AnimatedBuilder(
      animation: _c,
      builder: (context, child) => Opacity(
        opacity: fade.value.clamp(0.0, 1.0),
        child: Transform.translate(offset: Offset(0, (1 - move.value) * 14), child: child),
      ),
      child: widget.child,
    );
  }
}
