; ZLink Windows installer (Inno Setup 6+)
; Built by scripts/build.py / scripts/build_windows.ps1
;
; Expected layout (repo root = remote/):
;   dist\ZLink\ZLink.exe   (PyInstaller onedir output)
;   dist\ZLink-Setup-x.y.z.exe (this script's output)

#ifndef MyAppVersion
  #define MyAppVersion "0.6.4"
#endif

#ifndef MyAppName
  #define MyAppName "ZLink"
#endif

#ifndef RepoRoot
  #define RepoRoot "..\.."
#endif

#define MyAppPublisher "ZLink"
#define MyAppExeName "ZLink.exe"
#define MyAppURL "https://github.com/Huangxiaoze/zlink"
#define MyAppId "{{A7C8E2F1-4B3D-4E9A-9C21-6D8F0B5A1E33}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=
OutputDir={#RepoRoot}\dist
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile={#RepoRoot}\resources\icon\app.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoProductName={#MyAppName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#RepoRoot}\dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
