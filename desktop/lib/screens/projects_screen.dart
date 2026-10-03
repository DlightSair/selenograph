import 'dart:async';

import 'package:flutter/cupertino.dart' show CupertinoIcons;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';

import '../models/config_summary.dart';
import '../models/run_summary.dart';
import '../services/api_client.dart';
import '../shell/app_controller.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';
import 'new_project_screen.dart';
import 'project_detail_screen.dart';

/// The project list as a classic list view: one row per project with its
/// latest result, sortable columns, a search field, and keyboard navigation.
class ProjectsScreen extends StatefulWidget {
  final ApiClient api;

  const ProjectsScreen({super.key, required this.api});

  @override
  State<ProjectsScreen> createState() => _ProjectsScreenState();
}

enum _Col { name, status, instrument, lat, lon, dem, rmse, heldout, when }

class _Row {
  final ConfigSummary config;
  final RunSummary? run;
  _Row(this.config, this.run);

  double? get rmse => run?.metrics?.rmseM;
  double? get heldout => run?.metrics?.heldoutRmseM;
  String? get when => run?.finishedAt ?? run?.startedAt;
  String get status => run == null ? 'none' : run!.displayStatus;

  /// The status as shown in the Status column.
  String get statusWord => switch (status) {
        'done' => 'registered',
        'no fit' => 'no fit',
        'error' => 'run failed',
        'running' => 'running',
        _ => 'not run',
      };
}

