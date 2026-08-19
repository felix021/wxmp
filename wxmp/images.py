"""正文图片处理：收集、下载、归一化（转码压缩）、上传、替换 src。"""

from __future__ import annotations

import base64
import io
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageOps

from wxmp.errors import ImageError

MAX_DOWNLOAD = 20 * 1024 * 1024
CONTENT_IMG_LIMIT = 1024 * 1024  # 微信正文图片 1MB
JPEG_QUALITY_LADDER = (85, 75, 65, 55)


def make_download_session(download_proxy: str = "env") -> requests.Session:
    s = requests.Session()
    if download_proxy == "env":
        return s  # 默认 trust_env=True，跟随环境变量代理（外链可达性优先）
    s.trust_env = False
    if download_proxy.startswith(("http://", "https://", "socks5://")):
        s.proxies = {"http": download_proxy, "https": download_proxy}
    return s


@dataclass
class ImgRef:
    tag: Tag
    src: str
    kind: str  # local | remote | weixin | data
    path: Path | None = None  # local 时为解析后的绝对路径


def collect_images(soup: BeautifulSoup, base_dir: Path) -> list[ImgRef]:
    refs = []
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        if src.startswith("data:image/"):
            refs.append(ImgRef(img, src, "data"))
        elif src.startswith(("http://", "https://")):
            host = (urlparse(src).hostname or "").lower()
            if host == "mmbiz.qpic.cn" or host.endswith(".mmbiz.qpic.cn"):
                refs.append(ImgRef(img, src, "weixin"))
            else:
                refs.append(ImgRef(img, src, "remote"))
        else:
            p = Path(src).expanduser()
            if not p.is_absolute():
                p = (base_dir / p).resolve()
            refs.append(ImgRef(img, src, "local", path=p))
    return refs


def download_remote(url: str, session: requests.Session) -> bytes:
    try:
        resp = session.get(url, timeout=(5, 30), stream=True)
    except requests.RequestException as e:
        raise ImageError(f"图片下载失败 {url}: {e}") from e
    if resp.status_code != 200:
        raise ImageError(f"图片下载失败 HTTP {resp.status_code}: {url}")
    chunks, size = [], 0
    for chunk in resp.iter_content(64 * 1024):
        size += len(chunk)
        if size > MAX_DOWNLOAD:
            raise ImageError(f"图片超过 {MAX_DOWNLOAD // (1024 * 1024)}MB 上限: {url}")
        chunks.append(chunk)
    return b"".join(chunks)


def decode_data_uri(uri: str) -> bytes:
    m = re.match(r"data:image/[\w.+-]+;base64,(.*)", uri, re.S)
    if not m:
        raise ImageError("无法解析 data: URI 图片（仅支持 base64 格式）")
    try:
        return base64.b64decode(m.group(1))
    except Exception as e:
        raise ImageError(f"data: URI base64 解码失败: {e}") from e


def normalize_image(data: bytes, label: str, *, max_width: int,
                    limit: int = CONTENT_IMG_LIMIT) -> tuple[bytes, str, list[str]]:
    """归一化为微信可接受的 jpg/png 且不超过 limit。返回 (payload, ext, notes)。"""
    notes: list[str] = []
    head = data[:512].lstrip()
    if head.startswith(b"<?xml") or b"<svg" in head[:256]:
        raise ImageError(f"不支持 SVG 图片 {label}，请先转为 PNG/JPG")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ImageError(f"无法解析图片 {label}: {e}") from e

    fmt = (img.format or "").lower()
    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    # 本来就是合规的 jpg/png 且不用缩放 → 原样返回（保画质、最快）
    if fmt in ("jpeg", "png") and img.width <= max_width and len(data) <= limit:
        return data, "jpg" if fmt == "jpeg" else "png", notes

    if fmt == "gif":
        notes.append("动图仅取首帧")
    if fmt not in ("jpeg", "png"):
        notes.append(f"{fmt}→{'png' if has_alpha else 'jpg'}")

    img = ImageOps.exif_transpose(img)  # 纠正手机照片方向，同时丢弃 EXIF
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, max(1, round(img.height * ratio))), Image.LANCZOS)

    if has_alpha:
        payload, ext = _encode_png(img)
        if payload and len(payload) <= limit:
            return payload, ext, notes
        # PNG 压不下去：调色板量化
        quant = img.convert("RGB").quantize(colors=256)
        buf = io.BytesIO()
        quant.save(buf, "PNG", optimize=True)
        if buf.tell() <= limit:
            notes.append("已量化 256 色")
            return buf.getvalue(), "png", notes
        # 仍超限：白底合成转 JPEG（丢透明度）
        notes.append("透明度丢失(转白底jpg)")
        payload, ext = _encode_jpeg(img, limit, label)
        return payload, ext, notes
    payload, ext = _encode_jpeg(img, limit, label)
    return payload, ext, notes


def _encode_png(img: Image.Image) -> tuple[bytes, str]:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue(), "png"


def _encode_jpeg(img: Image.Image, limit: int, label: str) -> tuple[bytes, str]:
    if img.mode not in ("RGB", "L"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg.paste(img, mask=img.convert("RGBA").split()[-1])
        else:
            bg.paste(img)
        img = bg
    for q in JPEG_QUALITY_LADDER:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= limit:
            return buf.getvalue(), "jpg"
    raise ImageError(
        f"图片压缩后仍超过 {limit // 1024}KB: {label}（原始 {img.width}x{img.height}，"
        f"已尝试最低质量 {JPEG_QUALITY_LADDER[-1]}，请手动裁剪或降低分辨率）"
    )


def human(n: int) -> str:
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f}MB"
    if n >= 1024:
        return f"{n / 1024:.0f}KB"
    return f"{n}B"


def process_all(soup: BeautifulSoup, base_dir: Path, client, *,
                max_width: int = 1080,
                download_proxy: str = "env") -> tuple[list[str], list[dict]]:
    """处理正文图片。client=None 为离线模式（不上传）。

    返回 (日志行列表, 已上传图片列表)；
    已上传项: {"src": 原src, "url": mmbiz url, "payload": 归一化后字节, "ext": 后缀}
    """
    logs: list[str] = []
    uploaded: list[dict] = []
    refs = collect_images(soup, base_dir)
    n_weixin = sum(1 for r in refs if r.kind == "weixin")
    if n_weixin:
        logs.append(f"已是微信图片跳过 {n_weixin} 张")
    todo = [r for r in refs if r.kind != "weixin"]
    if not todo:
        return logs, uploaded
    if client is None:
        logs.append(f"[离线] 待上传正文图片 {len(todo)} 张")
        return logs, uploaded

    dl = make_download_session(download_proxy)
    for i, r in enumerate(todo, 1):
        label = r.src if r.kind != "local" else str(r.path)
        if r.kind == "local":
            if not r.path or not r.path.is_file():
                raise ImageError(f"图片文件不存在: {r.path or r.src}")
            data = r.path.read_bytes()
        elif r.kind == "remote":
            data = download_remote(r.src, dl)
        else:
            data = decode_data_uri(r.src)
        payload, ext, notes = normalize_image(data, label, max_width=max_width)
        url = client.upload_content_image(payload, f"image.{ext}")
        r.tag["src"] = url
        uploaded.append({"src": r.src, "url": url, "payload": payload, "ext": ext})
        extra = f", {', '.join(notes)}" if notes else ""
        logs.append(f"[{i}/{len(todo)}] {label} → OK "
                    f"({human(len(data))}→{human(len(payload))}{extra})")
    return logs, uploaded
