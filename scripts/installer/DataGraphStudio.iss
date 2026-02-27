#define MyAppName "Data Graph Studio"
#define MyAppExeName "DataGraphStudio.exe"

; Build-time overrides (CI passes /DMyAppVersion=...)
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{C9A7A7B7-6B08-4A5A-8E2B-4A4AE2C1B6F5}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\..\dist_installer
OutputBaseFilename=DataGraphStudio-Setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=..\..\resources\icons\dgs.ico
CloseApplications=yes
CloseApplicationsFilter=DataGraphStudio.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; PyInstaller onedir output (repo root dist/...) — this .iss lives in scripts/installer
Source: "..\..\dist\DataGraphStudio\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ExistingInstallPage: TWizardPage;
  ChoiceUpdate: TRadioButton;
  ChoiceClean: TRadioButton;
  ChoiceSkip: TRadioButton;
  ExistingUninstallString: String;
  ShouldCleanInstall: Boolean;

function TryGetExistingUninstallString(var S: String): Boolean;
var
  Key: String;
begin
  Key := 'Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{C9A7A7B7-6B08-4A5A-8E2B-4A4AE2C1B6F5}_is1';
  Result :=
    RegQueryStringValue(HKLM64, Key, 'UninstallString', S) or
    RegQueryStringValue(HKLM, Key, 'UninstallString', S) or
    RegQueryStringValue(HKCU, Key, 'UninstallString', S);
end;

procedure InitializeWizard;
var
  IntroLabel: TNewStaticText;
begin
  ShouldCleanInstall := False;
  ExistingUninstallString := '';

  if not TryGetExistingUninstallString(ExistingUninstallString) then
    Exit;

  ExistingInstallPage := CreateCustomPage(
    wpWelcome,
    'Existing Installation Detected',
    'Choose how to proceed with the existing Data Graph Studio installation.'
  );

  IntroLabel := TNewStaticText.Create(ExistingInstallPage);
  IntroLabel.Parent := ExistingInstallPage.Surface;
  IntroLabel.Left := ScaleX(0);
  IntroLabel.Top := ScaleY(8);
  IntroLabel.Width := ExistingInstallPage.SurfaceWidth;
  IntroLabel.AutoSize := False;
  IntroLabel.WordWrap := True;
  IntroLabel.Caption :=
    'Data Graph Studio is already installed. Select one option:';

  ChoiceUpdate := TRadioButton.Create(ExistingInstallPage);
  ChoiceUpdate.Parent := ExistingInstallPage.Surface;
  ChoiceUpdate.Left := ScaleX(0);
  ChoiceUpdate.Top := IntroLabel.Top + IntroLabel.Height + ScaleY(8);
  ChoiceUpdate.Width := ExistingInstallPage.SurfaceWidth;
  ChoiceUpdate.Caption := 'Update existing installation (recommended)';
  ChoiceUpdate.Checked := True;

  ChoiceClean := TRadioButton.Create(ExistingInstallPage);
  ChoiceClean.Parent := ExistingInstallPage.Surface;
  ChoiceClean.Left := ScaleX(0);
  ChoiceClean.Top := ChoiceUpdate.Top + ChoiceUpdate.Height + ScaleY(6);
  ChoiceClean.Width := ExistingInstallPage.SurfaceWidth;
  ChoiceClean.Caption := 'Remove old version first, then install fresh';

  ChoiceSkip := TRadioButton.Create(ExistingInstallPage);
  ChoiceSkip.Parent := ExistingInstallPage.Surface;
  ChoiceSkip.Left := ScaleX(0);
  ChoiceSkip.Top := ChoiceClean.Top + ChoiceClean.Height + ScaleY(6);
  ChoiceSkip.Width := ExistingInstallPage.SurfaceWidth;
  ChoiceSkip.Caption := 'Do not install (cancel setup)';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;

  if (ExistingInstallPage <> nil) and (CurPageID = ExistingInstallPage.ID) then
  begin
    if ChoiceSkip.Checked then
    begin
      MsgBox('Installation cancelled by user choice.', mbInformation, MB_OK);
      Result := False;
      WizardForm.Close;
      Exit;
    end;

    ShouldCleanInstall := ChoiceClean.Checked;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  UninstallExe: String;
  ResultCode: Integer;
begin
  Result := '';

  if not ShouldCleanInstall then
    Exit;

  UninstallExe := RemoveQuotes(ExistingUninstallString);
  if UninstallExe = '' then
  begin
    Result := 'Failed to resolve uninstaller path for existing installation.';
    Exit;
  end;

  if not Exec(UninstallExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Failed to launch uninstaller for clean install.';
    Exit;
  end;

  if ResultCode <> 0 then
    Result := 'Uninstaller returned non-zero exit code: ' + IntToStr(ResultCode);
end;
