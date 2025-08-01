; Script generated by the Inno Setup Script Wizard.
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define MyAppName "Joulescope"
#define MyAppVersion "1.3.7"
#define MyAppVersionUnderscores "1_3_7"
#define MyAppPublisher "Jetperch LLC"
#define MyAppURL "https://www.joulescope.com"
#define MyAppExeName "joulescope.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside the IDE.)
AppId={{F0D92A65-AC92-4313-BBD8-393C1FBE392B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
;AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE.txt
OutputDir=dist_installer
OutputBaseFilename=joulescope_setup_{#MyAppVersionUnderscores}
SetupIconFile=joulescope_ui\resources\icon.ico
UninstallDisplayIcon={app}\joulescope.exe
ChangesAssociations=yes
Compression=lzma
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\joulescope\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[InstallDelete]
Type: files; Name: "{app}\psutil\*.pyd"

[Icons]
Name: "{commonprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall

[Registry]
; https://stackoverflow.com/questions/26536030/file-association-in-inno-setup
Root: HKCR; Subkey: ".jls";                             ValueData: "{#MyAppName}";          Flags: uninsdeletevalue; ValueType: string;  ValueName: ""
Root: HKCR; Subkey: "{#MyAppName}";                     ValueData: "Program {#MyAppName}";  Flags: uninsdeletekey;   ValueType: string;  ValueName: ""
Root: HKCR; Subkey: "{#MyAppName}\DefaultIcon";         ValueData: "{app}\{#MyAppExeName},0";                        ValueType: string;  ValueName: ""
Root: HKCR; Subkey: "{#MyAppName}\shell\open\command";  ValueData: """{app}\{#MyAppExeName}"" ""%1""";               ValueType: string;  ValueName: ""

[Code]
function GetUninstallerPath(): String;
var
  sUnInstPath1: String;
  sUnInstPath2: String;
  sUnInstallString: String;
begin
    sUnInstPath1 := ExpandConstant('Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
    sUnInstPath2 := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
    if (RegQueryStringValue(HKLM, sUnInstPath1, 'UninstallString', sUnInstallString)) then
    else if (RegQueryStringValue(HKCU, sUnInstPath1, 'UninstallString', sUnInstallString)) then
    else if (RegQueryStringValue(HKLM, sUnInstPath2, 'UninstallString', sUnInstallString)) then
    else if (RegQueryStringValue(HKCU, sUnInstPath2, 'UninstallString', sUnInstallString)) then
    else
        ;
    Result := sUnInstallString;
end;

procedure UninstallOldVersion();
var
    UninstallerPath: String;
    ResultCode: Integer;
begin
    UninstallerPath := GetUninstallerPath();
    if (UninstallerPath <> '') then begin
        UninstallerPath := RemoveQuotes(UninstallerPath);
        Exec(UninstallerPath, '/VERYSILENT /NORESTART /SUPPRESSMSGBOXES', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
    if (CurStep = ssInstall) then
    begin
        UninstallOldVersion();
    end;
end;
