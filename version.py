"""버전/저장소 정보 (단일 출처). 빌드 스크립트, 설치 파일(.iss), 업데이트 확인이 모두 이 값을 읽는다.
새 버전을 낼 때는 __version__ 만 올리고 태그 v<__version__> 로 릴리스한다."""

__version__ = "0.1.5"

GITHUB_OWNER = "lovslave-netizen"
GITHUB_REPO = "JYLauncher_Explorer"
RELEASES_API = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
