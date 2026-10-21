#ifndef AppVersion
#define AppVersion "0.16.0"
#endif
[Setup]
AppId={{485382A0-3437-4DB8-9F23-794D4314474B}
AppName=OrbitDrop
AppVersion={#AppVersion}
AppPublisher=OrbitDrop
DefaultDirName={localappdata}\Programs\OrbitDrop
DefaultGroupName=OrbitDrop
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\dist\release
OutputBaseFilename=OrbitDrop-{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupMutex=OrbitDropSetup
UninstallDisplayIcon={app}\OrbitDrop.exe
[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; Flags: unchecked
[Files]
Source: "..\dist\OrbitDrop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\OrbitDrop"; Filename: "{app}\OrbitDrop.exe"
Name: "{autodesktop}\OrbitDrop"; Filename: "{app}\OrbitDrop.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\OrbitDrop.exe"; Description: "OrbitDrop starten"; Flags: nowait postinstall skipifsilent
