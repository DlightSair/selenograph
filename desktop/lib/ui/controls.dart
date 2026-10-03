// Interactive controls in the Platinum style: push buttons (with the pulsing
// default button), toolbar buttons, a sliding segmented control, checkbox,
// search field, text field and pop-up menu.
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/platinum.dart';

/// Hover / press / keyboard-focus tracking shared by the controls below.
class PtPressable extends StatefulWidget {
  final VoidCallback? onPressed;
  final Widget Function(BuildContext context, bool hovering, bool pressed, bool focused) builder;
  final String? tooltip;
  final bool autofocus;
  final MouseCursor? cursor;

  const PtPressable({
    super.key,
    required this.onPressed,
    required this.builder,
    this.tooltip,
    this.autofocus = false,
    this.cursor,
  });

  @override
  State<PtPressable> createState() => _PtPressableState();
}

class _PtPressableState extends State<PtPressable> {
  bool _hover = false;
  bool _down = false;
  bool _focus = false;

  bool get _enabled => widget.onPressed != null;

  @override
  Widget build(BuildContext context) {
    Widget w = FocusableActionDetector(
      enabled: _enabled,
      autofocus: widget.autofocus,
      mouseCursor: widget.cursor ?? (_enabled ? SystemMouseCursors.click : SystemMouseCursors.basic),
      onShowHoverHighlight: (v) => setState(() => _hover = v),
      onShowFocusHighlight: (v) => setState(() => _focus = v),
      actions: {
        ActivateIntent: CallbackAction<ActivateIntent>(onInvoke: (_) {
          widget.onPressed?.call();
          return null;
        }),
      },
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: _enabled ? (_) => setState(() => _down = true) : null,
        onTapUp: _enabled ? (_) => setState(() => _down = false) : null,
        onTapCancel: _enabled ? () => setState(() => _down = false) : null,
        onTap: widget.onPressed,
        child: widget.builder(context, _hover && _enabled, _down && _enabled, _focus && _enabled),
      ),
    );
    if (widget.tooltip != null) w = Tooltip(message: widget.tooltip!, child: w);
    return w;
  }
}

/// Blue focus ring around a rounded box, as on macOS.
class FocusRing extends StatelessWidget {
  final bool show;
  final double radius;
  final Widget child;

  const FocusRing({super.key, required this.show, required this.child, this.radius = kRadius});

  @override
  Widget build(BuildContext context) {
    return AnimatedContainer(
      duration: kFast,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius + 1),
        boxShadow: show ? [BoxShadow(color: Pt.accent.withValues(alpha: 0.45), spreadRadius: 2.5)] : const [],
      ),
      child: child,
    );
  }
}

/// The classic push button. `isDefault` paints it as the blue Aqua default
/// button, which pulses gently while it is enabled.
class PushButton extends StatefulWidget {
  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool isDefault;
  final bool compact;
  final String? tooltip;
  final double? minWidth;

  const PushButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.isDefault = false,
    this.compact = false,
    this.tooltip,
    this.minWidth,
  });

  @override
  State<PushButton> createState() => _PushButtonState();
}

