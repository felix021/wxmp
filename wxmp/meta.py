"""文章元数据：front-matter / CLI / 配置合并与校验。"""

from __future__ import annotations

from dataclasses import dataclass

from wxmp.config import Config
from wxmp.errors import ValidationError

TITLE_MAX = 32
AUTHOR_MAX = 16
DIGEST_MAX = 120
CONTENT_CHAR_MAX = 20000
CONTENT_WARN = 18000
CONTENT_BYTES_MAX = 1024 * 1024


@dataclass
class ArticleMeta:
    title: str = ""
    author: str = ""
    digest: str = ""
    cover: str = ""  # 本地图片路径（相对文章文件解析）
    theme: str = ""
    code_style: str = ""
    content_source_url: str = ""
    need_open_comment: int | None = None
    only_fans_can_comment: int | None = None
    no_digest: bool = False  # True = digest 留空，交给微信取正文前 54 字


def _pick(cli: dict, fm: dict, key: str, default=""):
    v = cli.get(key)
    if v in (None, ""):
        v = fm.get(key)
    if v in (None, ""):
        v = default
    return v


def _as_int(v) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def resolve_meta(fm: dict, cli: dict, cfg: Config, fallback_title: str = "") -> ArticleMeta:
    return ArticleMeta(
        title=_pick(cli, fm, "title") or fallback_title,
        author=_pick(cli, fm, "author"),
        digest=_pick(cli, fm, "digest"),
        cover=_pick(cli, fm, "cover"),
        theme=_pick(cli, fm, "theme", cfg.default_theme),
        code_style=_pick(cli, fm, "code_style", cfg.default_code_style),
        content_source_url=_pick(cli, fm, "content_source_url"),
        need_open_comment=_as_int(cli.get("need_open_comment", fm.get("need_open_comment"))),
        only_fans_can_comment=_as_int(cli.get("only_fans_can_comment", fm.get("only_fans_can_comment"))),
        no_digest=bool(cli.get("no_digest")),
    )


def validate(meta: ArticleMeta, content_html: str) -> list[str]:
    """校验微信字段限制；硬错误抛 ValidationError，软问题返回警告列表。"""
    warnings: list[str] = []
    if not meta.title:
        raise ValidationError("缺少标题：请在 front-matter 写 title，或用 --title 指定")
    if len(meta.title) > TITLE_MAX:
        raise ValidationError(f"标题 {len(meta.title)} 字，超过微信上限 {TITLE_MAX} 字: {meta.title!r}")
    if len(meta.author) > AUTHOR_MAX:
        raise ValidationError(f"作者名 {len(meta.author)} 字，超过微信上限 {AUTHOR_MAX} 字")
    if len(meta.digest) > DIGEST_MAX:
        raise ValidationError(f"摘要 {len(meta.digest)} 字，超过微信上限 {DIGEST_MAX} 字")
    n_chars = len(content_html)
    if n_chars > CONTENT_CHAR_MAX:
        raise ValidationError(
            f"正文 {n_chars} 字符，超过微信上限 {CONTENT_CHAR_MAX}（内联样式会膨胀体积），请拆篇或精简"
        )
    if n_chars > CONTENT_WARN:
        warnings.append(f"正文 {n_chars} 字符，接近微信上限 {CONTENT_CHAR_MAX}，注意预留余量")
    n_bytes = len(content_html.encode("utf-8"))
    if n_bytes > CONTENT_BYTES_MAX:
        raise ValidationError(f"正文 {n_bytes} 字节，超过微信上限 1MB")
    return warnings


def to_draft_article(meta: ArticleMeta, content_html: str, thumb_media_id: str) -> dict:
    article = {
        "title": meta.title,
        "content": content_html,
        "thumb_media_id": thumb_media_id,
    }
    if meta.author:
        article["author"] = meta.author
    if meta.digest:
        article["digest"] = meta.digest
    if meta.content_source_url:
        article["content_source_url"] = meta.content_source_url
    if meta.need_open_comment is not None:
        article["need_open_comment"] = meta.need_open_comment
    if meta.only_fans_can_comment is not None:
        article["only_fans_can_comment"] = meta.only_fans_can_comment
    return article
