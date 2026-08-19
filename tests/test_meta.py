import pytest

from wxmp.config import Config
from wxmp.errors import ValidationError
from wxmp.meta import resolve_meta, to_draft_article, validate


def test_priority_cli_over_frontmatter():
    m = resolve_meta({"title": "fm", "author": "a"}, {"title": "cli"}, Config())
    assert m.title == "cli"
    m2 = resolve_meta({"title": "fm"}, {}, Config())
    assert m2.title == "fm"
    m3 = resolve_meta({}, {}, Config(), fallback_title="h1标题")
    assert m3.title == "h1标题"


def test_defaults_from_config():
    cfg = Config(default_theme="plain", default_code_style="monokai")
    m = resolve_meta({}, {}, cfg)
    assert m.theme == "plain" and m.code_style == "monokai"


def test_validate_title_limits():
    m = resolve_meta({"title": "x" * 33}, {}, Config())
    with pytest.raises(ValidationError, match="32"):
        validate(m, "<p>c</p>")
    m2 = resolve_meta({"title": "ok"}, {"author": "a" * 17}, Config())
    with pytest.raises(ValidationError, match="16"):
        validate(m2, "<p>c</p>")


def test_validate_digest_byte_limit():
    # 111 字符 / 167 字节的摘要（真实踩坑案例）必须被拦下
    m = resolve_meta({"title": "t", "digest": "在 RTX 5060 Ti 16GB 上部署 Qwen3.6-35B-A3B（HauhauCS uncensored，IQ4_XS）的实测方案： 200K 上下文 + 视觉，单卡 16GB 跑满血 35B MoE 。硬件…"}, {}, Config())
    with pytest.raises(ValidationError, match="字节"):
        validate(m, "<p>c</p>")


def test_validate_content_limit():
    m = resolve_meta({"title": "t"}, {}, Config())
    with pytest.raises(ValidationError, match="20000"):
        validate(m, "x" * 20001)
    warns = validate(m, "x" * 18500)
    assert warns  # 接近上限给警告


def test_to_draft_article_omits_empty():
    m = resolve_meta({"title": "t"}, {}, Config())
    art = to_draft_article(m, "<p>c</p>", "MEDIA")
    assert art["title"] == "t" and art["thumb_media_id"] == "MEDIA"
    assert "author" not in art and "digest" not in art
    assert "need_open_comment" not in art
