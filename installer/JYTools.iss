; JY Tools 설치 프로그램 (Inno Setup 6)
;
; 빌드:  프로젝트 폴더에서 .\build.ps1 -Installer
;        (내부적으로 pyinstaller --noconfirm --clean JYTools.spec → ISCC /DAppVersion=x.y.z installer\JYTools.iss)
;
; 설치 구조: {app} 한 폴더에 JYLauncher.exe + JYExplorer.exe + _internal (두 프로그램이 런타임 공유)
; 사용자별 설치(관리자 권한 불필요) 고정 → 자동 업데이트 때 UAC 창이 뜨지 않음
;
; 업데이트(자동/수동 모두 같은 Setup.exe):
;   - 이미 설치돼 있으면 "처음 설치 때만" 하는 일(즐겨찾기 불러오기, 시작프로그램/우클릭 메뉴 등록)은 건너뜀
;     → 사용자가 앱 설정에서 꺼 둔 항목이 업데이트로 다시 켜지지 않음
;   - 조용한 설치(/SILENT)에서는 /RELAUNCH=launcher,explorer 로 지정한 프로그램을 설치 후 다시 실행

#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
#define AppName "JY Tools"
#define AppIdGuid "7A3C1E52-4B8D-4F6A-9C21-5D0E8B7F3A10"

[Setup]
AppId={{{#AppIdGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=lovslave-netizen
AppPublisherURL=https://github.com/lovslave-netizen/JYLauncher_Explorer
DefaultDirName={autopf}\JYTools
DefaultGroupName=JY Tools
PrivilegesRequired=lowest
OutputDir=..\dist_installer
OutputBaseFilename=JYTools-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\JYLauncher.exe
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Components]
Name: "launcher"; Description: "JY Launcher (런처)"; Types: full
Name: "explorer"; Description: "JY Explorer (탐색기)"; Types: full

[Tasks]
Name: "importfav"; Description: "Windows 탐색기의 기존 즐겨찾기를 JY Explorer '빠른 이동'으로 불러오기 (기존 내용은 유지되고 자동 백업됩니다)"; Components: explorer
Name: "startup"; Description: "Windows 시작 시 런처 자동 실행 (트레이 상주, Ctrl+Alt+L 로 호출)"; Components: launcher
Name: "startup_explorer"; Description: "Windows 시작 시 탐색기도 자동 실행 (트레이 상주, Win+E 로 JY Explorer 열기)"; Components: explorer
Name: "ctxmenu"; Description: "Windows 탐색기 우클릭 메뉴에 '런처에 추가' 넣기"; Components: launcher
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; Flags: unchecked

[Files]
Source: "..\dist\JYTools\JYLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: launcher
Source: "..\dist\JYTools\JYExplorer.exe"; DestDir: "{app}"; Flags: ignoreversion; Components: explorer
; 공유 런타임 (_internal): 어느 쪽을 골라도 필요
Source: "..\dist\JYTools\_internal\*"; DestDir: "{app}\_internal"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\JY Launcher"; Filename: "{app}\JYLauncher.exe"; Components: launcher
Name: "{group}\JY Explorer"; Filename: "{app}\JYExplorer.exe"; Components: explorer
Name: "{autodesktop}\JY Launcher"; Filename: "{app}\JYLauncher.exe"; Tasks: desktopicon; Components: launcher
Name: "{autodesktop}\JY Explorer"; Filename: "{app}\JYExplorer.exe"; Tasks: desktopicon; Components: explorer

[Registry]
; 시작 프로그램 (처음 설치 때만 등록. 제거 시 삭제)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JYLauncher"; ValueData: """{app}\JYLauncher.exe"" --background"; Flags: uninsdeletevalue; Tasks: startup; Check: IsFreshInstall
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JYExplorer"; ValueData: """{app}\JYExplorer.exe"" --background"; Flags: uninsdeletevalue; Tasks: startup_explorer; Check: IsFreshInstall
; 앱 설정에서 켠 시작 프로그램도 제거할 때 같이 지움 (값을 새로 만들지는 않음)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "JYLauncher"; Flags: dontcreatekey uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "JYExplorer"; Flags: dontcreatekey uninsdeletevalue
; 탐색기 우클릭 메뉴: 런처에 추가 (파일 / 폴더) — 처음 설치 때만 등록 (앱 설정의 토글과 같은 키)
Root: HKCU; Subkey: "Software\Classes\*\shell\JYLauncherAdd"; ValueType: string; ValueData: "런처에 추가"; Flags: uninsdeletekey; Tasks: ctxmenu; Check: IsFreshInstall
Root: HKCU; Subkey: "Software\Classes\*\shell\JYLauncherAdd\command"; ValueType: string; ValueData: """{app}\JYLauncher.exe"" --add ""%1"""; Tasks: ctxmenu; Check: IsFreshInstall
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JYLauncherAdd"; ValueType: string; ValueData: "런처에 추가"; Flags: uninsdeletekey; Tasks: ctxmenu; Check: IsFreshInstall
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JYLauncherAdd\command"; ValueType: string; ValueData: """{app}\JYLauncher.exe"" --add ""%1"""; Tasks: ctxmenu; Check: IsFreshInstall
; 앱 설정에서 켠 우클릭 메뉴도 제거할 때 같이 지움
Root: HKCU; Subkey: "Software\Classes\*\shell\JYLauncherAdd"; ValueType: none; Flags: dontcreatekey uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Directory\shell\JYLauncherAdd"; ValueType: none; Flags: dontcreatekey uninsdeletekey

[Run]
; 처음 설치 때만: 즐겨찾기 불러오기
Filename: "{app}\JYExplorer.exe"; Parameters: "--import-favorites"; Flags: runhidden waituntilterminated; StatusMsg: "Windows 탐색기 즐겨찾기를 불러오는 중..."; Tasks: importfav; Check: IsFreshInstall
; 화면 있는 설치: 마지막 페이지의 "시작" 체크
Filename: "{app}\JYLauncher.exe"; Parameters: "--background"; Flags: nowait postinstall skipifsilent; Description: "JY Launcher 시작"; Components: launcher
; 조용한 업데이트: 업데이트 전에 켜져 있던 프로그램만 다시 실행 (/RELAUNCH=launcher,explorer)
Filename: "{app}\JYLauncher.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Components: launcher; Check: ShouldRelaunch('launcher')
Filename: "{app}\JYExplorer.exe"; Parameters: "--background"; Flags: nowait runasoriginaluser; Components: explorer; Check: ShouldRelaunch('explorer')

; 참고: 제거해도 사용자 데이터(%APPDATA%\JYTools: 북마크, 런처 목록, 백업)는 남겨 둡니다.

[Code]
var
  Fresh: Boolean;

function InitializeSetup(): Boolean;
begin
  // 같은 AppId 로 이미 설치돼 있으면 업그레이드
  Fresh := not RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + '{#AppIdGuid}' + '}_is1');
  Result := True;
end;

function IsFreshInstall(): Boolean;
begin
  Result := Fresh;
end;

function ShouldRelaunch(Name: String): Boolean;
begin
  Result := WizardSilent and (Pos(Name, ExpandConstant('{param:RELAUNCH|}')) > 0);
end;
