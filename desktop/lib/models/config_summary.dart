class ConfigSummary {
  final String name;
  final String aoiName;
  final double latMin;
  final double latMax;
  final double lonMin;
  final double lonMax;
  final String sourceInstrument;
  final String sourcePath;
  final String referencePath;
  final bool demEnabled;

  ConfigSummary({
    required this.name,
    required this.aoiName,
    required this.latMin,
    required this.latMax,
    required this.lonMin,
    required this.lonMax,
    required this.sourceInstrument,
    required this.sourcePath,
    required this.referencePath,
    required this.demEnabled,
  });

  factory ConfigSummary.fromJson(Map<String, dynamic> json) {
    return ConfigSummary(
      name: json['name'] as String,
      aoiName: json['aoi_name'] as String,
      latMin: (json['lat_min'] as num).toDouble(),
      latMax: (json['lat_max'] as num).toDouble(),
      lonMin: (json['lon_min'] as num).toDouble(),
      lonMax: (json['lon_max'] as num).toDouble(),
      sourceInstrument: json['source_instrument'] as String,
      sourcePath: json['source_path'] as String,
      referencePath: json['reference_path'] as String,
      demEnabled: json['dem_enabled'] as bool,
    );
  }

  String get displayName => aoiName.replaceAll('_', ' ').toUpperCase();
}
