import 'dart:async';
import 'package:flutter/material.dart';

import '../services/api_client.dart';
import '../services/server_launcher.dart';
import '../theme/platinum.dart';
import '../ui/controls.dart';
import '../ui/moon.dart';
import '../ui/panels.dart';
import 'app_shell.dart';

/// The app's single startup gate. Owns connecting to the local pipeline
/// service end to end — checking it, launching it if needed, waiting for it to
/// come up — so nothing downstream ever has to know a local server is
/// involved. Drawn like a classic Mac start-up window on the desktop pattern.
class SplashScreen extends StatefulWidget {
  /// Injectable for tests; the app uses the defaults.
  final ApiClient? api;
  final Future<ServerLaunchResult> Function({bool force})? launcher;

  const SplashScreen({super.key, this.api, this.launcher});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  late final ApiClient _api = widget.api ?? ApiClient();

  static const _statusMessages = [
    'Preparing workspace…',
    'Loading the pipeline…',
    'Almost ready…',
  ];

  String _status = _statusMessages.first;
  bool _troubleshooting = false;
  Timer? _statusCycler;

  @override
  void initState() {
    super.initState();
    _connect();
  }

  @override
  void dispose() {
    _statusCycler?.cancel();
    super.dispose();
  }

  Future<void> _connect() async {
    setState(() {
      _troubleshooting = false;
      _status = _statusMessages.first;
    });

    var messageIndex = 0;
    _statusCycler?.cancel();
    _statusCycler = Timer.periodic(const Duration(seconds: 3), (_) {
      messageIndex = (messageIndex + 1) % _statusMessages.length;
      if (mounted) setState(() => _status = _statusMessages[messageIndex]);
    });

    if (await _api.health()) {
      _proceed();
      return;
    }

    await (widget.launcher ?? ServerLauncher.ensureStarted)(force: true);

    // About 45 s of polling, counted in attempts rather than wall-clock time.
    for (var attempt = 0; mounted && attempt < 64; attempt++) {
      if (await _api.health()) {
        _proceed();
        return;
      }
      await Future.delayed(const Duration(milliseconds: 700));
    }

    _statusCycler?.cancel();
    if (!mounted) return;
    setState(() => _troubleshooting = true);
  }

  void _proceed() {
    _statusCycler?.cancel();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(fadeRoute((_) => AppShell(api: _api)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Pt.desk,
      body: CustomPaint(
        painter: const _DeskPainter(),
        child: Center(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 260),
            child: _troubleshooting ? _troubleView() : _loadingView(),
          ),
        ),
      ),
    );
  }

  Widget _window({required String title, required Widget child, double width = 400, Key? key}) {
    return Container(
      key: key,
      width: width,
      decoration: BoxDecoration(
        color: Pt.chrome,
        borderRadius: BorderRadius.circular(kRadius + 2),
        border: Border.all(color: Pt.edge),
        boxShadow: const [BoxShadow(color: Color(0x80000000), offset: Offset(4, 5))],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(kRadius + 1),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              height: 24,
              decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Pt.edge))),
              child: CustomPaint(
                painter: const PinstripePainter(),
                child: Center(
                  child: Container(
                    color: Pt.chrome,
                    padding: const EdgeInsets.symmetric(horizontal: 10),
                    child: Text(title, style: ui(weight: FontWeight.w700)),
                  ),
                ),
              ),
            ),
            child,
          ],
        ),
      ),
    );
  }

  Widget _loadingView() {
    return _window(
      key: const ValueKey('loading'),
      title: 'Starting',
      child: Padding(
        padding: const EdgeInsets.fromLTRB(28, 24, 28, 24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const AnimatedMoon(size: 96),
            const SizedBox(height: 14),
            Text('Selenograph', style: titleStyle(size: 22)),
            const SizedBox(height: 2),
            Text('Lunar image registration', style: captionStyle(size: 12)),
            const SizedBox(height: 20),
            const BarberPole(width: 300, height: 14),
            const SizedBox(height: 10),
            Text(_status, style: ui(color: Pt.ink2)),
          ],
        ),
      ),
    );
  }

  Widget _troubleView() {
    return _window(
      key: const ValueKey('trouble'),
      title: 'Error',
      width: 520,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Callout(
              kind: CalloutKind.error,
              title: 'Registration service did not respond.',
              child: Text('Projects and runs are unavailable until it is running.', style: TextStyle(fontSize: 12, color: Pt.ink2)),
            ),
            const SizedBox(height: 12),
            Panel(
              title: 'Details',
              collapsible: true,
              initiallyOpen: false,
              child: SelectableText(_diagnosticText(), style: mono(size: 11, color: Pt.ink2)),
            ),
            const SizedBox(height: 14),
            Align(
              alignment: Alignment.centerRight,
              child: PushButton(label: 'Retry', isDefault: true, onPressed: _connect),
            ),
          ],
        ),
      ),
    );
  }

  String _diagnosticText() {
    final searched = ServerLauncher.lastSearchedPaths;
    final log = ServerLauncher.lastLogPath;
    final buffer = StringBuffer('Could not reach 127.0.0.1:8000.\n');
    if (searched.isNotEmpty) {
      buffer.write('Searched for algo/.venv at:\n${searched.take(6).join('\n')}\n');
    }
    if (log != null) {
      buffer.write('Server log: $log\n');
    }
    buffer.write(
      'Manual fallback: run algo/start_server.bat, or from algo/ inside its venv:\n'
      '  ./.venv/Scripts/python.exe -m algo.api.server',
    );
    return buffer.toString();
  }
}

/// The classic grey "desktop" dither behind windows.
class _DeskPainter extends CustomPainter {
  const _DeskPainter();

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = Pt.desk);
    final dot = Paint()
      ..color = const Color(0x16000000)
      ..isAntiAlias = false;
    for (double y = 0; y < size.height; y += 2) {
      for (double x = (y / 2).floor().isEven ? 0 : 1; x < size.width; x += 2) {
        canvas.drawRect(Rect.fromLTWH(x, y, 1, 1), dot);
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}
