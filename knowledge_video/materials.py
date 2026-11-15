from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import requests


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())


def text_of(markup):
    parser = TextParser()
    parser.feed(markup)
    return " ".join(parser.parts)


def public_url(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname or p.username:
        raise ValueError("资料仅支持公开 HTTP(S) 网页")
    addresses = {
        ipaddress.ip_address(item[4][0])
        for item in socket.getaddrinfo(
            p.hostname, p.port or (443 if p.scheme == "https" else 80)
        )
    }
    # TUN proxies can return benchmark-range synthetic DNS addresses for public
    # domains. Verify those domains through HTTPS DNS; never allow private IPs.
    fake_range = ipaddress.ip_network("198.18.0.0/15")
    if addresses and all(a.version == 4 and a in fake_range for a in addresses):
        try:
            ipaddress.ip_address(p.hostname)
        except ValueError:
            pass
        else:
            raise ValueError("资料地址不能使用保留 IP")
        verified = []
        for kind in ("A", "AAAA"):
            response = requests.get(
                "https://dns.google/resolve",
                params={"name": p.hostname, "type": kind},
                timeout=(5, 12),
            )
            response.raise_for_status()
            answer = response.json()
            if answer.get("Status") != 0:
                raise ValueError("公开 DNS 无法验证资料域名")
            verified.extend(
                ipaddress.ip_address(a["data"])
                for a in answer.get("Answer", [])
                if a["type"] in (1, 28)
            )
        addresses = set(verified)
    if not addresses or any(not a.is_global for a in addresses):
        raise ValueError("资料地址不能指向本地网络")
    return url


def fetch_source(url):
    for _ in range(4):
        public_url(url)
        with requests.get(
            url,
            timeout=(8, 18),
            headers={
                "User-Agent": "KnowledgeVideoStudio/0.2 (+local educational research)"
            },
            allow_redirects=False,
            stream=True,
        ) as r:
            if r.is_redirect:
                url = urljoin(url, r.headers["Location"])
                continue
            r.raise_for_status()
            if not any(
                t in r.headers.get("content-type", "") for t in ("text/", "json", "xml")
            ):
                raise ValueError("当前资料抓取支持文本网页，不支持二进制文件")
            content = bytearray()
            for chunk in r.iter_content(32768):
                content.extend(chunk)
                if len(content) > 2_000_000:
                    raise ValueError("资料网页超过 2 MB")
            raw = content.decode(
                r.encoding if r.encoding and r.encoding != "ISO-8859-1" else "utf-8",
                errors="replace",
            )
            text = text_of(raw)
            if len(text) < 100:
                raise ValueError("网页未返回足够的正文")
            title = re.search(
                r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL
            )
            return {
                "url": url,
                "title": html.unescape(title.group(1)) if title else url,
                "text": text[:16000],
                "sha256": hashlib.sha256(content).hexdigest(),
            }
    raise ValueError("资料网页重定向过多")


class SlideParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.slides = []
        self.current = None
        self.depth = 0
        self.nested = False
        self.fragment_groups = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "section":
            if self.depth:
                self.nested = True
            if self.depth == 0:
                self.fragment_groups = set()
                self.current = {
                    "id": attrs.get("id")
                    or attrs.get("data-slide-id")
                    or f"slide_{len(self.slides) + 1}",
                    "text": "",
                    "visible": [],
                    "index": len(self.slides),
                    "fragments": 0,
                }
                self.slides.append(self.current)
            self.depth += 1
        if self.current:
            if "fragment" in attrs.get("class", "").split():
                group = attrs.get("data-fragment-index")
                if group is None or group not in self.fragment_groups:
                    self.current["fragments"] += 1
                if group is not None:
                    self.fragment_groups.add(group)
            for key in ("data-fragment", "data-item"):
                if attrs.get(key):
                    self.current["visible"].append(attrs[key])

    def handle_endtag(self, tag):
        if tag == "section":
            self.depth = max(0, self.depth - 1)
            if not self.depth:
                self.current = None

    def handle_data(self, data):
        if self.current:
            self.current["text"] += data.strip() + " "


def inspect_slides(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in (".html", ".htm"):
        raise ValueError("请选择存在的 HTML slides 文件")
    raw = path.read_text(encoding="utf-8")
    if len(raw) > 600000:
        raise ValueError("HTML 超过 600 KB，请将大资源移到独立文件")
    parser = SlideParser()
    parser.feed(raw)
    if parser.nested and "Reveal.initialize" in raw:
        raise ValueError("暂不支持 Reveal 纵向嵌套课件，请先整理为横向页面")
    if not parser.slides:
        raise ValueError("已有课件需要使用 section 分页，或提供 Reveal.js 课件")
    if len({s["id"] for s in parser.slides}) != len(parser.slides):
        raise ValueError("课件页面 id 重复，请使用唯一 id")
    if len(parser.slides) > 40:
        raise ValueError("当前单任务最多支持 40 页课件")
    return {
        "path": str(path),
        "html": raw,
        "slides": parser.slides,
        "custom": "setPresentationState" in raw,
        "reveal": "Reveal.initialize" in raw,
    }


RESOURCE = re.compile(
    r"(?P<a>\b(?:src|href)\s*=\s*[\"\'])(?P<u>[^\"\']+)(?P<z>[\"\'])|(?P<c>url\(\s*[\"\']?)(?P<v>[^)\"\']+)(?P<d>[\"\']?\s*\))",
    re.IGNORECASE,
)
ALLOWED = {
    ".css",
    ".js",
    ".mjs",
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".gif",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".ttc",
    ".eot",
}


def available_font_sources(raw, parent):
    """Keep working @font-face alternatives when an offline deck omits old formats."""

    def face(match):
        found = [False]

        def declaration(src):
            kept = []
            for choice in re.split(r",(?=\s*(?:url|local)\()", src.group(1)):
                url = re.search(r"url\(\s*[\"\']?([^\"\')]+)", choice, re.IGNORECASE)
                if url:
                    value = url.group(1)
                    parsed = urlparse(value)
                    if (
                        not parsed.scheme
                        and not value.startswith("//")
                        and not (parent / unquote(parsed.path)).is_file()
                    ):
                        continue
                kept.append(choice)
            found[0] |= bool(kept)
            return "src:" + ",".join(kept) + ";" if kept else ""

        result = re.sub(
            r"\bsrc\s*:\s*([^;]+);", declaration, match.group(0), flags=re.IGNORECASE
        )
        if not found[0]:
            raise ValueError("课件字体缺少可用文件")
        return result

    return re.sub(r"@font-face\s*\{[^}]+\}", face, raw, flags=re.IGNORECASE)


def bundle_html(source: Path, destination: Path):
    """Copy only referenced assets, never a user's whole parent directory."""
    source = source.expanduser().resolve()
    assets = destination.parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    seen: dict[Path, str] = {}
    budget = [0]

    def copy_asset(path):
        path = path.resolve()
        if path in seen:
            return seen[path]
        if path.suffix.lower() not in ALLOWED or not path.is_file():
            raise ValueError(f"找不到或不支持课件资源：{path.name}")
        budget[0] += path.stat().st_size
        if budget[0] > 80_000_000 or len(seen) > 300:
            raise ValueError("课件资源超过 80 MB 或 300 个文件")
        name = hashlib.sha256(str(path).encode()).hexdigest()[:16] + path.suffix
        seen[path] = name
        if path.suffix in (".css",):
            (assets / name).write_text(
                rewrite(
                    available_font_sources(path.read_text(), path.parent),
                    path.parent,
                    True,
                ),
                encoding="utf-8",
            )
        else:
            (assets / name).write_bytes(path.read_bytes())
        return name

    def rewrite(raw, parent, in_asset=False):
        def repl(m):
            value = m.group("u") or m.group("v")
            p = urlparse(value)
            if p.scheme or value.startswith(("#", "//")):
                return m.group(0)
            if not p.path:
                return m.group(0)
            ref = (parent / unquote(p.path)).resolve()
            if ref.suffix.lower() not in ALLOWED:
                return m.group(0)
            name = copy_asset(ref)
            new = ("" if in_asset else "assets/") + name
            if p.fragment:
                new += "#" + p.fragment
            return (m.group("a") or m.group("c")) + new + (m.group("z") or m.group("d"))

        return RESOURCE.sub(repl, raw)

    raw = rewrite(source.read_text(encoding="utf-8"), source.parent)
    destination.write_text(raw, encoding="utf-8")
    return raw
