import 'dart:io';

import 'algo_paths.dart';

enum ServerLaunchResult {
  alreadyAttempted,
  algoNotFound,
  started,
  failedToStart,
}

/// Best-effort auto-start for the local API server.
///
/// A packaged build runs the bundled service. A development checkout runs
/// `python -m algo.api.server` through `cmd /c start`: `flutter run` hosts the
/// app in a Windows Job Object, and a child started with plain `Process.start`
/// stays in that job and is killed when it is torn down. `start` launches a
/// new top-level console process outside the job, and its visible console
/// window shows server crashes.
class ServerLauncher {
  static bool _attempted = false;
  static Process? _bundledProcess;

  /// The packaged service (`server/selenograph-server.exe` next to the app).
  static File get bundledServer => File(
        '${File(Platform.resolvedExecutable).parent.path}${Platform.pathSeparator}server${Platform.pathSeparator}selenograph-server.exe',
      );
  static bool get hasBundled => bundledServer.existsSync();

  /// Where the packaged service is listening, once started.
  static String? baseUrl;

  /// Directories checked while looking for the algo folder, for diagnostics.
  static List<String> get lastSearchedPaths => AlgoPaths.lastSearchedPaths;

  /// Tries to spawn `python -m algo.api.server`. By default only once per
  /// app lifetime; pass `force: true` for an explicit user-triggered retry.
  static Future<ServerLaunchResult> ensureStarted({bool force = false}) async {
    if (_attempted && !force) return ServerLaunchResult.alreadyAttempted;
    _attempted = true;

    // Packaged build: the service ships next to the app and needs no Python. It
    // listens on a free port, runs without a window, and exits with this app.
    if (hasBundled) {
      try {
        _bundledProcess?.kill();
        final probe = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
        final port = probe.port;
        await probe.close();
        _bundledProcess = await Process.start(
          bundledServer.path,
          ['--port', '$port', '--parent-pid', '$pid'],
          workingDirectory: bundledServer.parent.path,
          mode: ProcessStartMode.detachedWithStdio,
        );
        _bundledProcess!.stdout.drain<void>();
        _bundledProcess!.stderr.drain<void>();
        baseUrl = 'http://127.0.0.1:$port';
        return ServerLaunchResult.started;
      } catch (_) {
        return ServerLaunchResult.failedToStart;
      }
    }

    final algoDir = AlgoPaths.findAlgoDir();
    if (algoDir == null) return ServerLaunchResult.algoNotFound;

    final sep = Platform.pathSeparator;
    final pythonPath = '${algoDir.path}$sep.venv${sep}Scripts${sep}python.exe';

    if (!File(pythonPath).existsSync()) return ServerLaunchResult.algoNotFound;

    try {
      await Process.start(
        'cmd',
        ['/c', 'start', 'Lunar Registration Server', pythonPath, '-m', 'algo.api.server'],
        workingDirectory: algoDir.path,
        mode: ProcessStartMode.detached,
      );
      return ServerLaunchResult.started;
    } catch (_) {
      return ServerLaunchResult.failedToStart;
    }
  }
}
