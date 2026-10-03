import 'json_util.dart';

/// Which registration options a project's config turns on
/// (`details.registration`). Every field may be null.
class RegistrationOptions {
  final String? mode; // e.g. "prior_guided"
  final bool? relit; // DEM re-lit with the source's Sun as an extra reference layer
  final bool? dem; // DEM available for the terrain-parallax model
  final bool? nonrigid; // cross-validated non-rigid residual field

  RegistrationOptions({this.mode, this.relit, this.dem, this.nonrigid});

  factory RegistrationOptions.fromJson(Map<String, dynamic> json) => RegistrationOptions(
        mode: asString(json['mode']),
        relit: asBool(json['relit']),
        dem: asBool(json['dem']),
        nonrigid: asBool(json['nonrigid']),
      );
}

/// Facts read from a project's actual source/reference products
/// (`GET /configs/{name}/details`), as opposed to the config file itself.
/// All of it is nullable: the server omits what a product doesn't provide.
class ConfigDetails {
  final String? sourceInstrument;
  final double? sourceGsd;
  final double? sourceSunElevation;
  final double? sourceSunAzimuth;
  final int? sourceLines;
  final int? sourceSamples;

  // Viewing geometry (spacecraft attitude when the source was acquired).
  final double? sourceRoll;
  final double? sourcePitch;
  final double? sourceYaw;
  final double? sourceAltitudeKm;

  /// "n" nadir, "f" forward (+25 deg), "a" aft (-25 deg); null for other instruments.
  final String? sourceCamera;

  final double? referenceGsd;
  final int? referenceRows;
  final int? referenceCols;
  final String? referenceProvider;
  final String? referenceLayer;

  final RegistrationOptions? registration;

  ConfigDetails({
    this.sourceInstrument,
    this.sourceGsd,
    this.sourceSunElevation,
    this.sourceSunAzimuth,
    this.sourceLines,
    this.sourceSamples,
    this.sourceRoll,
    this.sourcePitch,
    this.sourceYaw,
    this.sourceAltitudeKm,
    this.sourceCamera,
    this.referenceGsd,
    this.referenceRows,
    this.referenceCols,
    this.referenceProvider,
    this.referenceLayer,
    this.registration,
  });

  /// How many reference pixels one source pixel spans.
  double? get expectedScale =>
      (sourceGsd != null && referenceGsd != null && referenceGsd! > 0) ? sourceGsd! / referenceGsd! : null;

  /// Plain-language camera name, or null when the product has no camera code.
  String? get cameraLabel {
    switch (sourceCamera?.toLowerCase()) {
      case 'n':
        return 'Nadir (looking straight down)';
      case 'f':
        return 'Forward (+25°)';
      case 'a':
        return 'Aft (−25°)';
      default:
        return sourceCamera;
    }
  }

  factory ConfigDetails.fromJson(Map<String, dynamic> json) {
    final source = asMap(json['source']) ?? const <String, dynamic>{};
    final reference = asMap(json['reference']) ?? const <String, dynamic>{};
    final registration = asMap(json['registration']);
    return ConfigDetails(
      sourceInstrument: asString(source['instrument']),
      sourceGsd: asDouble(source['gsd']),
      sourceSunElevation: asDouble(source['sun_elevation']),
      sourceSunAzimuth: asDouble(source['sun_azimuth']),
      sourceLines: asInt(source['lines']),
      sourceSamples: asInt(source['samples']),
      sourceRoll: asDouble(source['roll']),
      sourcePitch: asDouble(source['pitch']),
      sourceYaw: asDouble(source['yaw']),
      sourceAltitudeKm: asDouble(source['altitude_km']),
      sourceCamera: asString(source['camera']),
      referenceGsd: asDouble(reference['gsd']),
      referenceRows: asInt(reference['rows']),
      referenceCols: asInt(reference['cols']),
      referenceProvider: asString(reference['provider']),
      referenceLayer: asString(reference['layer']),
      registration: registration == null ? null : RegistrationOptions.fromJson(registration),
    );
  }
}
