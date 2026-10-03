import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:lunar_registration_desktop/main.dart';
import 'package:lunar_registration_desktop/screens/splash_screen.dart';
import 'package:lunar_registration_desktop/services/api_client.dart';
import 'package:lunar_registration_desktop/services/server_launcher.dart';
import 'package:lunar_registration_desktop/theme/platinum.dart';

/// A backend that never answers, and a launcher that does nothing — the splash
/// must never touch the real server in tests.
ApiClient _deadApi() => ApiClient(client: MockClient((req) async => http.Response('', 500)));
Future<ServerLaunchResult> _noLaunch({bool force = false}) async => ServerLaunchResult.failedToStart;

void main() {
  testWidgets('the app starts on the splash screen with the app name', (WidgetTester tester) async {
    await tester.pumpWidget(LunarRegistrationApp(api: _deadApi(), launcher: _noLaunch));
    await tester.pump();
    expect(find.byType(SplashScreen), findsOneWidget);
    expect(find.textContaining('Selenograph'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
  });

  testWidgets('splash screen shows the app name while connecting', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildPlatinumTheme(), home: SplashScreen(api: _deadApi(), launcher: _noLaunch)));
    await tester.pump();
    expect(find.text('Selenograph'), findsOneWidget);
    expect(find.textContaining('Preparing'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2)); // lets the connect loop notice it was disposed
  });

  testWidgets('splash screen explains a backend that never comes up, and offers Retry', (tester) async {
    await tester.pumpWidget(MaterialApp(theme: buildPlatinumTheme(), home: SplashScreen(api: _deadApi(), launcher: _noLaunch)));
    await tester.pump();
    await tester.pump(const Duration(seconds: 50)); // past the 45 s wait
    await tester.pump(const Duration(milliseconds: 400));
    expect(tester.takeException(), isNull);
    expect(find.text('Error'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Details'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(seconds: 2));
  });
}