class _PushButtonState extends State<PushButton> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1100));

  @override
  void initState() {
    super.initState();
    _syncPulse();
  }

  @override
  void didUpdateWidget(PushButton old) {
    super.didUpdateWidget(old);
    _syncPulse();
  }

  void _syncPulse() {
    final shouldPulse = widget.isDefault && widget.onPressed != null;
    if (shouldPulse && !_pulse.isAnimating) {
      _pulse.repeat(reverse: true);
    } else if (!shouldPulse && _pulse.isAnimating) {
      _pulse.stop();
      _pulse.value = 0;
    }
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final disabled = widget.onPressed == null;
    final height = widget.compact ? 22.0 : 26.0;
    return PtPressable(
      onPressed: widget.onPressed,
      tooltip: widget.tooltip,
      builder: (context, hover, down, focus) {
        final isDef = widget.isDefault && !disabled;
        final fg = disabled ? Pt.ink3 : (isDef ? Colors.white : Pt.ink);
        final Color top;
        final Color bottom;
        final Color outline;
        if (disabled) {
          top = const Color(0xFFE2E0DB);
          bottom = const Color(0xFFD4D2CC);
          outline = Pt.shade;
        } else if (isDef) {
          top = down ? Pt.accentLo : Pt.accentHi;
          bottom = down ? Pt.accent : Pt.accent;
          outline = Pt.accentLo;
        } else {
          top = down ? Pt.chromeLo : Pt.chromeHi;
          bottom = down ? const Color(0xFFBDBBB3) : Pt.chromeLo;
          outline = Pt.edge;
        }
        final label = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.icon != null) ...[
              Icon(widget.icon, size: 15, color: fg),
              const SizedBox(width: 6),
            ],
            Text(
              widget.label,
              style: ui(
                weight: isDef ? FontWeight.w700 : FontWeight.w400,
                color: fg,
              ),
            ),
          ],
        );
        final face = Container(
          constraints: BoxConstraints(minWidth: widget.minWidth ?? (widget.compact ? 0 : 76), minHeight: height),
          padding: EdgeInsets.symmetric(horizontal: widget.compact ? 10 : 16),
          alignment: Alignment.center,
          child: Transform.translate(offset: Offset(0, down ? 0.5 : 0), child: label),
        );
        Widget button = Stack(
          children: [
            Positioned.fill(
              child: CustomPaint(
                painter: BevelPainter(
                  style: down ? BevelStyle.sunken : BevelStyle.raised,
                  top: top,
                  bottom: bottom,
                  outline: outline,
                  bevel: !isDef,
                ),
              ),
            ),
            // Hover: a soft white wash that fades in.
            Positioned.fill(
              child: IgnorePointer(
                child: AnimatedOpacity(
                  duration: kFast,
                  opacity: hover && !down ? 0.28 : 0,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(kRadius),
                    ),
                  ),
                ),
              ),
            ),
            face,
          ],
        );
        if (isDef) {
          // Aqua pulse: the glow breathes while the button is the default action.
          button = AnimatedBuilder(
            animation: _pulse,
            builder: (context, child) {
              final glow = focus ? 0.5 : 0.10 + 0.32 * Curves.easeInOut.transform(_pulse.value);
              return DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(kRadius + 1),
                  boxShadow: [BoxShadow(color: Pt.accent.withValues(alpha: glow), spreadRadius: 2.5)],
                ),
                child: child,
              );
            },
            child: button,
          );
        } else {
          button = FocusRing(show: focus, child: button);
        }
        return button;
      },
    );
  }
}

/// A flat toolbar button: just an icon and a label until hovered, then it
/// rises into a bevelled button; pressed or toggled-on it sinks.
class ToolButton extends StatelessWidget {
  final IconData icon;
  final String? label;
  final VoidCallback? onPressed;
  final String? tooltip;
  final bool active;

  const ToolButton({super.key, required this.icon, this.label, required this.onPressed, this.tooltip, this.active = false});

