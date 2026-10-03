import 'package:flutter/material.dart';

enum Section { projects, benchmark, about }

extension SectionLabel on Section {
  String get label => switch (this) {
        Section.projects => 'Projects',
        Section.benchmark => 'Benchmark',
        Section.about => 'About',
      };
}

/// What the menu bar's "Project" menu can do while a project is open. The
/// project screen registers one in `initState` and clears it on dispose.
class ProjectActions {
  final VoidCallback? run;
  final VoidCallback? openLatest;
  const ProjectActions({this.run, this.openLatest});
}

/// Shared state of the shell: the current section, the nested navigator the
/// content lives in, the breadcrumb trail, and hooks the menu bar calls.
class AppController extends ChangeNotifier {
  Section section = Section.projects;
  bool sidebarVisible = true;
  bool serverUp = true;
  int projectCount = 0;

  final GlobalKey<NavigatorState> navKey = GlobalKey<NavigatorState>(debugLabel: 'content');
  final List<String> _crumbs = [];
  List<String> get crumbs => List.unmodifiable(_crumbs);

  ProjectActions? _project;
  ProjectActions? get project => _project;

  /// Set by the shell: opens the "New project" screen.
  VoidCallback? newProject;

  /// Set by the shell: switches section (replacing the content stack).
  void Function(Section)? _go;
  void bindGo(void Function(Section) go) => _go = go;

  VoidCallback? _refresh;
  VoidCallback? get refresh => _refresh;

  void go(Section s) {
    if (section == s && (navKey.currentState?.canPop() ?? false) == false) return;
    section = s;
    _go?.call(s);
    notifyListeners();
  }

  bool get canGoBack => navKey.currentState?.canPop() ?? false;

  void back() => navKey.currentState?.maybePop();

  void toggleSidebar() {
    sidebarVisible = !sidebarVisible;
    notifyListeners();
  }

  void setServerUp(bool v) {
    if (serverUp == v) return;
    serverUp = v;
    notifyListeners();
  }

  void setProjectCount(int n) {
    if (projectCount == n) return;
    projectCount = n;
    _notifyLater();
  }

  void registerProject(ProjectActions? actions) {
    _project = actions;
    _notifyLater();
  }

  void registerRefresh(VoidCallback? cb) {
    _refresh = cb;
  }

  void _setCrumbs(List<String> c) {
    _crumbs
      ..clear()
      ..addAll(c);
    _notifyLater();
  }

  // Notifications triggered from build/initState must wait for the frame.
  bool _pending = false;
  bool _disposed = false;

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }

  void _notifyLater() {
    if (_pending || _disposed) return;
    _pending = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pending = false;
      if (!_disposed) notifyListeners();
    });
  }

  late final NavigatorObserver observer = _CrumbObserver(this);
}

/// Tracks the route stack so the status bar can show a path.
class _CrumbObserver extends NavigatorObserver {
  final AppController c;
  final List<String> _stack = [];
  _CrumbObserver(this.c);

  void _push(Route<dynamic> r) => _stack.add(r.settings.name ?? '');
  void _publish() => c._setCrumbs([for (final s in _stack) if (s.isNotEmpty) s]);

  @override
  void didPush(Route<dynamic> route, Route<dynamic>? previousRoute) {
    _push(route);
    _publish();
  }

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) {
    if (_stack.isNotEmpty) _stack.removeLast();
    _publish();
  }

  @override
  void didRemove(Route<dynamic> route, Route<dynamic>? previousRoute) {
    final i = _stack.lastIndexOf(route.settings.name ?? '');
    if (i >= 0) _stack.removeAt(i);
    _publish();
  }

  @override
  void didReplace({Route<dynamic>? newRoute, Route<dynamic>? oldRoute}) {
    if (_stack.isNotEmpty) _stack.removeLast();
    if (newRoute != null) _push(newRoute);
    _publish();
  }
}

class AppScope extends InheritedNotifier<AppController> {
  const AppScope({super.key, required AppController controller, required super.child}) : super(notifier: controller);

  static AppController of(BuildContext context) {
    final s = context.dependOnInheritedWidgetOfExactType<AppScope>();
    assert(s != null, 'No AppScope above this context');
    return s!.notifier!;
  }

  /// Without subscribing to changes (for use in callbacks / initState). Null
  /// when a screen is shown outside the shell (tests, previews).
  static AppController? maybeRead(BuildContext context) =>
      context.getInheritedWidgetOfExactType<AppScope>()?.notifier;
}
