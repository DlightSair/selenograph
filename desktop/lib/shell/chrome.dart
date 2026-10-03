// The frame around every screen: a Mac-style menu bar with a clock, a source-list
// sidebar whose blue selection slides between items, and a status bar with a
// path trail and the server state.
import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/moon.dart';
import '../ui/panels.dart';
import 'app_controller.dart';

// ---- menu bar --------------------------------------------------------------

class AppMenuBar extends StatefulWidget {
  final AppController controller;
  const AppMenuBar({super.key, required this.controller});

  @override
  State<AppMenuBar> createState() => _AppMenuBarState();
}

class _AppMenuBarState extends State<AppMenuBar> {
  Timer? _clock;
  DateTime _now = DateTime.now();

  @override
  void initState() {
    super.initState();
    _clock = Timer.periodic(const Duration(seconds: 20), (_) {
      if (mounted) setState(() => _now = DateTime.now());
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    super.dispose();
  }

  Widget _item(String label, VoidCallback? onPressed) => MenuItemButton(
        onPressed: onPressed,
        child: Text(label),
      );

  @override
  Widget build(BuildContext context) {
    final c = widget.controller;
    return AnimatedBuilder(
      animation: c,
      builder: (context, _) {
        final p = c.project;
        final menuTheme = MenuThemeData(
          style: MenuStyle(
            backgroundColor: const WidgetStatePropertyAll(Pt.chromeHi),
            surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
            shadowColor: const WidgetStatePropertyAll(Color(0x66000000)),
            elevation: const WidgetStatePropertyAll(8),
            padding: const WidgetStatePropertyAll(EdgeInsets.symmetric(vertical: 3)),
            shape: WidgetStatePropertyAll(RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(kRadius),
              side: const BorderSide(color: Pt.edge),
            )),
          ),
        );
        final buttonStyle = ButtonStyle(
          foregroundColor: WidgetStateProperty.resolveWith((s) {
            if (s.contains(WidgetState.disabled)) return Pt.ink3;
            if (s.contains(WidgetState.hovered) || s.contains(WidgetState.focused) || s.contains(WidgetState.pressed)) return Colors.white;
            return Pt.ink;
          }),
          backgroundColor: WidgetStateProperty.resolveWith((s) {
            if (s.contains(WidgetState.disabled)) return Colors.transparent;
            if (s.contains(WidgetState.hovered) || s.contains(WidgetState.focused) || s.contains(WidgetState.pressed)) return Pt.accent;
            return Colors.transparent;
          }),
          overlayColor: const WidgetStatePropertyAll(Colors.transparent),
          textStyle: WidgetStatePropertyAll(ui()),
          shape: const WidgetStatePropertyAll(RoundedRectangleBorder()),
          padding: const WidgetStatePropertyAll(EdgeInsets.symmetric(horizontal: 12)),
          minimumSize: const WidgetStatePropertyAll(Size(0, 24)),
          iconColor: const WidgetStatePropertyAll(Pt.ink2),
        );
        // Titles in the bar highlight on hover / while open only; keyboard focus
        // highlighting is kept for the items inside the menus.
        final barStyle = buttonStyle.copyWith(
          foregroundColor: WidgetStateProperty.resolveWith((s) =>
              s.contains(WidgetState.hovered) || s.contains(WidgetState.pressed) ? Colors.white : Pt.ink),
          backgroundColor: WidgetStateProperty.resolveWith((s) =>
              s.contains(WidgetState.hovered) || s.contains(WidgetState.pressed) ? Pt.accent : Colors.transparent),
        );
        final bar = Theme(
          data: Theme.of(context).copyWith(
            menuTheme: menuTheme,
            menuButtonTheme: MenuButtonThemeData(style: buttonStyle),
            menuBarTheme: const MenuBarThemeData(
              style: MenuStyle(
                backgroundColor: WidgetStatePropertyAll(Colors.transparent),
                elevation: WidgetStatePropertyAll(0),
                shadowColor: WidgetStatePropertyAll(Colors.transparent),
                surfaceTintColor: WidgetStatePropertyAll(Colors.transparent),
                padding: WidgetStatePropertyAll(EdgeInsets.zero),
                shape: WidgetStatePropertyAll(RoundedRectangleBorder()),
                minimumSize: WidgetStatePropertyAll(Size(0, 24)),
              ),
            ),
          ),
          child: MenuBar(
            children: [
              SubmenuButton(
                style: barStyle,
                menuChildren: [
                  _item('About Selenograph', () => c.go(Section.about)),
                  const Divider(height: 7, color: Pt.rule),
                  _item('Hide / show sidebar', c.toggleSidebar),
                ],
                child: const Padding(
                  padding: EdgeInsets.symmetric(vertical: 4),
                  child: MoonIcon(size: 15, phase: 0.62),
                ),
              ),
              SubmenuButton(
                style: barStyle,
                menuChildren: [
                  _item('New project…', c.newProject),
                  _item('Refresh', c.refresh),
                ],
                child: const Text('File'),
              ),
              SubmenuButton(
                style: barStyle,
                menuChildren: [
                  _item('Projects', () => c.go(Section.projects)),
                  _item('Benchmark', () => c.go(Section.benchmark)),
                  _item('About', () => c.go(Section.about)),
                  const Divider(height: 7, color: Pt.rule),
                  _item('Back', c.canGoBack ? c.back : null),
                ],
                child: const Text('Go'),
              ),
              SubmenuButton(
                style: barStyle,
                menuChildren: [
                  _item('Run registration', p?.run),
                  _item('View latest results', p?.openLatest),
                ],
                child: const Text('Project'),
              ),
              SubmenuButton(
                style: barStyle,
                menuChildren: [
                  _item('About Selenograph', () => c.go(Section.about)),
                ],
                child: const Text('Help'),
              ),
            ],
          ),
        );
        return Container(
          height: 24,
          decoration: const BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFFF4F2EE), Pt.chromeLo]),
            border: Border(bottom: BorderSide(color: Pt.edge)),
          ),
          child: Row(
            children: [
              const SizedBox(width: 4),
              bar,
              const Spacer(),
              Text(DateFormat('EEE h:mm a').format(_now), style: ui(color: Pt.ink)),
              const SizedBox(width: 12),
            ],
          ),
        );
      },
    );
  }
}

