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
    # 未超限的短文本原样返回，不加省略号
    assert make_digest("<p>short</p>", max_bytes=30) == "short"


def test_compact_structural_whitespace():
    # 块级标签之间的 \n 会被微信解析成空列表项，必须删掉
    out = sanitize_for_wechat("<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n<p>t</p>")
    assert out == '<ul><li>a</li><li>b</li></ul><p>t</p>'
    # 表格结构空白同样压缩
    out2 = sanitize_for_wechat("<table>\n<thead>\n<tr>\n<th>h</th>\n</tr>\n</thead>\n</table>")
    assert "\n" not in out2
    # inline 标签之间的空格是文本分隔，必须保留
    out3 = sanitize_for_wechat("<p>word1 <strong>b</strong> <em>c</em> end</p>")
    assert "word1 <strong>b</strong> <em>c</em> end" in out3
    # pre 内空白有语义，不动
    out4 = sanitize_for_wechat("<pre><code>a\n  b</code></pre>")
    assert "a\n  b" in out4


def test_highlight_unknown_lang_fallback():
    from wxmp.render import render_markdown

    out = render_markdown("```notalang\n<x>&\n```", "default")
    assert "&lt;x&gt;&amp;" in out  # 未知语言降级为纯转义


def test_highlight_inline_spans():
    from wxmp.render import render_markdown

    out = render_markdown("```python\ndef f():\n    pass\n```", "default")
    assert "<span" in out and "color:#" in out
