"""updater.py 오프라인 테스트: 가짜 GitHub(로컬 HTTP 서버)로 조회/다운로드/해시 검증을 확인.  python test_updater.py"""
import hashlib
import http.server
import json
import threading

import updater as U

PAYLOAD = b"fake-installer-bytes" * 5000
GOOD = hashlib.sha256(PAYLOAD).hexdigest()
state = {"sha": GOOD, "tag": "v9.9.9", "with_sha_asset": True}


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}/dl/"
        if self.path == "/api":
            assets = [{"name": "JYTools-Setup-9.9.9.exe", "browser_download_url": base + "JYTools-Setup-9.9.9.exe"}]
            if state["with_sha_asset"]:
                assets.append({"name": "JYTools-Setup-9.9.9.exe.sha256", "browser_download_url": base + "JYTools-Setup-9.9.9.exe.sha256"})
            body = json.dumps({"tag_name": state["tag"], "body": "notes", "assets": assets}).encode()
        elif self.path.endswith(".sha256"):
            body = (state["sha"] + "  JYTools-Setup-9.9.9.exe\n").encode()
        else:
            body = PAYLOAD
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
U.RELEASES_API = f"http://127.0.0.1:{srv.server_port}/api"
U.ALLOWED_PREFIX = f"http://127.0.0.1:{srv.server_port}/dl/"

assert U.parse_version("v0.10.1") == (0, 10, 1) and U.is_newer("0.10.0", "0.9.9") and not U.is_newer("0.1.0", "0.1.0")

info = U.fetch_latest()
assert info and info["version"] == "9.9.9", info
seen = []
p = U.download_verified(info, seen.append)
assert p.read_bytes() == PAYLOAD and seen and seen[-1] == 100

state["sha"] = "0" * 64                                   # 해시 불일치 → 거부 + 파일 삭제
try:
    U.download_verified(info)
    raise SystemExit("FAIL: 해시 불일치를 통과시킴")
except ValueError:
    assert not p.exists()

state["tag"] = "v0.0.1"                                    # 현재보다 낮으면 None
assert U.fetch_latest() is None
state.update(tag="v9.9.9", with_sha_asset=False)           # 해시 파일 없는 릴리스는 무시
assert U.fetch_latest() is None
state["with_sha_asset"] = True
U.ALLOWED_PREFIX = "https://github.com/x/y/releases/download/"   # 허용 주소가 아니면 무시
assert U.fetch_latest() is None
print("updater tests OK")