// ---- sidebar ---------------------------------------------------------------

class SidebarView extends StatelessWidget {
  final AppController controller;
  const SidebarView({super.key, required this.controller});

  static const double width = 188;
  static const double _item = 26;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final entries = <_SideEntry>[
          _SideEntry(Section.projects, CupertinoIcons.folder_fill, 'Projects', badge: controller.projectCount > 0 ? '${controller.projectCount}' : null),
          const _SideEntry(Section.benchmark, CupertinoIcons.chart_bar_alt_fill, 'Benchmark'),
          const _SideEntry(Section.about, CupertinoIcons.info_circle_fill, 'About'),
        ];
        final selected = entries.indexWhere((e) => e.section == controller.section);
        // y offset of each entry inside the list (section headers add space).
        double yOf(int i) => 22 + i * _item + (i >= 2 ? 30 : 0);
        return Container(
          width: width,
          decoration: const BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Color(0xFFEDEBE7), Pt.sidebar]),
            border: Border(right: BorderSide(color: Pt.edge)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 14, 12, 14),
                child: Row(
                  children: [
                    const MoonIcon(size: 34, phase: 0.62),
                    const SizedBox(width: 9),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Selenograph', style: ui(size: 14, weight: FontWeight.w700, height: 1.1)),
                          const SizedBox(height: 2),
                          Text('Image registration', style: captionStyle()),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const Hairline(),
              Expanded(
                child: Stack(
                  children: [
                    AnimatedPositioned(
                      duration: const Duration(milliseconds: 320),
                      curve: kSpring,
                      left: 6,
                      right: 6,
                      top: yOf(selected < 0 ? 0 : selected),
                      height: _item,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(kRadius),
                          gradient: const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.accentHi, Pt.accent]),
                          border: Border.all(color: Pt.accentLo),
                        ),
                      ),
                    ),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        _header('Workspace'),
                        _row(entries[0]),
                        _row(entries[1]),
                        const SizedBox(height: 8),
                        _header('Help'),
                        _row(entries[2]),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _header(String t) => SizedBox(
        height: 22,
        child: Padding(
          padding: const EdgeInsets.only(left: 14, top: 6),
          child: Text(t, style: ui(size: 11, weight: FontWeight.w700, color: Pt.ink2)),
        ),
      );

  Widget _row(_SideEntry e) {
    final selected = controller.section == e.section;
    return PtPressable(
      onPressed: () => controller.go(e.section),
      builder: (context, hover, down, focus) {
        final fg = selected ? Colors.white : Pt.ink;
        return Container(
          height: _item,
          margin: const EdgeInsets.symmetric(horizontal: 6),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(kRadius),
            color: hover && !selected ? const Color(0x14000000) : Colors.transparent,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            children: [
              Icon(e.icon, size: 15, color: selected ? Colors.white : Pt.ink2),
              const SizedBox(width: 8),
              Expanded(child: Text(e.label, style: ui(color: fg, weight: selected ? FontWeight.w700 : FontWeight.w400))),
              if (e.badge != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                  decoration: BoxDecoration(
                    color: selected ? Colors.white.withValues(alpha: 0.28) : const Color(0x22000000),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(e.badge!, style: ui(size: 10.5, color: selected ? Colors.white : Pt.ink2, weight: FontWeight.w700)),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _SideEntry {
  final Section section;
  final IconData icon;
  final String label;
  final String? badge;
  const _SideEntry(this.section, this.icon, this.label, {this.badge});
}

// ---- status bar ------------------------------------------------------------

class StatusBarView extends StatelessWidget {
  final AppController controller;
  final String serverUrl;
  const StatusBarView({super.key, required this.controller, required this.serverUrl});

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final crumbs = controller.crumbs;
        return Container(
          height: 22,
          padding: const EdgeInsets.symmetric(horizontal: 10),
          decoration: const BoxDecoration(
            gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.chromeHi, Pt.chromeLo]),
            border: Border(top: BorderSide(color: Pt.edge)),
          ),
          child: Row(
            children: [
              const Icon(CupertinoIcons.folder, size: 12, color: Pt.ink2),
              const SizedBox(width: 6),
              Expanded(
                child: Row(
                  children: [
                    for (var i = 0; i < crumbs.length; i++) ...[
                      if (i > 0)
                        const Padding(
                          padding: EdgeInsets.symmetric(horizontal: 3),
                          child: Icon(Icons.chevron_right, size: 13, color: Pt.ink3),
                        ),
                      Flexible(
                        child: Text(
                          crumbs[i],
                          overflow: TextOverflow.ellipsis,
                          style: ui(size: 11, weight: i == crumbs.length - 1 ? FontWeight.w700 : FontWeight.w400, color: Pt.ink),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: 12),
              Tooltip(
                message: controller.serverUp ? 'The local pipeline server is answering.' : 'The local pipeline server is not answering.',
                child: Row(
                  children: [
                    StatusBadge(status: controller.serverUp ? 'done' : 'error', showText: false),
                    const SizedBox(width: 6),
                    Text(
                      controller.serverUp ? 'Server $serverUrl' : 'Server offline',
                      style: ui(size: 11, color: controller.serverUp ? Pt.ink : Pt.red),
                    ),
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
