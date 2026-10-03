class VizCheck {
  final String label;
  final bool? ok; // null = could not be evaluated
  final String detail;

  VizCheck({required this.label, required this.ok, required this.detail});

  factory VizCheck.fromJson(Map<String, dynamic> json) =>
      VizCheck(label: json['label'] as String, ok: json['ok'] as bool?, detail: json['detail'] as String);
}

class VizParam {
  final String label;
  final String value;

  VizParam({required this.label, required this.value});

  factory VizParam.fromJson(Map<String, dynamic> json) =>
      VizParam(label: json['label'] as String, value: json['value'] as String);
}

class VizItem {
  final String name;
  final String title;
  final String caption;
  final String group;

  VizItem({required this.name, required this.title, required this.caption, required this.group});

  factory VizItem.fromJson(Map<String, dynamic> json) => VizItem(
        name: json['name'] as String,
        title: json['title'] as String,
        caption: json['caption'] as String,
        group: json['group'] as String,
      );
}

/// Mirrors `GET /runs/{id}/viz`: sanity checks and numbers about the fitted
/// transform, plus the list of separately-zoomable images rendered for it.
class VizManifest {
  final String verdict; // ok | suspect
  final String summary;
  final List<VizCheck> checks;
  final List<VizParam> params;
  final List<VizItem> items;

  VizManifest({
    required this.verdict,
    required this.summary,
    required this.checks,
    required this.params,
    required this.items,
  });

  bool get suspect => verdict == 'suspect';

  /// Item groups in first-appearance order, so the server controls section order.
  List<String> get groups => items.map((i) => i.group).toSet().toList();

  factory VizManifest.fromJson(Map<String, dynamic> json) {
    List<T> list<T>(String key, T Function(Map<String, dynamic>) build) =>
        (json[key] as List).map((e) => build(e as Map<String, dynamic>)).toList();
    return VizManifest(
      verdict: json['verdict'] as String,
      summary: json['summary'] as String,
      checks: list('checks', VizCheck.fromJson),
      params: list('params', VizParam.fromJson),
      items: list('items', VizItem.fromJson),
    );
  }
}
