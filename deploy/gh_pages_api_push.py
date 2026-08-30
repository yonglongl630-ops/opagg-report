#!/usr/bin/env python3
"""用 GitHub Git Data API 把 output/ 同步到 gh-pages 分支。

背景：本机 git 走本地代理时 TLS 不稳定（大文件上传经常被掐断），
而 curl 到 api.github.com 稳定，因此发布改用 REST API 直接建 blob/tree/commit/ref。

用法: python3 deploy/gh_pages_api_push.py
依赖: 钥匙串中 github.com 的凭据（git credential-osxkeychain）或环境变量 GITHUB_TOKEN。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
REPO = "yonglongl630-ops/opagg-report"
BRANCH = "gh-pages"
API = f"https://api.github.com/repos/{REPO}"


def _get_token() -> str:
    env = os.environ.get("GITHUB_TOKEN", "").strip()
    if env:
        return env
    try:
        p = subprocess.run(
            ["git", "credential-osxkeychain", "get"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in (p.stdout or "").splitlines():
            if line.startswith("password="):
                return line.split("=", 1)[1].strip()
    except Exception as e:  # noqa: BLE001
        print(f"读取钥匙串凭据失败: {e}")
    raise SystemExit("未找到 GitHub 凭据（钥匙串或 GITHUB_TOKEN）")


def _api(method: str, path: str, payload: dict | None = None, token: str = "", retries: int = 3) -> dict:
    url = API + path
    cmd = ["curl", "-sS", "--max-time", "300", "-w", "\n%{http_code}", "-X", method, "-H", f"Authorization: Bearer {token}",
           "-H", "Accept: application/vnd.github+json"]
    body_file = None
    if payload is not None:
        # 大 blob 的 base64 可能超过命令行参数上限，写临时文件用 -d @file 提交
        import tempfile
        fd, body_file = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        cmd += ["-H", "Content-Type: application/json", "-d", f"@{body_file}"]
    cmd += [url]
    last = ""
    try:
        for i in range(retries):
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            out_raw = (p.stdout or "").strip()
            parts = out_raw.rsplit("\n", 1)
            code = parts[-1].strip() if parts else ""
            out = parts[0] if len(parts) > 1 else out_raw
            if p.returncode == 0 and code in ("200", "201") and out:
                try:
                    return json.loads(out)
                except json.JSONDecodeError:
                    pass
            last = f"HTTP {code}: {out[:400]}" if out else (p.stderr or "")[-200:]
            time.sleep(3 * (i + 1))
    finally:
        if body_file:
            try:
                os.unlink(body_file)
            except OSError:
                pass
    raise RuntimeError(f"API {method} {path} 失败: {last[:300]}")


def collect_files() -> list[tuple[str, str]]:
    """返回 [(相对路径, 绝对路径)]，排除 preview_*.png 与临时文件。"""
    out = []
    if not os.path.isdir(OUTPUT_DIR):
        raise SystemExit(f"output 目录不存在: {OUTPUT_DIR}")
    for name in sorted(os.listdir(OUTPUT_DIR)):
        if name.startswith("preview_") or name.startswith("."):
            continue
        full = os.path.join(OUTPUT_DIR, name)
        if os.path.isfile(full):
            out.append((name, full))
    out.append((".nojekyll", ""))  # 空文件，保持 Pages 不渲染 Jekyll
    return out


def main() -> int:
    token = _get_token()
    files = collect_files()
    print(f"待上传 {len(files)} 个文件（{REPO} {BRANCH}）")

    # 1) 当前 gh-pages HEAD
    ref = _api("GET", f"/git/ref/heads/{BRANCH}", token=token)
    head_sha = ref.get("object", {}).get("sha", "")
    print(f"当前 HEAD: {head_sha}")

    # 2) 逐个上传 blob
    tree = []
    for path, full in files:
        if full:
            with open(full, "rb") as f:
                content = base64.b64encode(f.read()).decode()
        else:
            content = ""
        blob = _api("POST", "/git/blobs", {"content": content, "encoding": "base64"}, token=token)
        tree.append({"path": path, "mode": "100644", "type": "blob", "sha": blob.get("sha", "")})
        print(f"  blob ok: {path} ({len(content) // 1024}KB)")

    # 3) 重建整棵树（base_tree 缺省=空根，旧文件自动剔除）
    t = _api("POST", "/git/trees", {"tree": tree}, token=token)
    tree_sha = t.get("sha", "")
    print(f"tree ok: {tree_sha}")

    # 4) 提交
    msg = f"日报更新 {time.strftime('%Y-%m-%d %H:%M')}"
    c = _api("POST", "/git/commits", {"message": msg, "tree": tree_sha, "parents": [head_sha]}, token=token)
    commit_sha = c.get("sha", "")
    print(f"commit ok: {commit_sha}")

    # 5) 更新分支
    _api("PATCH", f"/git/refs/heads/{BRANCH}", {"sha": commit_sha, "force": True}, token=token)
    print(f"已发布 {commit_sha} -> {BRANCH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
