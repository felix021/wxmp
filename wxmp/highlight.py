"""Pygments 内联样式高亮：token 直接输出带 style 的 <span>，不产生 class。"""

from __future__ import annotations

import html
import io
from typing import Callable

from pygments.formatter import Formatter
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound


class _InlineFormatter(Formatter):
    """把每个 token 渲染为 <span style="color:...;font-weight:...">text</span>。"""

    def format_unencoded(self, tokensource, outfile):
        for ttype, value in tokensource:
            st = self.style.style_for_token(ttype)
            decl = []
            if st.get("color"):
                decl.append(f"color:#{st['color'].lstrip('#')}")
            if st.get("bgcolor"):
                decl.append(f"background-color:#{st['bgcolor'].lstrip('#')}")
            if st.get("bold"):
                decl.append("font-weight:700")
            if st.get("italic"):
                decl.append("font-style:italic")
            if st.get("underline"):
                decl.append("text-decoration:underline")
            text = html.escape(value, quote=False)
            if decl:
                outfile.write(f'<span style="{";".join(decl)}">{text}</span>')
            else:
                outfile.write(text)


def make_highlighter(code_style: str) -> Callable[[str, str, str], str]:
    """返回满足 markdown-it options.highlight 签名 (code, lang, attrs) 的高亮函数。

    返回以 <pre 开头的字符串时 markdown-it 会跳过内部包装，直接使用。
    """
    formatter = _InlineFormatter(style=get_style_by_name(code_style))

    def _highlight(code: str, lang: str, attrs: str) -> str:
        lang = (lang or "").strip().lower()
        if not lang:
            return ""  # 无语言标注，交给 markdown-it 默认转义包装
        try:
            from pygments.lexers import get_lexer_by_name

            lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
        except ClassNotFound:
            escaped = html.escape(code, quote=False)
            return f"<pre><code>{escaped}</code></pre>"
        buf = io.StringIO()
        formatter.format(lexer.get_tokens(code), buf)
        return f"<pre><code>{buf.getvalue()}</code></pre>"

    return _highlight


def list_code_styles() -> list[str]:
    from pygments.styles import get_all_styles

    return sorted(get_all_styles())
