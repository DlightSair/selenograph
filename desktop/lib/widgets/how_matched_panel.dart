import 'package:flutter/material.dart';

import '../models/run_metrics.dart';
import '../theme/platinum.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';

/// "How it was matched", as a list of compact panels for the results
/// inspector: the coarse-to-fine stage table, the representation vote, which
/// extra layers/models were used, and the rescue note. Everything is optional
/// in the metrics, so each panel only appears when its data exists (older
/// runs). With `failed` the same panels read as "what was tried".
class HowMatched {
  HowMatched._();

  /// Whether there is anything to show at all.
  static bool hasContent(RunMetrics m) =>
      m.stages.isNotEmpty || m.captureCandidates.isNotEmpty || m.relitLayer != null || m.nonrigid != null || m.rescue != null;

  static List<Widget> panels(RunMetrics m, {bool failed = false}) {
    return [
      if (m.stages.isNotEmpty) _stages(m, failed),
      if (m.captureCandidates.isNotEmpty) _vote(m, failed),
      if (m.relitLayer != null || m.nonrigid != null) _layers(m),
      if (m.rescue != null) _rescue(m.rescue!),
    ];
  }

  static String _int(int? v) => v == null ? '—' : '$v';

  /// 6.0 -> "6", 2.5 -> "2.5".
  static String _trim(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);

  // ---- stages --------------------------------------------------------------

