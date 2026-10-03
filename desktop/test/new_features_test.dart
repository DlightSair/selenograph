import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:lunar_registration_desktop/models/benchmark_summary.dart';
import 'package:lunar_registration_desktop/models/config_details.dart';
import 'package:lunar_registration_desktop/models/config_summary.dart';
import 'package:lunar_registration_desktop/models/run_summary.dart';
import 'package:lunar_registration_desktop/screens/benchmark_screen.dart';
import 'package:lunar_registration_desktop/screens/project_detail_screen.dart';
import 'package:lunar_registration_desktop/screens/results_screen.dart';
import 'package:lunar_registration_desktop/services/api_client.dart';
import 'package:lunar_registration_desktop/theme/platinum.dart';

// Trimmed copies of what the server really returns (metrics.json of a good run
// with an adopted non-rigid field + parallax, and of a run with no reliable fit).
const _goodMetrics = <String, dynamic>{
  'rmse': 0.949,
  'rmse_m': 3.97,
  'inlier_count': 516,
  'inlier_ratio': 0.778,
  'uniformity_cov': 1.08,
  'match_count': 663,
  'reference_gsd_m': 4.18,
  'source_gsd_m': 0.25,
  'source_decimation': 8.0,
  'stages': [
    {'down': 2.0, 'source_down': 31.86, 'tile': 128, 'attempted': 99, 'matched': 75, 'agreeing_tiles': 37},
    {'down': 1.0, 'source_down': 16.0, 'tile': 128, 'bar': 0.109, 'attempted': 899, 'matched': 663, 'fit_inliers': 637},
  ],
  'structure': 'intensity',
  'capture_candidates': {
    'intensity': {'tiles': 75, 'attempted': 99, 'agree': 37, 'median_ncc': 0.182},
    'edges': {'tiles': 96, 'attempted': 99, 'agree': 24, 'median_ncc': 0.189},
    'cfog': {'tiles': 1, 'attempted': 99, 'agree': 0, 'median_ncc': 640.8},
  },
  'relit_layer': true,
  'dem_available': true,
  'nonrigid': {
    'cv_rmse_homography_px': 2.77,
    'cv_rmse_nonrigid_px': 2.21,
    'nonrigid': 'adopted',
    'field_rms_px': 2.43,
    'field_max_px': 6.3,
    'cv_gain_pct': 20.3,
    'parallax': {
      'alpha_along': -0.0086,
      'alpha_cross': -0.0037,
      'explained_variance': 0.305,
      'dem_relief_m': 2540.1,
      'expected_abs_alpha_along': 0.2478,
      'expected_abs_alpha_cross': 0.0336,
    },
  },
  'rescue': {'rotation_deg': 12.5, 'scale': 1.1, 'hypotheses_tried': 40},
  'heldout_rmse_px': 2.21,
  'heldout_rmse_m': 9.24,
  'nonrigid_field_rms_m': 10.19,
};

const _failedMetrics = <String, dynamic>{
  'rmse': null,
  'inlier_count': 0,
  'inlier_ratio': 0.0,
  'uniformity_cov': null,
  'match_count': 0,
  'stages': [
    {'down': 2.0, 'source_down': 31.86, 'tile': 128, 'attempted': 99, 'matched': 75, 'agreeing_tiles': 22},
  ],
  'nonrigid': null,
  'failure': 'source has no usable contrast (mean DN 1.0): the strip is in shadow or unlit',
};

