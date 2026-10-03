import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:lunar_registration_desktop/screens/about_screen.dart';
import 'package:lunar_registration_desktop/screens/app_shell.dart';
import 'package:lunar_registration_desktop/screens/new_project_screen.dart';
import 'package:lunar_registration_desktop/screens/results_screen.dart';
import 'package:lunar_registration_desktop/services/api_client.dart';
import 'package:lunar_registration_desktop/theme/platinum.dart';
import 'package:lunar_registration_desktop/ui/controls.dart';
import 'package:lunar_registration_desktop/ui/moon.dart';
import 'package:lunar_registration_desktop/ui/panels.dart';

http.Response _json(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> _config(String name, String aoi, String instrument, double lat) => {
      'name': name,
      'aoi_name': aoi,
      'lat_min': lat,
      'lat_max': lat + 1,
      'lon_min': 10.0,
      'lon_max': 11.0,
      'source_instrument': instrument,
      'source_path': '../data/src/$name',
      'reference_path': '../data/ref/$name.tif',
      'dem_enabled': instrument == 'OHRC',
    };

Map<String, dynamic> _run(String id, String config, {Map<String, dynamic>? metrics}) => {
      'run_id': id,
      'status': 'done',
      'config': config,
      'started_at': '2026-10-02T18:00:00+00:00',
      'finished_at': '2026-10-02T18:05:00+00:00',
      'metrics': metrics,
    };

const _good = <String, dynamic>{
  'rmse': 0.9,
  'rmse_m': 3.97,
  'inlier_count': 50,
  'inlier_ratio': 0.8,
  'match_count': 60,
  'heldout_rmse_m': 5.5,
};
const _noFit = <String, dynamic>{
  'inlier_count': 0,
  'inlier_ratio': 0.0,
  'match_count': 0,
  'failure': 'source has no usable contrast',
};

ApiClient _api() => ApiClient(client: MockClient((req) async {
      switch (req.url.path) {
        case '/health':
          return _json({'ok': true});
        case '/configs':
          return _json([
            _config('alpha.yaml', 'alpha_crater', 'OHRC', 10),
            _config('beta.yaml', 'beta_plain', 'TMC2', 20),
            _config('gamma.yaml', 'gamma_ridge', 'IIRS', 30),
          ]);
        case '/runs':
          return _json([
            _run('r_beta', 'beta.yaml', metrics: _noFit),
            _run('r_alpha', 'alpha.yaml', metrics: _good),
          ]);
        case '/benchmarks':
          return _json({'detail': 'none'}, 404);
        default:
          if (req.url.path.endsWith('/details')) return _json({'source': {'gsd': 0.25}, 'reference': {'gsd': 5.0}});
          return _json({'detail': 'not found'}, 404);
      }
    }));

Future<void> _settle(WidgetTester tester, {int frames = 8}) async {
  // Looping animations (barber pole, pulsing default button) never settle, so
  // pump a fixed number of frames instead of pumpAndSettle.
  for (var i = 0; i < frames; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

void _surface(WidgetTester tester, {double width = 1400, double height = 900}) {
  tester.view.physicalSize = Size(width, height);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

Widget _wrap(Widget child) => MaterialApp(theme: buildPlatinumTheme(), home: Scaffold(body: child));

void main() {
  group('app shell', () {
    testWidgets('lists projects with their latest result, filters and sorts', (tester) async {
      _surface(tester);
      await tester.pumpWidget(MaterialApp(theme: buildPlatinumTheme(), home: AppShell(api: _api())));
      await _settle(tester);

      expect(tester.takeException(), isNull);
      // Menu bar, sidebar and the list.
      expect(find.text('File'), findsOneWidget);
      expect(find.text('Benchmark'), findsWidgets);
      expect(find.text('ALPHA CRATER'), findsOneWidget);
      expect(find.text('BETA PLAIN'), findsOneWidget);
      expect(find.text('GAMMA RIDGE'), findsOneWidget);
      expect(find.text('3.97 m'), findsOneWidget); // alpha's RMSE
      expect(find.text('5.50 m'), findsOneWidget); // alpha's held-out error
      expect(find.text('no fit'), findsOneWidget); // beta
      expect(find.text('registered'), findsOneWidget); // alpha
      expect(find.text('not run'), findsOneWidget); // gamma
      expect(find.textContaining('3 projects'), findsOneWidget);

      // Filter by typing.
      await tester.enterText(find.byType(TextField).first, 'beta');
      await _settle(tester, frames: 2);
      expect(find.text('ALPHA CRATER'), findsNothing);
      expect(find.text('BETA PLAIN'), findsOneWidget);
      await tester.enterText(find.byType(TextField).first, '');
      await _settle(tester, frames: 2);

      // Sort by name descending: gamma first.
      await tester.tap(find.text('Name'));
      await _settle(tester, frames: 2);
      final first = tester.getTopLeft(find.text('GAMMA RIDGE')).dy;
      final last = tester.getTopLeft(find.text('ALPHA CRATER')).dy;
      expect(first, lessThan(last));

      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('opens a project inside the shell and goes back; sidebar switches sections', (tester) async {
      _surface(tester);
      await tester.pumpWidget(MaterialApp(theme: buildPlatinumTheme(), home: AppShell(api: _api())));
      await _settle(tester);

      await tester.tap(find.text('ALPHA CRATER'));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text('Open'));
      await _settle(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('Images'), findsOneWidget);
      expect(find.text('Last run'), findsOneWidget);
      expect(find.text('AOI'), findsOneWidget);
      // The sidebar is still there (nested navigator) and the breadcrumb shows the path.
      expect(find.text('Workspace'), findsOneWidget);
      expect(find.text('Projects'), findsWidgets);

      await tester.tap(find.text('Back'));
      await _settle(tester);
      expect(find.text('Images'), findsNothing);
      expect(find.text('ALPHA CRATER'), findsOneWidget);

      await tester.tap(find.text('Benchmark').first);
      await _settle(tester);
      expect(find.text('No benchmark yet'), findsOneWidget);

      await tester.tap(find.text('About').first);
      await _settle(tester);

      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('keeps working in a narrow window', (tester) async {
      _surface(tester, width: 700, height: 700);
      await tester.pumpWidget(MaterialApp(theme: buildPlatinumTheme(), home: AppShell(api: _api())));
      await _settle(tester);
      expect(tester.takeException(), isNull);
      await tester.tap(find.text('BETA PLAIN'));
      await tester.pump(const Duration(milliseconds: 400));
      await tester.tap(find.text('Open'));
      await _settle(tester);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });

  group('screens', () {
    testWidgets('new project form validates and shows the DEM field only when enabled', (tester) async {
      _surface(tester, width: 1100, height: 1400);
      await tester.pumpWidget(_wrap(NewProjectScreen(api: _api())));
      await _settle(tester);
      expect(tester.takeException(), isNull);

      expect(find.text('Project'), findsOneWidget);
      expect(find.text('Area of interest (degrees)'), findsOneWidget);
      expect(find.text('DEM'), findsNothing);

      await tester.tap(find.text('Create project'));
      await _settle(tester, frames: 2);
      expect(find.text('Required'), findsWidgets);

      await tester.tap(find.text('Use a DEM'));
      await _settle(tester, frames: 3);
      expect(find.text('DEM'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('about screen lists the shortcuts', (tester) async {
      _surface(tester);
      await tester.pumpWidget(_wrap(const AboutScreen()));
      await _settle(tester, frames: 3);
      expect(tester.takeException(), isNull);
      expect(find.text('Supported conditions'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });

  group('results', () {
    testWidgets('a run opened while running updates itself when it finishes', (tester) async {
      _surface(tester);
      var calls = 0;
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs/r1') {
          calls++;
          final running = calls < 3;
          return _json({
            'run_id': 'r1',
            'status': running ? 'running' : 'done',
            'config': 'alpha.yaml',
            'started_at': '2026-10-02T18:00:00+00:00',
            'finished_at': running ? null : '2026-10-02T18:00:03+00:00',
            'stage': running ? 'Matching' : null,
            'metrics': running ? null : _noFit,
          });
        }
        return _json({'detail': 'not found'}, 404);
      }));
      await tester.pumpWidget(_wrap(ResultsScreen(runId: 'r1', api: api)));
      await tester.pump(const Duration(milliseconds: 200));
      await tester.pump(const Duration(milliseconds: 200));
      expect(find.textContaining('Matching'), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(seconds: 2));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.textContaining('Matching'), findsNothing);
      expect(calls, greaterThanOrEqualTo(3));
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });

  group('design system', () {
    testWidgets('segmented control reports the tapped segment', (tester) async {
      String value = 'a';
      await tester.pumpWidget(_wrap(StatefulBuilder(
        builder: (context, set) => Center(
          child: SegmentedControl<String>(
            options: const [SegmentOption('a', 'One'), SegmentOption('b', 'Two')],
            value: value,
            onChanged: (v) => set(() => value = v),
          ),
        ),
      )));
      await tester.tap(find.text('Two'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(value, 'b');
    });

    testWidgets('push button: default pulses, disabled does not fire', (tester) async {
      var taps = 0;
      await tester.pumpWidget(_wrap(Column(
        children: [
          PushButton(label: 'Go', isDefault: true, onPressed: () => taps++),
          const PushButton(label: 'Nope', onPressed: null),
        ],
      )));
      await tester.pump(const Duration(milliseconds: 600));
      await tester.tap(find.text('Go'));
      await tester.tap(find.text('Nope'));
      expect(taps, 1);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('collapsible panel hides and shows its body', (tester) async {
      await tester.pumpWidget(_wrap(const Panel(title: 'Box', collapsible: true, child: Text('inside'))));
      expect(find.text('inside'), findsOneWidget);
      await tester.tap(find.text('Box'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('inside'), findsNothing);
      await tester.tap(find.text('Box'));
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('inside'), findsOneWidget);
    });

    testWidgets('property table, grid table, LCD readout and masonry lay out', (tester) async {
      _surface(tester, width: 900, height: 700);
      await tester.pumpWidget(_wrap(SingleChildScrollView(
        child: Column(
          children: [
            const PropertyTable(rows: [Prop('Label', 'value one'), Prop('Other', 'two', note: 'explained')]),
            const GridTable(
              columns: [GridColumn('A'), GridColumn('B', width: 60, align: TextAlign.right)],
              rows: [
                ['x', '1'],
                ['y', '2'],
              ],
            ),
            const SizedBox(width: 300, child: LcdReadout(label: 'RMSE', value: '4.79', unit: 'm')),
            Masonry(
              columns: 2,
              weights: const [1, 1, 1],
              children: const [Text('m1'), Text('m2'), Text('m3')],
            ),
          ],
        ),
      )));
      await tester.pump(const Duration(seconds: 1));
      expect(tester.takeException(), isNull);
      expect(find.text('explained'), findsOneWidget);
      expect(find.text('4.79'), findsOneWidget); // the count-up has finished
      expect(find.text('m3'), findsOneWidget);
    });

    testWidgets('moon icon and barber pole paint', (tester) async {
      await tester.pumpWidget(_wrap(const Column(children: [MoonIcon(size: 64), AnimatedMoon(size: 64), BarberPole()])));
      await tester.pump(const Duration(milliseconds: 500));
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    test('spring curve starts at 0, ends at 1 and overshoots a little', () {
      const c = SpringCurve();
      expect(c.transform(0), 0);
      expect(c.transform(1), 1);
      final peak = [for (var i = 1; i < 100; i++) c.transform(i / 100)].reduce((a, b) => a > b ? a : b);
      expect(peak, greaterThan(1.0));
      expect(peak, lessThan(1.15));
    });
  });
}
