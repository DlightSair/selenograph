import 'package:flutter/material.dart';

import '../theme/platinum.dart';
import '../ui/moon.dart';
import '../ui/panels.dart';
import '../ui/screen.dart';

/// A classic "About" box: the Moon, the name, one paragraph, and the shortcuts.
class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const ScreenHeader(title: 'About', subtitle: 'Version 1.0'),
        Expanded(
          child: ScreenBody(
            maxWidth: 760,
            child: Entrance(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Panel(
                    title: 'Selenograph',
                    padding: const EdgeInsets.all(18),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const MoonIcon(size: 96, phase: 0.62),
                        const SizedBox(width: 20),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text('Selenograph', style: titleStyle(size: 20)),
                              Text('Smart India Hackathon 2026 · problem statement 26166', style: captionStyle()),
                              const SizedBox(height: 10),
                              Text(
                                'Co-registration of Chandrayaan-2 OHRC (0.25 m), TMC-2 (5 m) and IIRS (100 m) images to LRO reference mosaics. '
                                'Runs that fail the fit checks are reported as No fit.',
                                style: ui(height: 1.45),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  const Panel(
                    title: 'Supported conditions',
                    child: PropertyTable(labelWidth: 120, rows: [
                      Prop('Illumination', 'Sun-angle differences: a DEM relit with the source’s Sun, and an image representation chosen per scene.', monospace: false, maxLines: 4),
                      Prop('Viewpoint', 'Non-rigid residual field (cross-validated); DEM parallax term', monospace: false, maxLines: 4),
                      Prop('Scale', '0.25 to 100 m/px; coarse-to-fine matching at common GSD', monospace: false, maxLines: 4),
                    ]),
                  ),],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
