@echo off
REM Starts the registration API server in its own console window, independent
REM of whatever launched this script (so it isn't tied to flutter run's own
REM process tree / Job Object -- see desktop/lib/services/server_launcher.dart
REM for why that matters). Double-click this, or run it before `flutter run`,
REM if the desktop app's own auto-start isn't working.
cd /d "%~dp0"
start "Lunar Registration Server" ".venv\Scripts\python.exe" -m algo.api.server
