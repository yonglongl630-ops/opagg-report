"""HTTP 与文本基础工具：会话、重试、编码、HTML 清洗、原子写文件。"""

from __future__ import annotations

import gzip
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import http.client
from typing import Any, Dict, Iterable, List, Optional

UA_PC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

log = logging.getLogger("opagg")


class Session:
    """带 Cookie 管理、重试、编码探测的 HTTP 会话（仅用标准库）。"""

    def __init__(self, ua: str = UA_PC, timeout: int = 15, retries: int = 2):
        self.ua = ua
        self.timeout = timeout
        self.retries = retries
        self.cookies: Dict[str, str] = {}
        self._opener = urllib.request.build_opener()

    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def absorb(self, resp: Any) -> None:
        for h in resp.headers.get_all("Set-Cookie") or []:
            m = re.match(r"\s*([^=]+)=([^;]*)", h)
            if m:
                self.cookies[m.group(1).strip()] = m.group(2).strip()

    def set_cookie_str(self, raw: str) -> None:
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                self.cookies[k.strip()] = v.strip()

    def request(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
        use_http: bool = False,
        data: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        binary: bool = False,
    ) -> Optional[bytes]:
        if params:
            url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        final_url = url.replace("https://", "http://") if use_http else url
        hdrs = {"User-Agent": self.ua}
        if self.cookies:
            hdrs["Cookie"] = self.cookie_header()
        if referer:
            hdrs["Referer"] = referer
        if headers:
            hdrs.update(headers)
        body = None
        if data:
            body = urllib.parse.urlencode(data).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        last_err: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(final_url, headers=hdrs, data=body)
                resp = self._opener.open(req, timeout=self.timeout)
                self.absorb(resp)
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
            # Python 3.9 中 socket.timeout / RemoteDisconnected 并非 TimeoutError 子类，用 OSError 兜底；
            # IncompleteRead 等 http.client.HTTPException 也一并捕获
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, http.client.HTTPException) as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.8 * (attempt + 1))
        log.warning("请求失败 %s: %s", final_url[:120], last_err)
        return None

    def get_text(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
        use_http: bool = False,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        raw = self.request(url, headers=headers, referer=referer, use_http=use_http, params=params)
        if raw is None:
            return None
        return decode_text(raw)

    def get_json(
        self,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        text = self.get_text(url, headers=headers, referer=referer, params=params)
        if text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试剥离 JSONP 包装
            m = re.search(r"^[^(]*\((.*)\)\s*;?\s*$", text, re.S)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
            log.warning("JSON 解析失败: %s", url[:120])
            return None

    def post_json(
        self,
        url: str,
        data: Dict[str, Any],
        *,
        headers: Optional[Dict[str, str]] = None,
        referer: Optional[str] = None,
    ) -> Optional[Any]:
        body = json.dumps(data).encode()
        hdrs = {"Content-Type": "application/json", "User-Agent": self.ua}
        if referer:
            hdrs["Referer"] = referer
        if headers:
            hdrs.update(headers)
        if self.cookies:
            hdrs["Cookie"] = self.cookie_header()
        last_err: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                req = urllib.request.Request(url, headers=hdrs, data=body, method="POST")
                resp = self._opener.open(req, timeout=self.timeout)
                self.absorb(resp)
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(decode_text(raw))
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, http.client.HTTPException) as e:
                last_err = e
                if attempt < self.retries:
                    time.sleep(0.8 * (attempt + 1))
        log.warning("POST 失败 %s: %s", url[:120], last_err)
        return None


def decode_text(raw: bytes) -> str:
    for enc in ("utf-8", "gbk", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")


TAG_RE = re.compile(r"<[^>]+>")


def strip_tags(text: str) -> str:
    return TAG_RE.sub("", text or "")


def clean_text(text: str, max_len: int = 600) -> str:
    """去掉 HTML 标签、控制字符，压缩空白，截断。"""
    if not text:
        return ""
    s = strip_tags(text)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > max_len:
        s = s[:max_len] + "…"
    return s


def atomic_write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp, path)


def load_json(path: str, default: Any = None) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path: str, obj: Any) -> None:
    atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=1))


def uniq_by(items: Iterable[Dict[str, Any]], key: str = "url") -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for it in items:
        k = it.get(key) or ""
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def now_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")
