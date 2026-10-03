import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;

import '../models/benchmark_summary.dart';
import '../models/config_details.dart';
import '../models/config_summary.dart';
import '../models/run_summary.dart';
import '../models/viz_manifest.dart';

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

/// Thin client for the local FastAPI server (algo.api.server). The server
/// runs inside the pipeline's own venv and is expected on localhost — this
/// app never talks to anything else.
class ApiClient {
  final String baseUrl;
  final http.Client _http;

  ApiClient({this.baseUrl = 'http://127.0.0.1:8000', http.Client? client})
      : _http = client ?? http.Client();

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<bool> health() async {
    try {
      final res = await _http.get(_uri('/health')).timeout(const Duration(seconds: 3));
      return res.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<List<ConfigSummary>> listConfigs() async {
    final res = await _http.get(_uri('/configs'));
    _check(res);
    final data = jsonDecode(res.body) as List;
    return data.map((e) => ConfigSummary.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<RunSummary>> listRuns({int limit = 50, String? config}) async {
    final res = await _http.get(_uri('/runs').replace(queryParameters: {'limit': '$limit', if (config != null) 'config': config}));
    _check(res);
    final data = _decode(res) as List;
    return data.map((e) => RunSummary.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<RunSummary> getRun(String runId) async {
    final res = await _http.get(_uri('/runs/$runId'));
    _check(res);
    return RunSummary.fromJson(_decode(res) as Map<String, dynamic>);
  }

  Future<String> createConfig({
    required String name,
    required String aoiName,
    required double latMin,
    required double latMax,
    required double lonMin,
    required double lonMax,
    required String sourceInstrument,
    required String sourcePath,
    required String referencePath,
    required bool demEnabled,
    String? demPath,
  }) async {
    final res = await _http.post(
      _uri('/configs'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'name': name,
        'aoi_name': aoiName,
        'lat_min': latMin,
        'lat_max': latMax,
        'lon_min': lonMin,
        'lon_max': lonMax,
        'source_instrument': sourceInstrument,
        'source_path': sourcePath,
        'reference_path': referencePath,
        'dem_enabled': demEnabled,
        if (demPath != null && demPath.isNotEmpty) 'dem_path': demPath,
      }),
    );
    _check(res);
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return data['name'] as String;
  }

  Future<String> startRun(String configName) async {
    final res = await _http.post(
      _uri('/runs'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'config': configName}),
    );
    _check(res);
    final data = jsonDecode(res.body) as Map<String, dynamic>;
    return data['run_id'] as String;
  }

  /// Sanity checks + image list for a finished run. The first request for a
  /// run renders everything from the full-resolution imagery (several
  /// seconds); after that it is served from the run's cache.
  Future<VizManifest> getVisualizations(String runId) async {
    final res = await _http.get(_uri('/runs/$runId/viz'));
    _check(res);
    return VizManifest.fromJson(_decode(res) as Map<String, dynamic>);
  }

  /// Direct URL for one rendered image of a run, for an `Image.network` widget.
  /// Opens the run's output folder in Explorer and returns its path.
  Future<String> openRunFolder(String runId) async {
    final res = await _http.post(_uri('/runs/$runId/open-folder'));
    _check(res);
    return (_decode(res) as Map)['path'] as String;
  }

  /// Streams the run's registered GeoTIFF to [destPath] (it can be hundreds of MB).
  Future<void> saveRegistered(String runId, String destPath) async {
    final res = await _http.send(http.Request('GET', _uri('/runs/$runId/registered.tif')));
    if (res.statusCode >= 400) {
      throw ApiException('${res.statusCode}: ${await res.stream.bytesToString()}');
    }
    final sink = File(destPath).openWrite();
    try {
      await res.stream.pipe(sink);
    } finally {
      await sink.close();
    }
  }

  String vizImageUrl(String runId, String name) => '$baseUrl/runs/$runId/viz/$name.png';

  /// Lat/lon bounds (min lat, max lat, min lon, max lon) of a source product.
  Future<List<double>> getFootprint(String sourcePath) async {
    final res = await _http.get(_uri('/footprint').replace(queryParameters: {'path': sourcePath}));
    _check(res);
    final j = _decode(res) as Map<String, dynamic>;
    return [for (final k in ['lat_min', 'lat_max', 'lon_min', 'lon_max']) (j[k] as num).toDouble()];
  }

  Future<ConfigDetails> getConfigDetails(String configName) async {
    final res = await _http.get(_uri('/configs/$configName/details'));
    _check(res);
    return ConfigDetails.fromJson(_decode(res) as Map<String, dynamic>);
  }

  /// The synthetic ground-truth benchmark, or null when the server has none
  /// yet (404 — it is produced offline by the algo benchmark scripts, not by
  /// a run). Any other failure throws.
  Future<BenchmarkSummary?> getBenchmarks() async {
    final res = await _http.get(_uri('/benchmarks'));
    if (res.statusCode == 404) return null;
    _check(res);
    return BenchmarkSummary.fromJson(_decode(res) as Map<String, dynamic>);
  }

  /// Direct URL for a project's source/reference quick-look, cropped to its
  /// AOI — generated and cached on first request, independent of any run.
  String previewUrl(String configName) => '$baseUrl/configs/$configName/preview.png';

  /// Parses a JSON body as UTF-8 regardless of the Content-Type charset (the
  /// server sends none, and metrics/benchmark text contains degree signs).
  Object? _decode(http.Response res) => jsonDecode(utf8.decode(res.bodyBytes, allowMalformed: true));

  void _check(http.Response res) {
    if (res.statusCode >= 400) {
      String detail = res.body;
      try {
        final parsed = jsonDecode(res.body);
        if (parsed is Map && parsed['detail'] != null) detail = parsed['detail'].toString();
      } catch (_) {}
      throw ApiException('${res.statusCode}: $detail');
    }
  }
}
