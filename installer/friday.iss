; Inno Setup script for F.R.I.D.A.Y. Build with: iscc installer\friday.iss
; Per-user install under %LOCALAPPDATA% so no UAC prompt is needed.
; Unsigned: first launch shows SmartScreen — More info > Run anyway.

#define AppVersion "1.0.0"

[Setup]
AppId={{9F2C7C2E-6C2E-4C7F-9E6E-F51D1A3B7A10}
AppName=F.R.I.D.A.Y.
AppVersion={#AppVersion}
AppPublisher=Damon Lin
DefaultDirName={localappdata}\Programs\FRIDAY
DefaultGroupName=F.R.I.D.A.Y.
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=FRIDAY-Setup-{#AppVersion}
SetupIconFile=..\static\images\friday.ico
UninstallDisplayIcon={app}\FRIDAY.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\FRIDAY\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\F.R.I.D.A.Y."; Filename: "{app}\FRIDAY.exe"
Name: "{userdesktop}\F.R.I.D.A.Y."; Filename: "{app}\FRIDAY.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FRIDAY.exe"; Description: "Launch F.R.I.D.A.Y."; Flags: nowait postinstall skipifsilent

; Settings and the Edge profile live outside {app} (%APPDATA%\FRIDAY, %LOCALAPPDATA%\FRIDAY)
; and are deliberately left behind on uninstall — reinstalling keeps your keys.
