"""Pygments 内联样式高亮：token 直接输出带 style 的 <span>，不产生 class。"""

from __future__ import annotations

import html
import io
from typing import Callable

from pygments.formatter import Formatter
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound


def _escape_code_text(value: str) -> str:
    """编码代码文本，避免微信编辑器在预览/保存时吞掉空格和换行。

    微信后台会重写代码块 DOM：纯空白文本节点和只含普通空格的 span
    可能被清空，原始换行也可能被折叠。用 NBSP 和显式 br 表达空白，
    不再依赖 white-space: pre-wrap 的浏览器行为。
    """
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    escaped = html.escape(value, quote=False)
    return escaped.replace(" ", "\u00a0").replace("\n", "<br/>")


class _InlineFormatter(Formatter):
    """把每个 token 渲染为 <span style="color:...;font-weight:...">text</span>。"""

    def format_unencoded(self, tokensource, outfile):
        for ttype, value in tokensource:
            text = _escape_code_text(value)
            # Pygments 会把空格和换行单独标成 Text.Whitespace。不要给这种
            # token 套空 span；微信保存时会清空它们，导致命令全部粘连。
            if value.isspace():
                outfile.write(text)
                continue
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
            return f"<pre><code>{_escape_code_text(code)}</code></pre>"
        try:
            from pygments.lexers import get_lexer_by_name

            lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
        except ClassNotFound:
            escaped = _escape_code_text(code)
            return f"<pre><code>{escaped}</code></pre>"
        buf = io.StringIO()
        formatter.format(lexer.get_tokens(code), buf)
        return f"<pre><code>{buf.getvalue()}</code></pre>"

    return _highlight


def list_code_styles() -> list[str]:
    from pygments.styles import get_all_styles

    return sorted(get_all_styles())