const _benchmarkJson = <String, dynamic>{
  'generated': '2026-10-02T18:54:29+00:00',
  'success_px': 1.5,
  'variant_notes': {
    'baseline': 'intensity correlation, homography only',
    'auto': 'representation chosen per scene',
    'relit': 'auto + DEM re-lit with the source’s Sun',
  },
  'suites': [
    {'name': 'illumination', 'title': 'Illumination variation', 'variants': ['baseline', 'auto', 'relit'], 'groups': []},
  ],
  'panels': [
    {
      'suite': 'illumination',
      'title': 'Sun azimuth difference (elevation 25° both)',
      'x_label': 'Sun azimuth difference (°)',
      'variants': ['baseline', 'auto', 'relit'],
      'points': [
        {
          'x': 0.0,
          'label': 'az0',
          'variants': {
            'baseline': {'n': 3, 'success': 1.0, 'median_rmse_px': 0.0222, 'median_rmse_m': 0.11, 'p90_rmse_px': 0.02, 'median_prior_rmse_px': 60.3},
            'auto': {'n': 3, 'success': 1.0, 'median_rmse_px': 0.0222, 'median_rmse_m': 0.11, 'p90_rmse_px': 0.02, 'median_prior_rmse_px': 60.3},
            'relit': {'n': 3, 'success': 1.0, 'median_rmse_px': 0.0761, 'median_rmse_m': 0.38, 'p90_rmse_px': 0.09, 'median_prior_rmse_px': 60.3},
          },
        },
        {
          'x': 90.0,
          'label': 'az90',
          'variants': {
            'baseline': {'n': 3, 'success': 0.0, 'median_rmse_px': 4.05, 'median_rmse_m': 20.2, 'p90_rmse_px': 4.4, 'median_prior_rmse_px': 60.3},
            'auto': {'n': 3, 'success': 0.3333, 'median_rmse_px': 4.05, 'median_rmse_m': 20.2, 'p90_rmse_px': 4.4, 'median_prior_rmse_px': 60.3},
            'relit': {'n': 3, 'success': 0.0, 'median_rmse_px': null, 'median_rmse_m': null, 'p90_rmse_px': null, 'median_prior_rmse_px': 60.3},
          },
        },
        {
          'x': 180.0,
          'label': 'az180',
          'variants': {
            'baseline': {'n': 3, 'success': 0.0, 'median_rmse_px': 6.11, 'median_rmse_m': 30.5, 'p90_rmse_px': 6.6, 'median_prior_rmse_px': 60.3},
            'auto': {'n': 3, 'success': 1.0, 'median_rmse_px': 0.265, 'median_rmse_m': 1.3, 'p90_rmse_px': 0.27, 'median_prior_rmse_px': 60.3},
            'relit': {'n': 3, 'success': 0.6667, 'median_rmse_px': 0.216, 'median_rmse_m': 1.08, 'p90_rmse_px': 1.57, 'median_prior_rmse_px': 60.3},
          },
        },
      ],
    },
  ],
};

Map<String, dynamic> _runJson(String id, Map<String, dynamic> metrics, {bool withTransform = true}) => {
      'run_id': id,
      'status': 'done',
      'config': 'demo.yaml',
      'started_at': '2026-10-02T18:00:00+00:00',
      'finished_at': '2026-10-02T18:05:00+00:00',
      'metrics': metrics,
      'transform': withTransform
          ? {
              'homography': [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
              ],
            }
          : null,
    };

http.Response _json(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)),
      status,
      headers: {'content-type': 'application/json'},
    );

Future<void> _settle(WidgetTester tester) async {
  // FadeSlideIn uses delayed futures and the chart sweeps in; pump past both
  // without pumpAndSettle (spinners would never settle).
  for (var i = 0; i < 8; i++) {
    await tester.pump(const Duration(milliseconds: 250));
  }
}

Widget _app(Widget home) => MaterialApp(theme: buildPlatinumTheme(), home: Scaffold(body: home));

