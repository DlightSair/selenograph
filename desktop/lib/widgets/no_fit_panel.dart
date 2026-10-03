import 'package:flutter/material.dart';

import '../theme/platinum.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';

/// Shown instead of the numeric readouts when a run completed but the matcher
/// found no transform it trusts (`metrics.failure`). Deliberately calm: this is
/// the pipeline refusing to return a confident-looking wrong answer, not a crash.
class NoFitPanel extends StatelessWidget {
  final String failure;

  const NoFitPanel({super.key, required this.failure});

  /// One plain-language line on what usually causes this kind of failure,
  /// picked from the server's reason text.
  static String hintFor(String failure) {
    final f = failure.toLowerCase();
    if (f.contains('no usable contrast') || f.contains('shadow') || f.contains('unlit')) {
      return 'This usually means the strip is in shadow or unlit when imaged, so there is no '
          'surface detail to match. Imagery taken with the Sun higher usually works.';
    }
    if (f.contains('global shift')) {
      return 'The two images never agreed on one overall offset. This usually means they look '
          'too different (very different Sun angle) or the starting position guess is far off.';
    }
    if (f.contains('not consistent with one transform') || f.contains('too few agree')) {
      return 'The tile-by-tile measurements contradicted each other. This usually means the '
          'images look too different, or the starting position guess was wrong.';
    }
    return 'Usual causes are very different lighting between the two images, shadowed or '
        'low-contrast imagery, or a starting position guess that is far off.';
  }

  @override
  Widget build(BuildContext context) {
    return Panel(
      title: 'No reliable fit',
      accent: Pt.red,
      icon: Icons.error,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('The run finished, but no transform could be trusted.', style: ui(size: 14, weight: FontWeight.w700, color: Pt.red)),
          const SizedBox(height: 10),
          PropertyTable(labelWidth: 70, rows: [
            Prop('Reason', failure, monospace: false, maxLines: 10),
          ]),
          const SizedBox(height: 10),
          Text(hintFor(failure), style: ui(height: 1.45)),
          const SizedBox(height: 8),
          const Note(
            'Rather than return a confident-looking wrong answer, the pipeline reports no fit. '
            'Nothing was fitted, so there are no accuracy numbers or overlays for this run.',
          ),
        ],
      ),
    );
  }
}
