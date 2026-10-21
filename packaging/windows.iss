#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
[Setup]
AppId={{230DF1C6-7AE7-4EA6-9E13-431B10D9A20B}
AppName=AutoEventTracker
AppVersion={#AppVersion}
AppPublisher=Exture
DefaultDirName={localappdata}\Programs\AutoEventTracker
DefaultGroupName=AutoEventTracker
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.18362
OutputDir=..\installers
OutputBaseFilename=AutoEventTracker-{#AppVersion}-windows-x64-setup
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AutoEventTracker.exe
CloseApplications=yes
[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; Flags: unchecked
[Files]
Source: "..\dist\AutoEventTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\AutoEventTracker"; Filename: "{app}\AutoEventTracker.exe"
Name: "{autodesktop}\AutoEventTracker"; Filename: "{app}\AutoEventTracker.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\AutoEventTracker.exe"; Description: "AutoEventTrackerを起動する"; Flags: nowait postinstall skipifsilent
