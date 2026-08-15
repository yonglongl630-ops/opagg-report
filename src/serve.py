"""本地预览 + 「立即刷新」服务。

用法：
  python3 -m src.serve [--port 8651] [--open]

功能：
- 以 http://127.0.0.1:8651 提供 output/ 下的日报/周报
- POST /api/refresh?source=all|sector|ths|cls|...  → 后台重采集并重新生成日报
- GET  /api/status                                  → 刷新状态（页面轮询用）

日报页面里的「立即刷新」按钮通过本服务实现：停止定时任务后，
查看时手动点击即可拉取各平台实时数据。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.aggregate import OUTPUT_DIR, STATE_DIR, default_date, run_day  # noqa: E402
from src.config import load_config  # noqa: E402

PORT = 8651
_lock = threading.Lock()
_state: Dict = {"running": False, "source": "", "started": "", "finished": "", "error": "", "result": {}}
_publish_state: Dict = {"running": False, "started": "", "finished": "", "error": "", "output": ""}


def _start_publish() -> None:
    """后台执行 gh-pages 发布脚本（本地生成数据 → 推送到 GitHub Pages）。"""
    with _lock:
        if _publish_state.get("running"):
            return
        _publish_state.update({"running": True, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "finished": "", "error": "", "output": ""})

    script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deploy", "gh_pages_push.sh")

    def worker() -> None:
        try:
            proc = subprocess.run(["bash", script], capture_output=True, text=True, timeout=300)
            tail = (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:]
            with _lock:
                if proc.returncode != 0:
                    _publish_state["error"] = f"发布失败(exit {proc.returncode}): {tail[-500:]}"
                else:
                    _publish_state["output"] = tail[-500:]
        except Exception as e:  # noqa: BLE001
            with _lock:
                _publish_state["error"] = str(e)
        finally:
            with _lock:
                _publish_state["running"] = False
                _publish_state["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")

    threading.Thread(target=worker, daemon=True).start()


def _status_path() -> str:
    return os.path.join(STATE_DIR, "refresh_status.json")


def _start_refresh(source: str) -> None:
    with _lock:
        if _state.get("running"):
            return
        _state.update({
            "running": True,
            "source": source or "all",
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished": "",
            "error": "",
            "result": {},
        })

    def worker() -> None:
        try:
            cfg = load_config()
            sources = None
            if source and source != "all":
                sources = [s for s in source.split(",") if s.strip()]
            report = run_day(cfg, default_date(), sources=sources, use_cache=False)
            with _lock:
                _state["result"] = {
                    "html": report.get("_html_path", ""),
                    "date": report.get("date", ""),
                    "sources": {
                        k: {"status": v.get("status"), "count": v.get("count")}
                        for k, v in (report.get("sources") or {}).items()
                    },
                }
        except Exception as e:  # noqa: BLE001
            with _lock:
                _state["error"] = str(e)
        finally:
            with _lock:
                _state["running"] = False
                _state["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
            os.makedirs(STATE_DIR, exist_ok=True)
            try:
                with open(_status_path(), "w", encoding="utf-8") as f:
                    json.dump(dict(_state), f, ensure_ascii=False, indent=1)
            except OSError:
                pass

    threading.Thread(target=worker, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "OpAggRefresh/1.0"

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, code: int, obj: Dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/status":
            with _lock:
                self._send_json(200, dict(_state))
            return
        if parsed.path == "/api/publish-status":
            with _lock:
                self._send_json(200, dict(_publish_state))
            return
        if parsed.path == "/api/publish":
            with _lock:
                busy = _publish_state.get("running")
            if busy:
                self._send_json(200, {"ok": False, "error": "已有发布任务进行中"})
                return
            _start_publish()
            self._send_json(200, {"ok": True, "message": "发布已开始，稍后查看 /api/publish-status"})
            return
        if parsed.path == "/api/refresh":
            qs = urllib.parse.parse_qs(parsed.query)
            source = (qs.get("source") or ["all"])[0]
            with _lock:
                busy = _state.get("running")
            if busy:
                self._send_json(200, {"ok": False, "error": "已有刷新任务进行中"})
                return
            _start_refresh(source)
            self._send_json(200, {"ok": True, "source": source})
            return
        # 静态文件
        rel = urllib.parse.unquote(parsed.path.lstrip("/")) or "report_%s.html" % default_date()
        if not rel or rel.endswith("/"):
            rel += "report_%s.html" % default_date()
        safe = os.path.normpath(os.path.join(OUTPUT_DIR, rel))
        if not safe.startswith(os.path.abspath(OUTPUT_DIR)):
            self._send_json(403, {"error": "forbidden"})
            return
        if not os.path.isfile(safe):
            self._send_json(404, {"error": "not found", "path": rel})
            return
        with open(safe, "rb") as f:
            body = f.read()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(os.path.splitext(safe)[1].lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        self.do_GET()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        print("[serve]", time.strftime("%H:%M:%S"), fmt % args)


def main() -> int:
    ap = argparse.ArgumentParser(description="日报预览 + 立即刷新服务")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()
    try:
        from src.aggregate import default_date
        index = os.path.join(OUTPUT_DIR, f"report_{default_date()}.html")
        print("日报预览: http://127.0.0.1:%d/%s" % (args.port, os.path.basename(index) if os.path.exists(index) else "output/"))
        print("刷新接口: POST http://127.0.0.1:%d/api/refresh?source=all|sector|ths|cls" % args.port)
        print("发布接口: POST http://127.0.0.1:%d/api/publish   （本地生成日报 → 推送到 GitHub Pages）" % args.port)
        if args.open:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{args.port}/{os.path.basename(index)}")
        ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