  @override
  Widget build(BuildContext context) {
    return PtPressable(
      onPressed: onPressed,
      tooltip: tooltip ?? label,
      builder: (context, hover, down, focus) {
        final disabled = onPressed == null;
        final fg = disabled ? Pt.ink3 : Pt.ink;
        final sunk = down || active;
        return FocusRing(
          show: focus,
          child: Stack(
            children: [
              Positioned.fill(
                child: AnimatedOpacity(
                  duration: kFast,
                  opacity: (hover || sunk) && !disabled ? 1 : 0,
                  child: CustomPaint(
                    painter: BevelPainter(
                      style: sunk ? BevelStyle.sunken : BevelStyle.raised,
                      top: sunk ? (active ? Pt.accentWash : Pt.chromeLo) : Pt.chromeHi,
                      bottom: sunk ? (active ? Pt.accentWash : Pt.chromeLo) : Pt.chromeLo,
                    ),
                  ),
                ),
              ),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: label == null ? 6 : 9, vertical: 4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(icon, size: 17, color: fg),
                    if (label != null) ...[
                      const SizedBox(width: 5),
                      Text(label!, style: ui(color: fg)),
                    ],
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class SegmentOption<T> {
  final T value;
  final String label;
  final IconData? icon;
  const SegmentOption(this.value, this.label, {this.icon});
}

/// Joined segmented control; the blue selection slides between segments.
class SegmentedControl<T> extends StatelessWidget {
  final List<SegmentOption<T>> options;
  final T value;
  final ValueChanged<T> onChanged;
  final double segmentWidth;

  const SegmentedControl({
    super.key,
    required this.options,
    required this.value,
    required this.onChanged,
    this.segmentWidth = 88,
  });

  @override
  Widget build(BuildContext context) {
    final index = options.indexWhere((o) => o.value == value).clamp(0, options.length - 1);
    const h = 24.0;
    return SizedBox(
      width: segmentWidth * options.length,
      height: h,
      child: Stack(
        children: [
          const Positioned.fill(child: CustomPaint(painter: BevelPainter(style: BevelStyle.raised))),
          AnimatedPositioned(
            duration: const Duration(milliseconds: 280),
            curve: kSpring,
            left: segmentWidth * index,
            top: 0,
            width: segmentWidth,
            height: h,
            child: const CustomPaint(
              painter: BevelPainter(top: Pt.accentHi, bottom: Pt.accent, outline: Pt.accentLo, bevel: false),
            ),
          ),
          Row(
            children: [
              for (var i = 0; i < options.length; i++)
                SizedBox(
                  width: segmentWidth,
                  child: PtPressable(
                    onPressed: () => onChanged(options[i].value),
                    builder: (context, hover, down, focus) {
                      final selected = i == index;
                      return Container(
                        alignment: Alignment.center,
                        decoration: BoxDecoration(
                          border: i > 0 && i != index && i - 1 != index
                              ? const Border(left: BorderSide(color: Pt.shade))
                              : null,
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (options[i].icon != null) ...[
                              Icon(options[i].icon, size: 14, color: selected ? Colors.white : Pt.ink),
                              const SizedBox(width: 5),
                            ],
                            AnimatedDefaultTextStyle(
                              duration: kMedium,
                              style: ui(
                                color: selected ? Colors.white : (hover ? Pt.accentLo : Pt.ink),
                                weight: selected ? FontWeight.w700 : FontWeight.w400,
                              ),
                              child: Text(options[i].label),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Square checkbox with a drawn tick and a clickable label.
class PtCheckbox extends StatelessWidget {
  final bool value;
  final String label;
  final ValueChanged<bool>? onChanged;
  final String? hint;

  const PtCheckbox({super.key, required this.value, required this.label, required this.onChanged, this.hint});

  @override
  Widget build(BuildContext context) {
    return PtPressable(
      onPressed: onChanged == null ? null : () => onChanged!(!value),
      builder: (context, hover, down, focus) {
        return Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            FocusRing(
              show: focus,
              radius: 2,
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
                        scale: value ? 1 : 0,
                        child: const Icon(Icons.check, size: 13, color: Pt.accentLo, weight: 900),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 7),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: ui(color: onChanged == null ? Pt.ink3 : Pt.ink)),
                  if (hint != null) Text(hint!, style: captionStyle()),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}

/// Rounded search field with a magnifier and a clear button.
class SearchBox extends StatefulWidget {
  final String hint;
  final ValueChanged<String> onChanged;
  final double width;

  const SearchBox({super.key, required this.onChanged, this.hint = 'Search', this.width = 200});

  @override
  State<SearchBox> createState() => _SearchBoxState();
}

class _SearchBoxState extends State<SearchBox> {
  final _ctrl = TextEditingController();
  final _focus = FocusNode();
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() => _focused = _focus.hasFocus));
    _ctrl.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FocusRing(
      show: _focused,
      radius: 12,
      child: SizedBox(
        width: widget.width,
        height: 24,
        child: Stack(
          children: [
            const Positioned.fill(child: CustomPaint(painter: BevelPainter(style: BevelStyle.sunken, radius: 12))),
            Padding(
              padding: const EdgeInsets.only(left: 8, right: 6),
              child: Row(
                children: [
                  const Icon(Icons.search, size: 15, color: Pt.ink2),
                  const SizedBox(width: 5),
                  Expanded(
                    child: TextField(
                      controller: _ctrl,
                      focusNode: _focus,
                      onChanged: widget.onChanged,
                      style: ui(),
                      cursorWidth: 1,
                      decoration: InputDecoration(
                        isCollapsed: true,
                        border: InputBorder.none,
                        hintText: widget.hint,
                        hintStyle: ui(color: Pt.ink3),
                      ),
                    ),
                  ),
                  if (_ctrl.text.isNotEmpty)
                    GestureDetector(
                      onTap: () {
                        _ctrl.clear();
                        widget.onChanged('');
                      },
                      child: const MouseRegion(
                        cursor: SystemMouseCursors.click,
                        child: Icon(Icons.cancel, size: 14, color: Pt.ink3),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A sunken single-line (or multi-line) text field with validation, used in
/// forms. Validation reads the controller directly, so values set by a
/// "Browse..." button validate correctly.
class PtTextField extends StatefulWidget {
  final TextEditingController controller;
  final String? hint;
  final String? Function(String value)? validator;
  final TextInputType? keyboardType;
  final bool monospace;
  final List<TextInputFormatter>? inputFormatters;

  const PtTextField({
    super.key,
    required this.controller,
    this.hint,
    this.validator,
    this.keyboardType,
    this.monospace = true,
    this.inputFormatters,
  });

  @override
  State<PtTextField> createState() => _PtTextFieldState();
}

class _PtTextFieldState extends State<PtTextField> {
  final _focus = FocusNode();
  bool _focused = false;

  @override
  void initState() {
    super.initState();
    _focus.addListener(() => setState(() => _focused = _focus.hasFocus));
  }

  @override
  void dispose() {
    _focus.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FormField<String>(
      initialValue: widget.controller.text,
      autovalidateMode: AutovalidateMode.onUserInteraction,
      validator: (_) => widget.validator?.call(widget.controller.text.trim()),
      builder: (state) {
        final hasError = state.hasError;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            FocusRing(
              show: _focused,
              child: SizedBox(
                height: 24,
                child: Stack(
                  children: [
                    Positioned.fill(
                      child: CustomPaint(
                        painter: BevelPainter(
                          style: BevelStyle.sunken,
                          outline: hasError ? Pt.red : Pt.edge,
                        ),
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 7),
                      child: TextField(
                        controller: widget.controller,
                        focusNode: _focus,
                        keyboardType: widget.keyboardType,
                        inputFormatters: widget.inputFormatters,
                        onChanged: state.didChange,
                        cursorWidth: 1,
                        style: widget.monospace ? mono() : ui(),
                        textAlignVertical: TextAlignVertical.center,
                        decoration: InputDecoration(
                          isCollapsed: true,
                          border: InputBorder.none,
                          hintText: widget.hint,
                          hintStyle: ui(color: Pt.ink3, size: 11.5),
                          contentPadding: const EdgeInsets.symmetric(vertical: 5),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            if (hasError)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.error, size: 12, color: Pt.red),
                    const SizedBox(width: 4),
                    Text(state.errorText ?? '', style: ui(size: 11, color: Pt.red)),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

/// Pop-up menu (the Mac double-chevron style).
class PtPopup<T> extends StatelessWidget {
  final T value;
  final List<T> items;
  final String Function(T) labelOf;
  final ValueChanged<T> onChanged;
  final double width;

  const PtPopup({
    super.key,
    required this.value,
    required this.items,
    required this.onChanged,
    String Function(T)? labelOf,
    this.width = 160,
  }) : labelOf = labelOf ?? _defaultLabel;

  static String _defaultLabel(Object? v) => '$v';

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: 24,
      child: Stack(
        children: [
          const Positioned.fill(child: CustomPaint(painter: BevelPainter())),
          Padding(
            padding: const EdgeInsets.only(left: 9, right: 2),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<T>(
                value: value,
                isExpanded: true,
                isDense: true,
                focusColor: Colors.transparent,
                dropdownColor: Pt.paper,
                borderRadius: BorderRadius.circular(kRadius),
                icon: const Icon(Icons.unfold_more, size: 16, color: Pt.ink),
                style: ui(),
                items: [
                  for (final i in items) DropdownMenuItem<T>(value: i, child: Text(labelOf(i), style: ui())),
                ],
                onChanged: (v) {
                  if (v != null) onChanged(v);
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}
