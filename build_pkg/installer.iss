; Selenograph Windows installer. Build with:  ISCC.exe installer.iss
; Expects the assembled app folder in build_pkg\Selenograph (see README, "Building a release").
#define AppName "Selenograph"
#define AppVersion "1.0.0"

[Setup]
AppId={{6F0B7D52-3C1E-4A8B-9D47-5B2E1C8A90F3}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Selenograph
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=Selenograph-Setup
SetupIconFile=..\desktop\windows\runner\resources\app_icon.ico
UninstallDisplayIcon={app}\Selenograph.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Files]
Source: "Selenograph\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Selenograph.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Selenograph.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Run]
Filename: "{app}\Selenograph.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
