import 'package:flutter/material.dart';

import 'screens/splash_screen.dart';
import 'services/api_client.dart';
import 'services/server_launcher.dart';
import 'theme/platinum.dart';

void main() {
  runApp(const LunarRegistrationApp());
}

class LunarRegistrationApp extends StatelessWidget {
  /// Injectable for tests; the app uses the defaults.
  final ApiClient? api;
  final Future<ServerLaunchResult> Function({bool force})? launcher;

  const LunarRegistrationApp({super.key, this.api, this.launcher});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Selenograph',
      theme: buildPlatinumTheme(),
      // Scrollbars are placed explicitly where wanted (the automatic desktop
      // ones would double up with them).
      scrollBehavior: const MaterialScrollBehavior().copyWith(scrollbars: false),
      debugShowCheckedModeBanner: false,
      home: SplashScreen(api: api, launcher: launcher),
    );
  }
}
