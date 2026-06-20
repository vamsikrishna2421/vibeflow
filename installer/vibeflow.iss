; ============================================================================
;  VibeFlow — Inno Setup installer script
;  Produces a single "VibeFlowSetup.exe" that installs VibeFlow with a normal
;  next-next-finish wizard, optionally starts it with Windows, adds a Start
;  Menu shortcut, and registers a proper uninstaller.
;
;  Build it with:  scripts\build_installer.ps1   (builds the app first, then this)
;  Requires Inno Setup 6 (https://jrsoftware.org/isdl.php).
;
;  Per-user install (no administrator rights needed) into LocalAppData.
; ============================================================================

#define MyAppName "VibeFlow"
#define MyAppVersion "1.4.2"
#define MyAppPublisher "VibeFlow"
#define MyAppExeName "VibeFlow.exe"

[Setup]
AppId={{B7E9F3A2-1C4D-4E8B-9A5F-2D6C8E1A0B3F}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release\installer
OutputBaseFilename=VibeFlowSetup
SetupIconFile=..\src\vibeflow\resources\logos\vibeflow.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Close VibeFlow automatically when installing an update or uninstalling.
CloseApplications=yes
CloseApplicationsFilter=*.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; GroupDescription: "Startup:"; \
    Description: "Start VibeFlow automatically when I sign in to Windows"; \
    Flags: checkablealone
Name: "desktopicon"; GroupDescription: "Additional shortcuts:"; \
    Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
; The PyInstaller one-folder build (release\VibeFlow\) is bundled here.
Source: "..\release\VibeFlow\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    Tasks: desktopicon

[Registry]
; Auto-start at login (per-user). Uses the same value name the app's tray
; toggle manages, so there is a single source of truth.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "VibeFlow"; \
    ValueData: """{app}\{#MyAppExeName}"""; \
    Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch VibeFlow now"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Make sure the tray app isn't running so its files can be removed.
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "StopVibeFlow"
