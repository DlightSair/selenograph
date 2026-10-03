import 'dart:convert';
import 'dart:io';

import 'algo_paths.dart';

enum ServerLaunchResult {
  alreadyAttempted,
  algoNotFound,
  started,
  failedToStart,
}

/// Best-effort auto-start for the local API server, so the desktop app is
/// usable as a single double-click rather than "open two terminals".
///
/// Windows gotcha this works around: `flutter run` hosts the app inside a
/// Windows Job Object, and a child process spawned via plain `Process.start`
/// (even with `ProcessStartMode.detached`) stays a member of that job unless
/// explicitly broken out of it -- it runs fine for a few seconds, then gets
/// killed the moment that job is torn down (e.g. once the debug session
/// finishes attaching). `cmd /c start` sidesteps this: `start` launches the
/// target as a genuinely new top-level console process, independent of the
/// calling job, which is also why the server's own console window is
/// visible -- that's not a side effect, it's what makes a crash visible
/// instead of silently swallowed.
class ServerLauncher {
  static bool _attempted = false;
  static Process? _bundledProcess;

  /// The packaged service (server/selenograph-server.exe next to the app), if this is a packaged build.
  static File get bundledServer => File(
        '${File(Platform.resolvedExecutable).parent.path}${Platform.pathSeparator}server${Platform.pathSeparator}selenograph-server.exe',
      );
  static bool get hasBundled => Platform.isWindows && bundledServer.existsSync();

  /// Where the packaged service is listening, once started.
  static String? baseUrl;

  /// Non-Windows only: where the launched process's stdout/stderr are being
  /// logged (Windows gets a live console window instead, see above).
  static String? lastLogPath;

  /// Set after an `algoNotFound` result: every directory this session
  /// actually checked, for diagnosing a bad search assumption.
  static List<String> get lastSearchedPaths => AlgoPaths.lastSearchedPaths;

  /// Tries to spawn `python -m algo.api.server`. By default only once per
  /// app lifetime; pass `force: true` for an explicit user-triggered retry.
  static Future<ServerLaunchResult> ensureStarted({bool force = false}) async {
    if (_attempted && !force) return ServerLaunchResult.alreadyAttempted;
    _attempted = true;

    // Packaged build: the registration service ships next to the app and needs no Python. It listens on a
    // free port of its own (never a fixed one another program might use), runs without a window, and exits
    // when this app does.
    if (Platform.isWindows && bundledServer.existsSync()) {
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

    final pythonPath = Platform.isWindows
        ? '${algoDir.path}${Platform.pathSeparator}.venv${Platform.pathSeparator}Scripts${Platform.pathSeparator}python.exe'
        : '${algoDir.path}${Platform.pathSeparator}.venv${Platform.pathSeparator}bin${Platform.pathSeparator}python';

    if (!File(pythonPath).existsSync()) return ServerLaunchResult.algoNotFound;

    try {
      if (Platform.isWindows) {
        // See class doc: routes through `start` so the server escapes
        // flutter run's Job Object instead of dying with it.
        await Process.start(
          'cmd',
          ['/c', 'start', 'Lunar Registration Server', pythonPath, '-m', 'algo.api.server'],
          workingDirectory: algoDir.path,
          mode: ProcessStartMode.detached,
        );
      } else {
        final logFile = File(
          '${Directory.systemTemp.path}${Platform.pathSeparator}lunar_registration_server_launch.log',
        );
        final sink = logFile.openWrite();
        final process = await Process.start(
          pythonPath,
          ['-m', 'algo.api.server'],
          workingDirectory: algoDir.path,
          mode: ProcessStartMode.detachedWithStdio,
        );
        process.stdout.transform(utf8.decoder).listen(sink.write);
        process.stderr.transform(utf8.decoder).listen(sink.write);
        lastLogPath = logFile.path;
      }
      return ServerLaunchResult.started;
    } catch (_) {
      return ServerLaunchResult.failedToStart;
    }
  }
}
