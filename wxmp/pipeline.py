"""构建编排：push 与 preview 共用同一条管线，保证预览即所得。"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup

from wxmp import images, render, themes
from wxmp.config import Config
from wxmp.errors import ImageError, ValidationError
from wxmp.meta import ArticleMeta, resolve_meta, validate
from wxmp.render import make_digest

MATERIALS_CACHE = Path("~/.cache/wxmp/materials.json").expanduser()


@dataclass
class BuiltArticle:
    meta: ArticleMeta
    content_html: str  # 最终 content：图片已换 mmbiz、样式已内联、已净化
    theme_name: str = ""
    warnings: list[str] = field(default_factory=list)
    report: list[str] = field(default_factory=list)  # 过程日志
    uploaded_images: list[dict] = field(default_factory=list)
    thumb_media_id: str = ""


def build_article(path: Path, opts: dict, cfg: Config, client=None) -> BuiltArticle:
    """文件 → (meta, 最终 content)。

    client=None 为离线模式（preview / --dry-run）：不上传图片，src 保持原样。
    """
    text = path.read_text(encoding="utf-8")
    report: list[str] = []
    warnings: list[str] = []

    is_md = path.suffix.lower() in (".md", ".markdown", ".mdown")
    if is_md:
        fm, body = render.extract_front_matter(text)
        code_style = opts.get("code_style") or fm.get("code_style") or cfg.default_code_style
        html_frag = render.render_markdown(body, code_style)
    else:
        fm = {}
        html_frag = render.parse_user_html(text)

    soup = BeautifulSoup(html_frag, "html.parser")
    logs, uploaded = images.process_all(
        soup, path.parent, client,
        max_width=cfg.image_max_width, download_proxy=cfg.download_proxy,
    )
    report.extend(logs)

    theme_name = opts.get("theme") or fm.get("theme") or cfg.default_theme
    resolved_theme, css = themes.load_theme(theme_name)
    html_final = render.apply_theme(str(soup), css, on_warning=warnings.append)
    report.extend(f"主题警告: {w}" for w in warnings)

    fallback_title = ""
    h1 = BeautifulSoup(html_final, "html.parser").find("h1")
    if h1:
        fallback_title = h1.get_text(strip=True)

    meta = resolve_meta(fm, opts, cfg, fallback_title=fallback_title)
    warnings.extend(validate(meta, html_final))
    if not meta.digest and not meta.no_digest:
        meta.digest = make_digest(html_final)

    return BuiltArticle(
        meta=meta, content_html=html_final, theme_name=resolved_theme,
        warnings=warnings, report=report, uploaded_images=uploaded,
    )


def upload_cover(client, cover: str, article_dir: Path) -> str:
    """上传封面为永久素材，sha256 缓存避免重复上传占素材库额度。"""
    p = Path(cover).expanduser()
    if not p.is_absolute():
        p = article_dir / p
    if not p.is_file():
        raise ImageError(f"封面图片不存在: {p}")
    raw = p.read_bytes()
    key = hashlib.sha256(raw).hexdigest()

    cache: dict = {}
    try:
        cache = json.loads(MATERIALS_CACHE.read_text(encoding="utf-8"))
        if key in cache:
            return cache[key]["media_id"]
    except (OSError, ValueError):
        pass

    payload, ext, notes = images.normalize_image(
        raw, str(p), max_width=5000, limit=10 * 1024 * 1024
    )
    media_id, url = client.add_material(payload, f"cover.{ext}")
    try:
        MATERIALS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        cache[key] = {"media_id": media_id, "url": url, "name": p.name}
        tmp = MATERIALS_CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        os.chmod(tmp, 0o600)
        tmp.replace(MATERIALS_CACHE)
    except OSError:
        pass
    return media_id


def ensure_thumb(client, built: BuiltArticle, article_dir: Path,
                 report: list[str]) -> str:
    """封面优先 front-matter/CLI；缺省时用正文第一张图；都没有则报错。"""
    if built.meta.cover:
        report.append(f"封面上传: {built.meta.cover}")
        return upload_cover(client, built.meta.cover, article_dir)
    if built.uploaded_images:
        first = built.uploaded_images[0]
        report.append(f"未指定封面，使用正文第一张图: {first['src']}")
        media_id, _ = client.add_material(first["payload"], f"cover.{first['ext']}")
        return media_id
    raise ValidationError(
        "微信草稿必须有封面：请在 front-matter 写 cover（本地图片路径）或用 --cover 指定；"
        "正文若无图片则必须显式给封面"
    )