class _ProjectsScreenState extends State<ProjectsScreen> {
  List<_Row>? _rows;
  String? _error;
  String _filter = '';
  _Col _sortCol = _Col.name;
  bool _asc = true;
  int? _selected; // index into the *visible* list
  final _focus = FocusNode();
  final _scroll = ScrollController();
  AppController? _app;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _app ??= AppScope.maybeRead(context);
    _app?.registerRefresh(_load);
  }

  @override
  void dispose() {
    _app?.registerRefresh(null);
    _focus.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([widget.api.listConfigs(), widget.api.listRuns(limit: 500)]);
      final configs = results[0] as List<ConfigSummary>;
      final runs = results[1] as List<RunSummary>;
      // listRuns is newest first, so the first run seen per config is its latest.
      final latest = <String, RunSummary>{};
      for (final r in runs) {
        if (r.config != null) latest.putIfAbsent(r.config!, () => r);
      }
      if (!mounted) return;
      setState(() {
        _rows = [for (final c in configs) _Row(c, latest[c.name])];
        _error = null;
      });
      _app?.setProjectCount(configs.length);
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    }
  }

  List<_Row> get _visible {
    final all = _rows ?? const <_Row>[];
    final q = _filter.trim().toLowerCase();
    final list = q.isEmpty
        ? all.toList()
        : all.where((r) {
            final c = r.config;
            return c.displayName.toLowerCase().contains(q) ||
                c.aoiName.toLowerCase().contains(q) ||
                c.sourceInstrument.toLowerCase().contains(q) ||
                r.status.contains(q);
          }).toList();
    int cmpNum(double? a, double? b) {
      if (a == null && b == null) return 0;
      if (a == null) return 1; // nulls last, whichever direction
      if (b == null) return -1;
      return _asc ? a.compareTo(b) : b.compareTo(a);
    }

    int cmpStr(String? a, String? b) {
      if (a == null && b == null) return 0;
      if (a == null) return 1;
      if (b == null) return -1;
      return _asc ? a.compareTo(b) : b.compareTo(a);
    }

    list.sort((a, b) {
      switch (_sortCol) {
        case _Col.name:
          return cmpStr(a.config.displayName, b.config.displayName);
        case _Col.status:
          return cmpStr(a.statusWord, b.statusWord);
        case _Col.instrument:
          return cmpStr(a.config.sourceInstrument, b.config.sourceInstrument);
        case _Col.lat:
          return cmpNum(a.config.latMin, b.config.latMin);
        case _Col.lon:
          return cmpNum(a.config.lonMin, b.config.lonMin);
        case _Col.dem:
          return cmpNum(a.config.demEnabled ? 1 : 0, b.config.demEnabled ? 1 : 0);
        case _Col.rmse:
          return cmpNum(a.rmse, b.rmse);
        case _Col.heldout:
          return cmpNum(a.heldout, b.heldout);
        case _Col.when:
          return cmpStr(a.when, b.when);
      }
    });
    return list;
  }

  void _sortBy(_Col c) {
    setState(() {
      if (_sortCol == c) {
        _asc = !_asc;
      } else {
        _sortCol = c;
        _asc = true;
      }
    });
  }

  void _open(_Row row) {
    Navigator.of(context)
        .push(ptRoute((_) => ProjectDetailScreen(api: widget.api, config: row.config), label: row.config.displayName))
        .then((_) => _load());
  }

  Future<void> _newProject() async {
    final created = await Navigator.of(context).push<bool>(ptRoute((_) => NewProjectScreen(api: widget.api), label: 'New project'));
    if (created == true) _load();
  }

  KeyEventResult _onKey(FocusNode node, KeyEvent e) {
    if (e is! KeyDownEvent) return KeyEventResult.ignored;
    final list = _visible;
    if (list.isEmpty) return KeyEventResult.ignored;
    final key = e.logicalKey;
    if (key == LogicalKeyboardKey.arrowDown) {
      setState(() => _selected = ((_selected ?? -1) + 1).clamp(0, list.length - 1));
      _ensureVisible();
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.arrowUp) {
      setState(() => _selected = ((_selected ?? list.length) - 1).clamp(0, list.length - 1));
      _ensureVisible();
      return KeyEventResult.handled;
    }
    if ((key == LogicalKeyboardKey.enter || key == LogicalKeyboardKey.numpadEnter) && _selected != null && _selected! < list.length) {
      _open(list[_selected!]);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  static const double _rowH = 26;

  void _ensureVisible() {
    final i = _selected;
    if (i == null || !_scroll.hasClients) return;
    final top = i * _rowH;
    final bottom = top + _rowH;
    final pos = _scroll.position;
    if (top < pos.pixels) {
      _scroll.animateTo(top, duration: kFast, curve: Curves.easeOut);
    } else if (bottom > pos.pixels + pos.viewportDimension) {
      _scroll.animateTo(bottom - pos.viewportDimension, duration: kFast, curve: Curves.easeOut);
    }
  }

  String _subtitle() {
    final rows = _rows;
    if (rows == null) return 'Loading…';
    final fit = rows.where((r) => r.status == 'done').length;
    final nofit = rows.where((r) => r.status == 'no fit').length;
    final none = rows.where((r) => r.run == null).length;
    return '${rows.length} projects · $fit registered · $nofit with no reliable fit · $none not run yet';
  }

  @override
  Widget build(BuildContext context) {
    final visible = _visible;
    final selectedRow = _selected != null && _selected! < visible.length ? visible[_selected!] : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ScreenHeader(
          title: 'Projects',
          subtitle: _subtitle(),
          actions: [
            SearchBox(hint: 'Filter projects', width: 190, onChanged: (v) => setState(() {
                  _filter = v;
                  _selected = null;
                })),
            PushButton(label: 'New project…', onPressed: _newProject, compact: true),
            PushButton(
              label: 'Open',
              isDefault: true,
              compact: true,
              onPressed: selectedRow == null ? null : () => _open(selectedRow),
            ),
          ],
        ),
        Expanded(
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: _content(visible),
          ),
        ),
      ],
    );
  }

  Widget _content(List<_Row> visible) {
    if (_rows == null) {
      return Center(
        child: _error == null
            ? const Row(mainAxisSize: MainAxisSize.min, children: [Spinner(), SizedBox(width: 10), Text('Loading projects…')])
            : Callout(kind: CalloutKind.error, title: 'Could not load the projects', child: SelectableText(_error!, style: ui(size: 11.5))),
      );
    }
    if (_rows!.isEmpty) {
      return const Center(child: Callout(kind: CalloutKind.info, title: 'No projects yet', child: Note('Choose “New project…” to point the pipeline at a source image and a reference.')));
    }
    return Focus(
      focusNode: _focus,
      autofocus: true,
      onKeyEvent: _onKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: Well(
              child: LayoutBuilder(builder: (context, box) {
                final cols = _columns(box.maxWidth);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _header(cols),
                    Expanded(
                      child: visible.isEmpty
                          ? Center(child: Text('No project matches “$_filter”.', style: ui(color: Pt.ink2)))
                          : Scrollbar(
                              controller: _scroll,
                              child: Padding(
                                padding: const EdgeInsets.only(right: 13),
                                child: ListView.builder(
                                  controller: _scroll,
                                  itemExtent: _rowH,
                                  itemCount: visible.length,
                                  itemBuilder: (context, i) => _ProjectRow(
                                    row: visible[i],
                                    cols: cols,
                                    index: i,
                                    selected: _selected == i,
                                    onTap: () {
                                      _focus.requestFocus();
                                      setState(() => _selected = i);
                                    },
                                    onOpen: () => _open(visible[i]),
                                  ),
                                ),
                              ),
                            ),
                    ),
                  ],
                );
              }),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: Text(
                  'Double-click or press Enter to open a project. Click a column title to sort.',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: captionStyle(),
                ),
              ),
              if (_error != null) Flexible(child: Text(_error!, maxLines: 1, overflow: TextOverflow.ellipsis, style: ui(size: 11, color: Pt.red))),
            ],
          ),
        ],
      ),
    );
  }

  /// Column layout for a given width; the name column takes what is left and
  /// the least important columns drop out first when the window is narrow.
  List<_ColSpec> _columns(double width) {
    final all = <_ColSpec>[
      _ColSpec(_Col.name, 'Name', null),
      _ColSpec(_Col.status, 'Status', 92),
      _ColSpec(_Col.instrument, 'Instrument', 86),
      _ColSpec(_Col.lat, 'Latitude °', 112, align: TextAlign.right),
      _ColSpec(_Col.lon, 'Longitude °', 118, align: TextAlign.right),
      _ColSpec(_Col.dem, 'DEM', 48, align: TextAlign.center),
      _ColSpec(_Col.rmse, 'RMSE', 84, align: TextAlign.right),
      _ColSpec(_Col.heldout, 'Held-out', 84, align: TextAlign.right),
      _ColSpec(_Col.when, 'Last run', 132),
    ];
    // Status LED (30) + name (min 200) are always shown.
    final drop = [_Col.dem, _Col.when, _Col.lon, _Col.lat, _Col.heldout, _Col.status];
    var cols = [...all];
    double need() => 30 + 200 + cols.where((c) => c.width != null).fold<double>(0, (s, c) => s + c.width!);
    for (final d in drop) {
      if (need() <= width) break;
      cols = cols.where((c) => c.col != d).toList();
    }
    return cols;
  }

  Widget _header(List<_ColSpec> cols) {
    Widget cell(_ColSpec c) {
      final active = _sortCol == c.col;
      final content = PtPressable(
        onPressed: () => _sortBy(c.col),
        builder: (context, hover, down, focus) => Container(
          color: down ? const Color(0x18000000) : (hover ? const Color(0x0C000000) : Colors.transparent),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          alignment: c.align == TextAlign.right ? Alignment.centerRight : (c.align == TextAlign.center ? Alignment.center : Alignment.centerLeft),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Flexible(child: Text(c.label, maxLines: 1, overflow: TextOverflow.ellipsis, style: ui(weight: FontWeight.w700, size: 11.5))),
              if (active)
                AnimatedRotation(
                  duration: kMedium,
                  curve: kSpring,
                  turns: _asc ? 0 : 0.5,
                  child: const Icon(Icons.arrow_drop_up, size: 16, color: Pt.ink),
                ),
            ],
          ),
        ),
      );
      final boxed = DecoratedBox(
        decoration: const BoxDecoration(border: Border(right: BorderSide(color: Pt.shade))),
        child: content,
      );
      return c.width != null ? SizedBox(width: c.width, child: boxed) : Expanded(child: boxed);
    }

    return Container(
      height: 24,
      decoration: const BoxDecoration(
        gradient: LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.chromeHi, Pt.chromeLo]),
        border: Border(bottom: BorderSide(color: Pt.edge)),
      ),
      child: Row(
        children: [
          const SizedBox(width: 30, child: DecoratedBox(decoration: BoxDecoration(border: Border(right: BorderSide(color: Pt.shade))), child: SizedBox.expand())),
          for (final c in cols) cell(c),
          const SizedBox(width: 13),
        ],
      ),
    );
  }
}

