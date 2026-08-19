import pytest

from wxmp.errors import RenderError
from wxmp.render import (
    apply_theme, extract_front_matter, make_digest, plain_text,
    sanitize_for_wechat,
)


def test_front_matter_extraction():
    fm, body = extract_front_matter("---\ntitle: T\nauthor: A\n---\n\n# hi\n")
    assert fm == {"title": "T", "author": "A"}
    assert body.strip().startswith("# hi")


def test_front_matter_invalid_yaml():
    with pytest.raises(RenderError):
        extract_front_matter("---\n[broken\n---\nbody")


def test_front_matter_non_mapping():
    with pytest.raises(RenderError, match="mapping"):
        extract_front_matter("---\n- a\n- b\n---\nbody")


def test_sanitize_strips_dangerous():
    out = sanitize_for_wechat(
        '<p onclick="x()" class="c" id="i">ok</p>'
        "<script>alert(1)</script>"
        "<style>p{}</style>"
    )
    assert "script" not in out and "style=" not in out.replace("style>", "")
    assert "class=" not in out and "onclick" not in out
    assert "ok" in out


def test_sanitize_unwraps_unknown_tags():
    out = sanitize_for_wechat("<article><p>keep</p></article>")
    assert "article" not in out and "keep" in out


def test_apply_theme_end_to_end():
    out = apply_theme("<p>hi</p><pre><code>x</code></pre>", "p { color: red; }")
    assert 'style="color:red"' in out


def test_digest_byte_limit():
    html = "<h1>标题</h1><p>" + "正" * 200 + "</p>"
    d = make_digest(html, max_bytes=30)
    assert d.endswith("…")
    assert len(d.encode("utf-8")) <= 33  # 30 + "…"3 字节
    # 中英混合：ASCII 多时字符数更多
    d2 = make_digest("<p>" + "a" * 500 + "</p>", max_bytes=30)
    assert d2 == "a" * 30  # 未超限时无省略号


def test_highlight_unknown_lang_fallback():
    from wxmp.render import render_markdown

    out = render_markdown("```notalang\n<x>&\n```", "default")
    assert "&lt;x&gt;&amp;" in out  # 未知语言降级为纯转义


def test_highlight_inline_spans():
    from wxmp.render import render_markdown

    out = render_markdown("```python\ndef f():\n    pass\n```", "default")
    assert "<span" in out and "color:#" in out
