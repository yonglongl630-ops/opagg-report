"""日报预览 + 「立即刷新」服务（本地 / 局域网 / 云端）。

用法：
  python3 -m src.serve [--port 8651] [--open]             # 仅本机
  python3 -m src.serve --lan                               # 绑定 0.0.0.0，手机同 WiFi 可访问
  python3 -m src.serve --cloud --port 8000                 # 云端部署（Docker/Render 等）

功能：
- 以 http://<host>:<port> 提供 output/ 下的日报
- POST /api/refresh?source=all|sector|ths|cls|...  → 后台重采集并重新生成日报
- GET  /api/status                                  → 刷新状态（页面轮询用）
- POST /api/publish                                  → 把最新日报发布到 GitHub Pages

日报页面里的「立即刷新」按钮通过本服务实现；手机端用同一来源访问
（http://<电脑局域网IP>:<port> 或云端 https 域名）即可同源刷新。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
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
_token = os.environ.get("OPAGG_TOKEN", "") or ""
_lock = threading.Lock()
_state: Dict = {"running": False, "source": "", "date": "", "started": "", "finished": "", "error": "", "result": {}}
_publish_state: Dict = {"running": False, "started": "", "finished": "", "error": "", "output": ""}


def _lan_ip() -> str:
    """探测本机局域网 IPv4：优先 192.168/10/172.16-31 私网段，排除 VPN/虚拟网卡地址。"""
    import re
    candidates = []
    for iface in ("en0", "en1"):
        try:
            out = subprocess.run(
                ["ipconfig", "getifaddr", iface],
                capture_output=True, text=True, timeout=3,
            )
            ip = (out.stdout or "").strip()
            if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", ip):
                candidates.append(ip)
        except Exception:  # noqa: BLE001
            continue
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", ip):
                candidates.append(ip)
    except OSError:
        pass
    if candidates:
        return candidates[0]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


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


def _start_refresh(source: str, date: str = "") -> None:
    with _lock:
        if _state.get("running"):
            return
        _state.update({
            "running": True,
            "source": source or "all",
            "date": date or default_date(),
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished": "",
            "error": "",
            "result": {},
        })

    def worker() -> None:
        # 采集放在独立子进程执行并设硬超时：即使某个网络请求挂起，也能自动终止并报错，
        # 避免「立即刷新」卡死无法再次刷新。
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sources = None
        if source and source != "all":
            sources = [s for s in source.split(",") if s.strip()]
        code = (
            "import json,sys;"
            "sys.path.insert(0,'.');"
            "from src.aggregate import run_day, default_date;"
            "from src.config import load_config;"
            "cfg=load_config();"
            f"r=run_day(cfg, {date!r} or default_date(), sources={sources!r}, use_cache=False);"
            "print(json.dumps({'html': r.get('_html_path',''), 'date': r.get('date',''), "
            "'sources': {k: {'status': v.get('status'), 'count': v.get('count')} "
            "for k, v in (r.get('sources') or {}).items()}}, ensure_ascii=False))"
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=900,
                cwd=root,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "")[-800:]
                raise RuntimeError(f"采集失败(exit {proc.returncode}): {detail}")
            lines = [ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()]
            if not lines:
                raise RuntimeError("采集无输出")
            with _lock:
                _state["result"] = json.loads(lines[-1])
        except subprocess.TimeoutExpired:
            with _lock:
                _state["error"] = "刷新超时（>15 分钟），已自动终止，请稍后重试"
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

    def _check_token(self) -> bool:
        if not _token:
            return True
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        return (qs.get("token") or [""])[0] == _token

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        # 允许公开 HTTPS 页面（GitHub Pages）访问本机 127.0.0.1 服务（Chrome Private Network Access）
        self.send_header("Access-Control-Allow-Private-Network", "true")

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
        if parsed.path == "/tunnel-url":
            # 返回当前 cloudflared 公网地址（供局域网内查看）
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tunnel_url.txt"), encoding="utf-8") as f:
                    url = f.read().strip()
            except OSError:
                url = ""
            self._send_json(200, {"url": url, "report": (url + "/report_%s.html" % default_date()) if url else ""})
            return
        if parsed.path == "/api/publish":
            if not self._check_token():
                self._send_json(403, {"ok": False, "error": "token 无效"})
                return
            with _lock:
                busy = _publish_state.get("running")
            if busy:
                self._send_json(200, {"ok": False, "error": "已有发布任务进行中"})
                return
            _start_publish()
            self._send_json(200, {"ok": True, "message": "发布已开始，稍后查看 /api/publish-status"})
            return
        if parsed.path == "/api/refresh":
            if not self._check_token():
                self._send_json(403, {"ok": False, "error": "token 无效"})
                return
            qs = urllib.parse.parse_qs(parsed.query)
            source = (qs.get("source") or ["all"])[0]
            date = (qs.get("date") or [""])[0]
            with _lock:
                busy = _state.get("running")
            if busy:
                self._send_json(200, {"ok": False, "error": "已有刷新任务进行中"})
                return
            _start_refresh(source, date)
            self._send_json(200, {"ok": True, "source": source, "date": date or default_date()})
            return
        # 静态文件：根路径默认 index.html（与在线首页一致），无 index 时回退当日日报
        rel = urllib.parse.unquote(parsed.path.lstrip("/"))
        if not rel or rel.endswith("/"):
            rel = "index.html" if os.path.exists(os.path.join(OUTPUT_DIR, "index.html")) else "report_%s.html" % default_date()
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
    ap.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    ap.add_argument("--lan", action="store_true", help="绑定 0.0.0.0，手机同局域网可访问")
    ap.add_argument("--cloud", action="store_true", help="云端模式：绑定 0.0.0.0，token 取 OPAGG_TOKEN")
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()
    host = args.host
    if args.lan or args.cloud:
        host = "0.0.0.0"
    port = args.port if not args.cloud else (args.port if args.port != PORT else 8000)
    global _token
    if args.cloud and not _token:
        print("提示：未设置 OPAGG_TOKEN，任何能访问该端口的人都可以触发刷新（云端建议设置 OPAGG_TOKEN）")
    try:
        # 幂等：端口已被占用说明服务已在运行（可能是开机自启实例），直接退出
        probe = socket.create_connection(("127.0.0.1", port), timeout=1)
        probe.close()
        print("刷新服务已在运行（端口 %d），无需重复启动。" % port)
        return 0
    except OSError:
        pass
    try:
        from src.aggregate import default_date
        index = os.path.join(OUTPUT_DIR, "index.html")
        if not os.path.exists(index):
            index = os.path.join(OUTPUT_DIR, f"report_{default_date()}.html")
        base = "http://127.0.0.1:%d" % port
        if host == "0.0.0.0":
            base = "http://%s:%d" % (_lan_ip(), port)
        name = os.path.basename(index) if os.path.exists(index) else ""
        print("日报预览(本机): http://127.0.0.1:%d/%s" % (port, name))
        if host == "0.0.0.0":
            print("手机端(同WiFi/云端): %s/%s" % (base, name))
            if base.startswith("http://127.0.0.1"):
                print("提示：未能自动识别局域网 IP，请在终端运行 ipconfig getifaddr en0 获取本机 IP，"
                      "手机打开 http://<该IP>:%d/%s" % (port, name))
        print("刷新接口: POST %s/api/refresh?source=all|sector|ths|cls" % base)
        print("发布接口: POST %s/api/publish   （生成日报 → 推送到 GitHub Pages）" % base)
        if args.open:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}/{name}")
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
