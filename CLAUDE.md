# JY Tools (JY Launcher + JY Explorer) — 이어서 작업할 때

먼저 `런쳐탐색기진행상황.md` (버전별 기록, 구조, 미배포 변경) 와 `다른PC에서_이어하기.md`(W 드라이브 상위 폴더) 를 읽을 것.

## 사용자 규칙 (대화에서 정해진 것)
- **배포(태그/push)는 사용자가 "올려" 라고 할 때만.** 하루 작업을 모아서 한 번에 올리는 것을 선호. 로컬 커밋까지만 해 둘 것.
- 사용자가 같은 PC 를 동시에 쓰는 중: 창을 띄우거나 클립보드/사용자 프로세스를 건드리는 테스트는 피함 (테스트는 offscreen Qt + 임시 APPDATA + `JY_INSTANCE`). 사용자의 notepad 등 프로세스를 종료하지 말 것.
- UAC/관리자 권한이 필요한 명령은 동의 없이 실행하지 않음.
- Windows 탐색기 설정은 건드리지 않음 (즐겨찾기 고정/해제만).
- 취소된 기능: 패널 4개, Ctrl+Shift+번호 단축키.
- 한국어로 답하고, 확인하지 못한 것은 확인 안 했다고 분명히 말함.

## 작업 방식
- **여러 PC 에서 이어서 개발: W:\파이썬\JYTools\Launcher_Explorer 가 기준(허브).** 작업 시작 전에 W 와 로컬을 비교(`git log` 의 HEAD 와 변경 파일 시각)해서 W 가 더 새로우면 W → 로컬로 가져온 뒤 로컬에서 개발하고, 끝나면(커밋 직후) 로컬 → W 로 백업(`robocopy /E`, **/MIR 금지**, build/dist/dist_installer/__pycache__ 제외). 양쪽에 서로 다른 변경이 있으면 덮어쓰지 말고 사용자에게 물어볼 것. 진행상황은 `런쳐탐색기진행상황.md` 에 기록(W 에도 반영).
- W 에서 git 을 직접 쓰면 dubious ownership 오류 → `git -c safe.directory='*'` 로 읽기만 하거나 로컬로 복사해서 작업.
- 설치 파일은 로컬 빌드가 아니라 `v*` 태그 push → `.github/workflows/release.yml`. 버전은 `version.py` 한 곳.
- 새 단축키를 등록하면 `SHORTCUT_HELP`(JYExplorer.py) 와 `make_manual.py` 도 갱신 (test_ops 가 목록 일치 검사).
- 테스트: `ci_test.ps1` (PYTHONUTF8, QT offscreen). 콘솔 출력은 ASCII 로.
- PowerShell 도구에서 `Remove-Item` 같은 삭제는 오탐 경고가 나므로 `(Get-Item x).Delete()` 사용.
- 파일이 원인 불명으로 되돌려진 적이 있음 → 수정 후 바로 커밋하고 W 에 복사.