void _bigSurface(WidgetTester tester, {double width = 1400, double height = 1000}) {
  tester.view.physicalSize = Size(width, height);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

void main() {
  group('model parsing', () {
    test('RunMetrics reads every new key', () {
      final m = RunMetrics.fromJson(_goodMetrics);
      expect(m.failed, isFalse);
      expect(m.heldoutRmseM, 9.24);
      expect(m.structure, 'intensity');
      expect(m.captureCandidates['intensity']!.agree, 37);
      expect(m.relitLayer, isTrue);
      expect(m.nonrigid!.adopted, isTrue);
      expect(m.nonrigid!.parallax!.expectedAbsAlphaAlong, 0.2478);
      expect(m.stages, hasLength(2));
      expect(m.stages.first.inliers, 37); // capture stage: agreeing tiles
      expect(m.stages.last.inliers, 637); // fit inliers
      expect(m.rescue!.hypothesesTried, 40);
      expect(m.scaleRatio, closeTo(0.25 / 4.18, 1e-9));
    });

    test('RunMetrics for a failed run and for legacy / empty maps never throws', () {
      final failed = RunMetrics.fromJson(_failedMetrics);
      expect(failed.failed, isTrue);
      expect(failed.rmse, isNull);
      expect(failed.inlierCount, 0);

      final legacy = RunMetrics.fromJson({'rmse': 1.0, 'inlier_count': 3, 'inlier_ratio': 0.5, 'match_count': 6});
      expect(legacy.failed, isFalse);
      expect(legacy.stages, isEmpty);
      expect(legacy.nonrigid, isNull);

      final empty = RunMetrics.fromJson({});
      expect(empty.inlierCount, 0);
      expect(empty.matchCount, 0);
      // Wrong types are ignored rather than thrown on.
      RunMetrics.fromJson({'stages': 'x', 'nonrigid': 5, 'capture_candidates': [], 'rescue': 'y', 'rmse': 'z'});
    });

    test('RunSummary: no-fit status', () {
      final r = RunSummary.fromJson(_runJson('r', _failedMetrics, withTransform: false));
      expect(r.isNoFit, isTrue);
      expect(r.displayStatus, 'no fit');
      expect(RunSummary.fromJson(_runJson('r', _goodMetrics)).displayStatus, 'done');
    });

    test('ConfigDetails tolerates old and new payloads', () {
      final old = ConfigDetails.fromJson({
        'source': {'gsd': 3.8},
        'reference': {'gsd': 5.0},
      });
      expect(old.registration, isNull);
      expect(old.cameraLabel, isNull);

      final d = ConfigDetails.fromJson({
        'source': {'camera': 'f', 'roll': 1.5, 'pitch': null, 'altitude_km': 100.2, 'instrument': 'TMC2'},
        'reference': {'provider': 'lroc', 'layer': 'wac'},
        'registration': {'mode': 'prior_guided', 'relit': true, 'dem': false, 'nonrigid': true},
      });
      expect(d.cameraLabel, contains('Forward'));
      expect(d.registration!.relit, isTrue);
      expect(d.registration!.dem, isFalse);
      expect(d.sourcePitch, isNull);
    });

    test('BenchmarkSummary parses panels, nulls and variant order', () {
      final b = BenchmarkSummary.fromJson(_benchmarkJson);
      expect(b.panels, hasLength(1));
      expect(b.variants, ['baseline', 'auto', 'relit']);
      expect(b.suiteTitle('illumination'), 'Illumination variation');
      expect(b.panels.first.points[1].variants['relit']!.medianRmsePx, isNull);
      expect(b.successPx, 1.5);
    });
  });

  group('widgets render without layout errors', () {
    testWidgets('results screen: good run shows the new readouts and how it was matched', (tester) async {
      _bigSurface(tester);
      var vizRequests = 0;
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs/r1') return _json(_runJson('r1', _goodMetrics));
        if (req.url.path.endsWith('/viz')) {
          vizRequests++;
          return _json({'detail': 'nope'}, 500);
        }
        return _json({'detail': 'not found'}, 404);
      }));
      await tester.pumpWidget(_app(ResultsScreen(runId: 'r1', api: api)));
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(find.text('Held-out error'), findsOneWidget);
      expect(find.text('Non-rigid'), findsOneWidget);
      expect(find.text('Matched on'), findsOneWidget);
      expect(find.textContaining('against reference'), findsOneWidget);
      expect(find.text('Matching stages'), findsOneWidget);
      expect(find.text('Representation vote'), findsOneWidget);
      expect(find.text('Terrain parallax model'), findsOneWidget);
      expect(find.text('chosen'), findsOneWidget);
      expect(vizRequests, 1);

      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('results screen: no-fit run shows the panel and never asks for visualizations', (tester) async {
      _bigSurface(tester);
      var vizRequests = 0;
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs/r2') return _json(_runJson('r2', _failedMetrics, withTransform: false));
        if (req.url.path.endsWith('/viz')) vizRequests++;
        return _json({'detail': 'not found'}, 404);
      }));
      await tester.pumpWidget(_app(ResultsScreen(runId: 'r2', api: api)));
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(find.text('No reliable fit'), findsOneWidget);
      expect(find.textContaining('in shadow or unlit'), findsWidgets);
      expect(find.text('RMSE'), findsNothing);
      expect(vizRequests, 0);

      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('results screen offers the output folder and GeoTIFF save', (tester) async {
      _bigSurface(tester);
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs/r1') return _json(_runJson('r1', _goodMetrics));
        return _json({'detail': 'x'}, 500);
      }));
      await tester.pumpWidget(_app(ResultsScreen(runId: 'r1', api: api)));
      await _settle(tester);
      expect(find.text('Open folder'), findsOneWidget);
      expect(find.text('Save GeoTIFF…'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('results screen fits a narrow window', (tester) async {
      _bigSurface(tester, width: 520, height: 900);
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs/r1') return _json(_runJson('r1', _goodMetrics));
        return _json({'detail': 'x'}, 500);
      }));
      await tester.pumpWidget(_app(ResultsScreen(runId: 'r1', api: api)));
      await _settle(tester);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('project detail: viewing geometry, illumination note and option chips', (tester) async {
      _bigSurface(tester);
      final api = ApiClient(client: MockClient((req) async {
        if (req.url.path == '/runs') return _json([_runJson('r1', _goodMetrics)..['config'] = 'demo.yaml']);
        if (req.url.path == '/configs/demo.yaml/details') {
          return _json({
            'source': {
              'instrument': 'OHRC',
              'gsd': 0.25,
              'sun_elevation': 3.2,
              'sun_azimuth': 101.0,
              'lines': 1000,
              'samples': 500,
              'roll': -2.5,
              'pitch': 0.4,
              'yaw': 0.0,
              'altitude_km': 98.7,
              'camera': 'n',
            },
            'reference': {'gsd': 5.0, 'rows': 10, 'cols': 10, 'provider': 'lroc', 'layer': 'wac'},
            'registration': {'mode': 'prior_guided', 'relit': true, 'dem': true, 'nonrigid': false},
          });
        }
        return _json({'detail': 'x'}, 404);
      }));
      final config = ConfigSummary(
        name: 'demo.yaml',
        aoiName: 'demo_aoi',
        latMin: 10,
        latMax: 11,
        lonMin: 20,
        lonMax: 21,
        sourceInstrument: 'OHRC',
        sourcePath: 'a',
        referencePath: 'b',
        demEnabled: true,
      );
      await tester.pumpWidget(_app(ProjectDetailScreen(api: api, config: config)));
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(find.text('Geometry'), findsOneWidget);
      expect(find.text('Illumination'), findsOneWidget);
      expect(find.textContaining('Sun elevation below 5'), findsOneWidget);
      expect(find.text('Relit DEM'), findsOneWidget);
      expect(find.text('Parallax'), findsOneWidget);
      expect(find.text('Nonrigid'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink()); // cancels the polling timer
    });

    testWidgets('benchmark screen: charts, toggle, and no-benchmark empty state', (tester) async {
      _bigSurface(tester);
      final api = ApiClient(client: MockClient((req) async => _json(_benchmarkJson)));
      await tester.pumpWidget(_app(BenchmarkScreen(api: api)));
      await _settle(tester);

      expect(tester.takeException(), isNull);
      expect(find.text('What this measures'), findsOneWidget);
      expect(find.textContaining('Sun azimuth difference'), findsWidgets);
      expect(find.text('100% · 0.02 px'), findsWidgets);
      expect(find.text('0% · —'), findsOneWidget); // every case failed

      // Hide a variant: its table column goes away.
      await tester.tap(find.text('relit').first);
      await _settle(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('0% · —'), findsNothing);

      await tester.pumpWidget(const SizedBox.shrink());

      final empty = ApiClient(client: MockClient((req) async => _json({'detail': 'no benchmark'}, 404)));
      await tester.pumpWidget(_app(BenchmarkScreen(api: empty)));
      await _settle(tester);
      expect(tester.takeException(), isNull);
      expect(find.text('No benchmark yet'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  });
}