  static Widget _stages(RunMetrics m, bool failed) {
    final refGsd = m.referenceGsdM;
    String down(StageInfo s) => s.down == null ? '—' : '${_trim(s.down!)}×';
    String metres(StageInfo s) {
      if (s.down == null || refGsd == null) return '—';
      final v = s.down! * refGsd;
      return v.toStringAsFixed(v < 100 ? 1 : 0);
    }

    return Panel(
      title: failed ? 'What was tried: stages' : 'Matching stages',
      collapsible: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Note(
            'Matching runs coarse to fine: early stages find the overall shift on a shrunken image, later ones '
            'refine it at higher resolution. Inliers are tiles consistent with the shared transform (in the first '
            'stage, tiles that agree on one global shift).',
          ),
          const SizedBox(height: 8),
          GridTable(
            rowHeight: 22,
            cellPadding: 5,
            columns: const [
              GridColumn('#', width: 22),
              GridColumn('Down', flex: 1, align: TextAlign.right, tooltip: 'How much the images are shrunk at this stage (relative to the reference)'),
              GridColumn('m/px', flex: 1, align: TextAlign.right, tooltip: 'Working resolution in metres per pixel'),
              GridColumn('Tile', width: 40, align: TextAlign.right, tooltip: 'Tile size in pixels'),
              GridColumn('Tried', width: 44, align: TextAlign.right, tooltip: 'Tiles attempted'),
              GridColumn('Matched', width: 58, align: TextAlign.right, tooltip: 'Tiles that produced a match'),
              GridColumn('Inliers', width: 54, align: TextAlign.right, tooltip: 'Tiles consistent with the transform'),
            ],
            rows: [
              for (var i = 0; i < m.stages.length; i++)
                [
                  '${i + 1}',
                  down(m.stages[i]),
                  metres(m.stages[i]),
                  m.stages[i].tile == null ? '—' : '${m.stages[i].tile}',
                  _int(m.stages[i].attempted),
                  _int(m.stages[i].matched),
                  _int(m.stages[i].inliers),
                ],
            ],
          ),
        ],
      ),
    );
  }

  // ---- representation vote ----------------------------------------------------

  static Widget _vote(RunMetrics m, bool failed) {
    final chosen = m.structure?.split('@').first;
    return Panel(
      title: failed ? 'What was tried: representations' : 'Representation vote',
      collapsible: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Note(
            'The matcher tries several image representations on the same tiles and keeps the one whose tiles '
            'agree most on a single shift. Bars show the share of tiles that agree.',
          ),
          const SizedBox(height: 10),
          for (final e in m.captureCandidates.entries) ...[
            _voteRow(e.key, e.value, selected: e.key == chosen),
            const SizedBox(height: 9),
          ],
          if (m.structureSwitched.isNotEmpty)
            Note('Switched representation while refining: ${m.structureSwitched.join(', ')}.'),
        ],
      ),
    );
  }

  static Widget _voteRow(String name, CaptureCandidate c, {required bool selected}) {
    final ncc = c.medianNcc;
    // Median NCC is a correlation, so it lives in [-1, 1]; anything outside
    // comes from a degenerate handful of tiles and would only mislead.
    final nccText = (ncc != null && ncc.abs() <= 1.0) ? ' · NCC ${ncc.toStringAsFixed(2)}' : '';
    final counts = c.attempted == null ? '—' : '${_int(c.agree)} of ${c.attempted} tiles agree$nccText';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Text(name, style: ui(weight: FontWeight.w700)),
            if (selected) ...[
              const SizedBox(width: 6),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(begin: Alignment.topCenter, end: Alignment.bottomCenter, colors: [Pt.accentHi, Pt.accent]),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Pt.accentLo),
                ),
                child: Text('chosen', style: ui(size: 10.5, color: Colors.white, weight: FontWeight.w700)),
              ),
            ],
          ],
        ),
        const SizedBox(height: 4),
        Meter(value: c.agreement, highlight: selected, height: 13),
        const SizedBox(height: 3),
        Text(counts, style: mono(size: 11, color: Pt.ink2)),
      ],
    );
  }

  // ---- layers & models ---------------------------------------------------------

  static Widget _layers(RunMetrics m) {
    final parallax = m.nonrigid?.parallax;
    final relit = m.relitLayer;
    final String parallaxDetail;
    if (parallax != null) {
      parallaxDetail = 'A terrain-height parallax pattern from the DEM was fitted to the residual shifts. '
          'Fitted coefficients are shown against the size expected from the viewing geometry.';
    } else if (m.demAvailable == false) {
      parallaxDetail = 'No DEM was available for this project.';
    } else {
      parallaxDetail = 'No terrain-parallax term was fitted for this run.';
    }
    return Panel(
      title: 'Layers and models',
      collapsible: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (relit != null) ...[
            _fact(
              used: relit,
              title: 'Illumination-aware DEM layer',
              detail: relit
                  ? 'A DEM re-lit with this image’s own Sun azimuth and elevation was added as an extra reference layer, '
                      'so shading is compared under matching light.'
                  : (m.demAvailable == false
                      ? 'No DEM was available for this project, so no re-lit layer could be built.'
                      : 'A DEM was available, but the re-lit layer was not enabled for this run.'),
            ),
            const SizedBox(height: 10),
          ],
          _fact(
            used: parallax != null,
            title: 'Terrain parallax model',
            detail: parallaxDetail,
            data: parallax == null ? null : _parallaxData(parallax),
          ),
        ],
      ),
    );
  }

  static Widget _fact({required bool used, required String title, required String detail, Widget? data}) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 1),
          child: Icon(used ? Icons.check_circle : Icons.remove_circle_outline, size: 16, color: used ? Pt.green : Pt.ink3),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Flexible(child: Text(title, style: ui(weight: FontWeight.w700))),
                  const SizedBox(width: 8),
                  Text(used ? 'used' : 'not used', style: ui(size: 11, color: used ? Pt.green : Pt.ink2, weight: FontWeight.w700)),
                ],
              ),
              const SizedBox(height: 2),
              Note(detail),
              if (data != null) ...[const SizedBox(height: 6), data],
            ],
          ),
        ),
      ],
    );
  }

  static String _coef(double? v) => v == null ? '—' : v.toStringAsFixed(4);

  static Widget _parallaxData(ParallaxInfo p) {
    return PropertyTable(labelWidth: 120, rows: [
      Prop('α along-track', _coef(p.alphaAlong)),
      if (p.expectedAbsAlphaAlong != null) Prop('expected |α| along', _coef(p.expectedAbsAlphaAlong)),
      if (p.alphaCross != null) Prop('α cross-track', _coef(p.alphaCross)),
      if (p.expectedAbsAlphaCross != null) Prop('expected |α| cross', _coef(p.expectedAbsAlphaCross)),
      if (p.explainedVariance != null) Prop('Residual explained', '${(p.explainedVariance! * 100).toStringAsFixed(0)}%'),
      if (p.demReliefM != null) Prop('DEM relief', '${p.demReliefM!.toStringAsFixed(0)} m'),
    ]);
  }

  // ---- rescue ------------------------------------------------------------------

  static Widget _rescue(RescueInfo r) {
    return Panel(
      title: 'Rescue search',
      collapsible: true,
      accent: Pt.amber,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Note(
            'The normal capture failed, so a wide search over rotation and scale was run to recover a badly wrong '
            'starting guess. The best hypothesis is listed below.',
          ),
          const SizedBox(height: 8),
          PropertyTable(labelWidth: 120, rows: [
            if (r.rotationDeg != null) Prop('Rotation', '${r.rotationDeg!.toStringAsFixed(1)}°'),
            if (r.scale != null) Prop('Scale', r.scale!.toStringAsFixed(2)),
            if (r.hypothesesTried != null) Prop('Hypotheses tried', '${r.hypothesesTried}'),
          ]),
        ],
      ),
    );
  }
}
