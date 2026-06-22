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
#define MyAppVersion "1.19.0"
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
; Optional, opt-in AI learning. The description discloses the real cost so the
; user can make an informed choice before ticking it.
Name: "ailearning"; \
    GroupDescription: "Optional AI feature (you can turn this on/off later in the tray):"; \
    Description: "Adaptive vocabulary learning — a local AI model learns your technical terms (names, tools, jargon) so they transcribe correctly over time. One-time ~1.8 GB download; uses ~2 GB RAM only while learning, then frees it (runs only when you edit and copy a transcript). 100% offline — no account, nothing leaves your PC."; \
    Flags: unchecked

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
; One-shot marker: if the user opted into adaptive learning, the app enables it
; on first run (downloading the model with progress) and clears this value.
Root: HKCU; Subkey: "Software\VibeFlow"; ValueType: dword; \
    ValueName: "EnableAiLearning"; ValueData: 1; \
    Tasks: ailearning; Flags: uninsdeletevalue uninsdeletekeyifempty

[Run]
; Interactive install: offer a "Launch VibeFlow now" checkbox on the finish page.
Filename: "{app}\{#MyAppExeName}"; Description: "Launch VibeFlow now"; \
    Flags: nowait postinstall skipifsilent
; Silent install (used by the in-app auto-updater): relaunch automatically so the
; tray app comes back after a hands-free update. We MUST launch it via Explorer,
; not as a child of the installer. Inno Setup 6.3+ enables Windows' "Redirection
; Guard" process mitigation on Setup, and it is inherited by every child process.
; That mitigation refuses to follow the symlinks in the Hugging Face model cache
; (model.bin -> blob), failing with "untrusted mount point" (WinError 448) so the
; speech model could not load after a silent update. Launching through Explorer
; runs VibeFlow in the normal shell context, outside the installer's mitigated
; process tree, so symlink traversal works exactly like a normal launch.
Filename: "{win}\explorer.exe"; Parameters: """{app}\{#MyAppExeName}"""; \
    Flags: nowait; Check: WizardSilent

[UninstallRun]
; Make sure the tray app isn't running so its files can be removed.
Filename: "{cmd}"; Parameters: "/C taskkill /IM {#MyAppExeName} /F"; \
    Flags: runhidden; RunOnceId: "StopVibeFlow"

[Code]
// VibeFlow is a tray app with no main window, so Windows' Restart Manager can't
// reliably close it ("Setup was unable to automatically close all applications").
// Force-close it ourselves before copying files — this also makes hands-free
// auto-updates work without that error dialog.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{cmd}'), '/C taskkill /IM {#MyAppExeName} /F', '',
    SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;

// On uninstall, offer to also remove the local AI runtime (Ollama), all
// downloaded AI models (several GB), and VibeFlow's per-user data — so nothing
// is left behind. The user can decline to keep Ollama (they may use it elsewhere).
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox(
      'Also remove the local AI runtime (Ollama) and ALL downloaded AI models'
      + #13#10 + '(this can free several GB), plus your VibeFlow data'
      + #13#10 + '(settings, vocabulary, writing profile, speech model)?'
      + #13#10 + #13#10 + 'Choose No to keep Ollama and your data.',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      // Stop and uninstall Ollama (silent; ignore any error).
      Exec(ExpandConstant('{cmd}'), '/C taskkill /IM ollama.exe /F', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Exec('winget',
        'uninstall --id Ollama.Ollama -e --silent --accept-source-agreements',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      // Remove Ollama program, cache, and the downloaded models.
      DelTree(ExpandConstant('{%USERPROFILE}\.ollama'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\Programs\Ollama'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\Ollama'), True, True, True);
      // Remove VibeFlow per-user data (settings, vocab, persona, speech models, log).
      DelTree(ExpandConstant('{userappdata}\VibeFlow'), True, True, True);
    end;
  end;
end;
