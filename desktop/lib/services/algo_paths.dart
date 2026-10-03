import 'dart:io';

/// Locates the `algo/` directory (identified by containing its own `.venv`)
/// near the running process, by walking upward from both the working
/// directory and the executable's own location. Shared by ServerLauncher (to
/// find the Python interpreter to spawn) and the "New Project" file picker
/// (to turn an absolute picked path into one relative to algo/, matching the
/// existing configs/*.yaml convention).
class AlgoPaths {
  AlgoPaths._();

  static List<String> lastSearchedPaths = [];

  static Directory? findAlgoDir() {
    lastSearchedPaths = [];
    final roots = <Directory>[
      Directory.current,
      File(Platform.resolvedExecutable).parent,
    ];
    for (final root in roots) {
      Directory? dir = root;
      for (int i = 0; i < 12 && dir != null; i++) {
        final candidate = Directory('${dir.path}${Platform.pathSeparator}algo');
        lastSearchedPaths.add(candidate.path);
        final venvMarker = Directory('${candidate.path}${Platform.pathSeparator}.venv');
        if (candidate.existsSync() && venvMarker.existsSync()) {
          return candidate;
        }
        final parent = dir.parent;
        dir = parent.path == dir.path ? null : parent; // stop at filesystem root
      }
    }
    return null;
  }
}
