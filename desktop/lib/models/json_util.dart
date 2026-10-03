// Tolerant JSON readers for the models that mirror server files which grow new
// optional keys over time (metrics.json, /configs/{name}/details, the
// benchmark summary). Each returns null on a missing key or a wrong type
// instead of throwing, so an older or newer server never breaks the UI.

double? asDouble(Object? v) {
  if (v is num && v.isFinite) return v.toDouble();
  return null;
}

int? asInt(Object? v) => v is num && v.isFinite ? v.toInt() : null;

String? asString(Object? v) => v is String ? v : null;

bool? asBool(Object? v) => v is bool ? v : null;

Map<String, dynamic>? asMap(Object? v) => v is Map ? Map<String, dynamic>.from(v) : null;

/// The list's elements that are JSON objects; anything else is skipped.
List<Map<String, dynamic>> asMapList(Object? v) =>
    v is List ? [for (final e in v) if (e is Map) Map<String, dynamic>.from(e)] : const [];
