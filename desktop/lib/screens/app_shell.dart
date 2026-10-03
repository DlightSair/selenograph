import 'dart:async';

import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../shell/app_controller.dart';
import '../shell/chrome.dart';
import '../theme/platinum.dart';
import 'about_screen.dart';
import 'benchmark_screen.dart';
import 'new_project_screen.dart';
import 'projects_screen.dart';

/// Main frame: menu bar on top, sidebar on the left, a nested navigator for
/// the content, and a status bar. The navigator is nested so the frame stays
/// put while projects and results open and close inside it. Only mounted once
/// the splash screen has confirmed the backend is reachable.
class AppShell extends StatefulWidget {
  final ApiClient api;

  const AppShell({super.key, required this.api});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final AppController _c = AppController();
  Timer? _health;

  @override
  void initState() {
    super.initState();
    _c.bindGo((s) {
      _c.navKey.currentState?.pushAndRemoveUntil(
        fadeRoute((_) => _root(s), label: s.label),
        (_) => false,
      );
    });
    _c.newProject = _openNewProject;
    _health = Timer.periodic(const Duration(seconds: 8), (_) async {
      final up = await widget.api.health();
      if (mounted) _c.setServerUp(up);
    });
  }

  @override
  void dispose() {
    _health?.cancel();
    _c.dispose();
    super.dispose();
  }

  Future<void> _openNewProject() async {
    _c.go(Section.projects);
    // Let the section switch settle, then push the form on top of the list.
    await Future<void>.delayed(const Duration(milliseconds: 30));
    final nav = _c.navKey.currentState;
    if (nav == null) return;
    await nav.push<bool>(ptRoute((_) => NewProjectScreen(api: widget.api), label: 'New project'));
    _c.refresh?.call();
  }

  Widget _root(Section s) {
    switch (s) {
      case Section.projects:
        return ProjectsScreen(api: widget.api);
      case Section.benchmark:
        return BenchmarkScreen(api: widget.api);
      case Section.about:
        return const AboutScreen();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      controller: _c,
      child: Focus(
          autofocus: true,
          child: Scaffold(
            backgroundColor: Pt.chrome,
            body: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AppMenuBar(controller: _c),
                Expanded(
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      AnimatedBuilder(
                        animation: _c,
                        builder: (context, child) => AnimatedContainer(
                          duration: const Duration(milliseconds: 280),
                          curve: Curves.easeOutCubic,
                          width: _c.sidebarVisible ? SidebarView.width : 0,
                          child: ClipRect(
                            child: OverflowBox(
                              alignment: Alignment.centerLeft,
                              minWidth: SidebarView.width,
                              maxWidth: SidebarView.width,
                              child: child,
                            ),
                          ),
                        ),
                        child: SidebarView(controller: _c),
                      ),
                      Expanded(
                        child: Navigator(
                          key: _c.navKey,
                          observers: [_c.observer],
                          onGenerateRoute: (settings) => fadeRoute((_) => _root(_c.section), label: _c.section.label),
                        ),
                      ),
                    ],
                  ),
                ),
                StatusBarView(controller: _c, serverUrl: widget.api.baseUrl.replaceFirst('http://', '')),
              ],
            ),
          ),
        ),
    );
  }
}
