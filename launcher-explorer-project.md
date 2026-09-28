# 개인 프로젝트 구상: 런처 + 탐색기

## 1. 런처 (Big Picture 스타일)

Steam Big Picture처럼 전체화면으로 앱을 카테고리별로 크게 띄우고 키보드/마우스로 빠르게 실행하는 전용 프로그램. Windows 시작 메뉴를 억지로 개조하는 대신 내가 원하는 분류와 UI로 직접 관리.

### 메인 화면
- 카테고리별 앱 목록 (업무 / 게임 / 도구 등, 즐겨찾기 상단 고정)
- 카테고리 펼침/접힘
- 우측 세로 스크롤바 (마우스 드래그 + 휠 지원)
- 키보드 ↑↓←→ 이동, Enter 실행, Esc 닫기
- 선택 항목이 자동으로 스크롤되어 화면에 보이게
- 설정 파일(json) 하나로 앱 추가/관리, 추후 우클릭 → 앱 추가 UI

```json
{
    "업무": [
        { "name": "Chrome", "path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" },
        { "name": "PDF", "path": "C:\\Program Files\\..." }
    ],
    "게임": [
        { "name": "Steam", "path": "C:\\Program Files (x86)\\Steam\\steam.exe" }
    ]
}
```

### 🕘 최근
- 최대 50개, 세로 스크롤
- 기본 정렬: 최근 사용순
- 검색 지원
- Windows에서 실제 사용한 최근 항목을 가져옴 (`%APPDATA%\Microsoft\Windows\Recent`)
- 항목 선택 → 바로 실행

### 📌 고정 보관함
- "가끔 필요하지만 기억하기 싫은 것" 보관용 (메인 런처는 "지금 실행할 것"만)
- 개수 제한 사실상 없음 (300개, 1000개도 스크롤로 처리, 전부 렌더링 안 함)
- 폴더/하위 폴더 무제한 지원, 각 폴더 펼침/접힘
- 세로 스크롤바 + 검색 + 정렬(파일명/확장자/수정 날짜/최근 사용/사용자 지정)
- 드래그로 폴더 간 이동, 항목 순서 변경
- 메인 런처 항목과 고정 보관함 항목은 같은 데이터를 참조 (복사본 아님)
- 클릭 → 바로 실행

### 실행 동작
- 런처 실행 → 특정 앱 실행 → 런처 자동 숨김 → 앱 종료하면 다시 런처 (선택 기능)

### 기술 스택 제안
- Python + PySide6 → PyInstaller exe

---

## 2. 탐색기 (MyExplorer) + 파일 선택창 (MyPicker)

### 배경 / 목적
Windows 표준 파일 선택창(모든 프로그램의 "첨부" 버튼)을 강제로 내 프로그램으로 교체하는 것은 불가능:
- Windows는 "기본 파일 선택기" 지정 설정을 제공하지 않음
- 프로그램마다 GetOpenFileName / IFileOpenDialog / WinUI FileOpenPicker 등 호출 방식이 달라 범용 후킹이 어려움

**대안(채택)**: 내 탐색기의 북마크를 추가할 때 **Windows 기본 즐겨찾기(Quick access/Home)에도 함께 등록**. 그러면 다른 프로그램의 기본 첨부창에서도 내가 등록한 폴더가 바로 보임. Windows 파일 선택창을 가로챌 필요 없음.

구현 방법 (셸 동사 사용):
```python
import win32com.client
sh = win32com.client.Dispatch("Shell.Application")
sh.Namespace(r"D:\점자").Self.InvokeVerb("pintohome")  # 즐겨찾기 추가
# 해제는 즐겨찾기 네임스페이스에서 해당 항목에 unpinfromhome 호출
```

### MyExplorer (메인 탐색기)

* Chrome식 탭 + 탭 고정
* WinSCP식 좌/우 2패널
* `Ctrl+C` 복사 / `Ctrl+X` 잘라내기 / `Ctrl+V` 붙여넣기
* 일반 Windows 탐색기와 동일한 기본 파일 조작 방식
* 드래그앤드롭
* ⭐ 북마크 + 북마크 폴더 (북마크 폴더 전체를 탭으로 한 번에 열기)
* 작업공간 저장 / 한 번에 열기
* 북마크 추가 시 Windows 즐겨찾기에도 자동 등록

### 파일 복사 / 이동

* 일반 Windows 탐색기처럼 `Ctrl+C / Ctrl+X / Ctrl+V`로 사용
* 폴더 복사 시 내부 파일을 최대 4개까지 병렬 처리
* 수백~수천 개의 작은 파일이 포함된 폴더는 여러 파일을 동시에 복사하여 처리 속도 향상
* 단일 대용량 파일은 일반적인 단일 파일 복사 방식으로 처리
* 복사/이동 중에도 MyExplorer를 계속 사용할 수 있도록 백그라운드 처리
* 파일 충돌 시 덮어쓰기 / 건너뛰기 / 이름 변경 등의 처리 지원


### MyPicker (파일 선택 전용, 필요시 별도 구현)
- ⭐ 북마크 표시 (MyExplorer와 데이터 공유: `bookmarks.json`/`bookmarks.db`)
- 폴더 이동, 파일 검색, 파일 선택
- 열기/취소 → 선택 결과를 호출 프로그램에 반환
- 단, 다른 프로그램이 이 창을 "자동으로" 호출하게 만들 공식적인 방법은 없음 → 위의 "Windows 즐겨찾기 동기화" 방식으로 대체 가능하면 MyPicker 자체는 우선순위 낮춰도 됨

### 확인 필요 사항
- Windows 11 Favorites(즐겨찾기) 저장 구조가 버전/업데이트에 따라 다를 수 있어, 실제 구현 시 최신 Windows 11 기준으로 동작 재확인 필요

### 기술 스택 제안
- Python + PySide6 (QFileSystemModel, QFileIconProvider, 탭/드래그 기본 제공) → PyInstaller exe

---

## 진행 순서 제안
1. **런처** 먼저 제작 (규모 작고 빠르게 1차 버전 사용 가능)
   - 여기서 만든 아이콘 렌더링 / 스크롤 / 트리 UI를 탐색기에서 재사용
2. 이후 **MyExplorer** 제작, 즐겨찾기 동기화 기능부터 검증
3. 필요성이 확인되면 MyPicker 별도 제작