class _ColSpec {
  final _Col col;
  final String label;
  final double? width;
  final TextAlign align;
  _ColSpec(this.col, this.label, this.width, {this.align = TextAlign.left});
}

class _ProjectRow extends StatefulWidget {
  final _Row row;
  final List<_ColSpec> cols;
  final int index;
  final bool selected;
  final VoidCallback onTap;
  final VoidCallback onOpen;

  const _ProjectRow({
    required this.row,
    required this.cols,
    required this.index,
    required this.selected,
    required this.onTap,
    required this.onOpen,
  });

  @override
  State<_ProjectRow> createState() => _ProjectRowState();
}

class _ProjectRowState extends State<_ProjectRow> {
  bool _hover = false;

  String _metres(double? v) => v == null ? '—' : '${v.toStringAsFixed(v >= 10 ? 1 : 2)} m';

  String _when(String? iso) {
    if (iso == null) return '—';
    try {
      return DateFormat('yyyy-MM-dd HH:mm').format(DateTime.parse(iso).toLocal());
    } catch (_) {
      return iso;
    }
  }

  String _range(double a, double b) => '${a.toStringAsFixed(1)} … ${b.toStringAsFixed(1)}';

  @override
  Widget build(BuildContext context) {
    final r = widget.row;
    final c = r.config;
    final sel = widget.selected;
    final bg = sel ? null : (_hover ? Pt.accentWash.withValues(alpha: 0.55) : (widget.index.isOdd ? Pt.stripe : Pt.paper));
    final fg = sel ? Colors.white : Pt.ink;
    final dim = sel ? Colors.white.withValues(alpha: 0.85) : Pt.ink2;

    Widget wrap(_ColSpec col, Widget child) {
      final aligned = Container(
        alignment: col.align == TextAlign.right ? Alignment.centerRight : (col.align == TextAlign.center ? Alignment.center : Alignment.centerLeft),
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: child,
      );
      return col.width != null ? SizedBox(width: col.width, child: aligned) : Expanded(child: aligned);
    }

    Text mono11(String s, {Color? color}) => Text(s, maxLines: 1, overflow: TextOverflow.ellipsis, style: mono(size: 11.5, color: color ?? fg));

    Widget cellFor(_ColSpec col) {
      switch (col.col) {
        case _Col.name:
          return wrap(
            col,
            Row(
              children: [
                Icon(CupertinoIcons.photo_on_rectangle, size: 14, color: dim),
                const SizedBox(width: 7),
                Flexible(child: Text(c.displayName, maxLines: 1, overflow: TextOverflow.ellipsis, style: ui(weight: FontWeight.w700, color: fg))),
              ],
            ),
          );
        case _Col.status:
          final tone = switch (r.status) {
            'done' => Pt.green,
            'no fit' => Pt.amber,
            'error' => Pt.red,
            _ => Pt.ink2,
          };
          return wrap(
            col,
            Text(r.statusWord, maxLines: 1, overflow: TextOverflow.ellipsis, style: ui(size: 11.5, color: sel ? Colors.white : tone, weight: r.status == 'none' ? FontWeight.w400 : FontWeight.w700)),
          );
        case _Col.instrument:
          return wrap(col, Text(c.sourceInstrument, style: ui(color: fg)));
        case _Col.lat:
          return wrap(col, mono11(_range(c.latMin, c.latMax)));
        case _Col.lon:
          return wrap(col, mono11(_range(c.lonMin, c.lonMax)));
        case _Col.dem:
          return wrap(col, Icon(c.demEnabled ? Icons.check : Icons.remove, size: 14, color: sel ? Colors.white : (c.demEnabled ? Pt.green : Pt.ink3)));
        case _Col.rmse:
          return wrap(col, mono11(_metres(r.rmse), color: r.rmse == null ? dim : fg));
        case _Col.heldout:
          return wrap(col, mono11(_metres(r.heldout), color: r.heldout == null ? dim : fg));
        case _Col.when:
          return wrap(col, mono11(_when(r.when), color: dim));
      }
    }

    return MouseRegion(
      onEnter: (_) => setState(() => _hover = true),
      onExit: (_) => setState(() => _hover = false),
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        // Select on press, not on release: with a double-tap recognizer present
        // a plain onTap would wait ~300 ms before firing.
        onTapDown: (_) => widget.onTap(),
        onDoubleTap: widget.onOpen,
        child: AnimatedContainer(
          duration: kFast,
          decoration: BoxDecoration(
            color: bg,
            gradient: sel ? const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.accentHi, Pt.accent]) : null,
            border: const Border(bottom: BorderSide(color: Color(0xFFE9E7E1))),
          ),
          child: Row(
            children: [
              SizedBox(width: 30, child: Center(child: StatusBadge(status: r.status, showText: false))),
              for (final col in widget.cols) cellFor(col),
            ],
          ),
        ),
      ),
    );
  }
}
