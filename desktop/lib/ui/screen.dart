// Per-screen chrome: a pinstriped title bar with the title and actions, and the
// padded, width-limited scrolling body.
import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';

import '../theme/platinum.dart';
import 'controls.dart';

/// Title bar for a screen: pinstripes, with the title and the toolbar buttons
/// sitting on solid plates on top of them (as on a Mac OS 8/9 window).
class ScreenHeader extends StatelessWidget {
  final String title;
  final String? subtitle;
  final bool showBack;
  final VoidCallback? onBack;
  final List<Widget> actions;
  final Widget? leading;

  const ScreenHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.showBack = false,
    this.onBack,
    this.actions = const [],
    this.leading,
  });

  @override
  Widget build(BuildContext context) {
    Widget plate(Widget child) => Container(
          decoration: BoxDecoration(color: Pt.chrome, borderRadius: BorderRadius.circular(kRadius)),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          child: child,
        );
    return Container(
      height: 50,
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Pt.edge)),
      ),
      child: CustomPaint(
        painter: const PinstripePainter(),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            children: [
              if (showBack) ...[
                plate(ToolButton(icon: CupertinoIcons.chevron_back, label: 'Back', onPressed: onBack ?? () => Navigator.of(context).maybePop())),
                const SizedBox(width: 10),
              ],
              if (leading != null) ...[leading!, const SizedBox(width: 10)],
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: plate(
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: titleStyle(), maxLines: 1, overflow: TextOverflow.ellipsis),
                        if (subtitle != null) Text(subtitle!, style: captionStyle(), maxLines: 1, overflow: TextOverflow.ellipsis),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 12),
              if (actions.isNotEmpty)
                plate(
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      for (var i = 0; i < actions.length; i++) ...[
                        if (i > 0) const SizedBox(width: 8),
                        actions[i],
                      ],
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Scrolling, padded, width-limited body so wide windows do not stretch rows
/// of data across the whole screen.
class ScreenBody extends StatefulWidget {
  final Widget child;
  final double maxWidth;
  final EdgeInsetsGeometry padding;
  final ScrollController? controller;

  const ScreenBody({super.key, required this.child, this.maxWidth = 1240, this.padding = const EdgeInsets.all(14), this.controller});

  @override
  State<ScreenBody> createState() => _ScreenBodyState();
}

class _ScreenBodyState extends State<ScreenBody> {
  // Always an explicit controller: two scroll views side by side must not both
  // claim the primary one.
  late final ScrollController _own = widget.controller ?? ScrollController();

  @override
  void dispose() {
    if (widget.controller == null) _own.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final maxWidth = widget.maxWidth;
    final padding = widget.padding;
    final child = widget.child;
    return Scrollbar(
      controller: _own,
      child: SingleChildScrollView(
        controller: _own,
        padding: EdgeInsets.zero,
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(maxWidth: maxWidth),
            child: Padding(padding: padding, child: child),
          ),
        ),
      ),
    );
  }
}

/// A toolbar separator.
class ToolSeparator extends StatelessWidget {
  const ToolSeparator({super.key});

  @override
  Widget build(BuildContext context) => Container(
        width: 2,
        height: 20,
        decoration: const BoxDecoration(
          border: Border(left: BorderSide(color: Pt.shade), right: BorderSide(color: Pt.hi)),
        ),
      );
}

/// A line of plain explanatory text with the standard secondary style.
class Note extends StatelessWidget {
  final String text;
  final double size;
  final Color? color;
  const Note(this.text, {super.key, this.size = 11.5, this.color});

  @override
  Widget build(BuildContext context) => Text(text, style: ui(size: size, color: color ?? Pt.ink2, height: 1.4));
}
