"""Markdown/HTML 渲染、主题应用与微信净化。"""

from __future__ import annotations

import re

import yaml
from bs4 import BeautifulSoup, Tag
from markdown_it import MarkdownIt

from wxmp import inliner
from wxmp.errors import RenderError
from wxmp.highlight import make_highlighter

# 这些标签连内容一起删除（微信不支持或禁止）
_DROP_TAGS = {
    "script", "style", "iframe", "input", "form", "button", "select",
    "textarea", "object", "embed", "track", "canvas", "svg", "video",
    "audio", "link", "meta", "noscript", "template",
}

# 白名单内的标签保留（其余 unwrap：去掉标签保留文字）
_KEEP_TAGS = {
    "p", "section", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot",
    "tr", "th", "td", "blockquote", "pre", "code", "strong", "em", "b",
    "i", "u", "del", "s", "sub", "sup", "mark", "a", "img", "hr", "br",
    "figure", "figcaption",
}

# 属性白名单（class/id 一律剥除，微信也会剥，提前剥省字符且保证预览所见即所得）
_ATTR_WHITELIST = {
    "style", "src", "href", "alt", "colspan", "rowspan", "width", "height",
}


def build_md(code_style: str) -> MarkdownIt:
    from mdit_py_plugins.front_matter import front_matter_plugin

    md = MarkdownIt("js-default", {"highlight": make_highlighter(code_style)})
    md.use(front_matter_plugin)
    return md


def extract_front_matter(md_text: str) -> tuple[dict, str]:
    """返回 (front_matter dict, 去掉 front-matter 后的正文)。"""
    tokens = build_md("default").parse(md_text)
    fm: dict = {}
    body = md_text
    for tok in tokens:
        if tok.type == "front_matter" and tok.map:
            try:
                data = yaml.safe_load(tok.content)
            except yaml.YAMLError as e:
                raise RenderError(f"front-matter YAML 解析失败: {e}") from e
            if data is None:
                data = {}
            if not isinstance(data, dict):
                raise RenderError("front-matter 必须是 `键: 值` 形式的 YAML 列表（mapping）")
            fm = data
            start, end = tok.map
            lines = md_text.split("\n")
            body = "\n".join(lines[:start] + lines[end:])
            break
    return fm, body


def render_markdown(body_md: str, code_style: str) -> str:
    html = build_md(code_style).render(body_md)
    if _has_stray_bold(html):
        # CommonMark 中文坑：**……）**的（加粗以全角标点结尾 + 紧跟汉字）
        # 闭合失效会把星号按字面输出。检测到残留时自动把边界标点移出
        # 加粗再重渲染；若修复后残留未减少则回退（不引入新问题）。
        fixed = _fix_cjk_flanking(body_md)
        if fixed != body_md:
            html2 = build_md(code_style).render(fixed)
            if html2.count("**") <= html.count("**"):
                html = html2
    return html


def _has_stray_bold(html: str) -> bool:
    no_pre = re.sub(r"<pre[^>]*>.*?</pre>", "", html, flags=re.S)
    return "**" in no_pre


_CJK = "一-鿿"
_CLOSE_PUNCT = "，。；：！？、）」』】”’"


def _fix_cjk_flanking(src: str) -> str:
    # 仅处理 closing 侧（**……P**H → **……**PH）：P**H 只可能是失效的
    # closer（有效 closer 不会有残留、不触发本修复）。opening 对称场景
    # （字**“……”**）与合法 closing（**加粗**（注）表面同形，正则无法区分，不修。
    close_pat = re.compile(
        r"\*\*([^*\n]*?)([%s])\*\*(?=[%s])" % (re.escape(_CLOSE_PUNCT), _CJK)
    )
    out, in_code = [], False
    for chunk in re.split(r"(`+)", src):
        if chunk.startswith("`"):
            in_code = not in_code  # 粗略跟踪 code span，code 内不动
            out.append(chunk)
            continue
        if in_code:
            out.append(chunk)
            continue
        out.append(close_pat.sub(r"**\1**\2", chunk))
    return "".join(out)


def parse_user_html(html_text: str) -> str:
    # BeautifulSoup 规整标签结构（不引入 html/body 包裹）
    return str(BeautifulSoup(html_text, "html.parser"))


def apply_theme(html: str, css: str, *, on_warning=None) -> str:
    """主题 CSS 内联 + 微信净化，输出最终 content 字符串。"""
    inlined = inliner.inline_css(html, css, on_warning=on_warning)
    return sanitize_for_wechat(inlined)


def sanitize_for_wechat(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    sanitize_soup(soup)
    return str(soup)


def sanitize_soup(soup: BeautifulSoup) -> None:
    for t in soup.find_all(_DROP_TAGS):
        t.decompose()
    for el in soup.find_all(True):
        if el.name not in _KEEP_TAGS:
            el.unwrap()
            continue
        for attr in list(el.attrs):
            if attr not in _ATTR_WHITELIST:
                del el.attrs[attr]
    _compact_structural_whitespace(soup)


# 块级标签：仅压缩"块级标签之间"的缩进/换行空白节点
_BLOCK_TAGS = {
    "p", "div", "section", "ul", "ol", "li", "table", "thead", "tbody",
    "tfoot", "tr", "th", "td", "blockquote", "pre", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "figure", "figcaption",
}


def _compact_structural_whitespace(soup: BeautifulSoup) -> None:
    """删除块级标签之间的纯空白文本节点（如 <ul>\\n<li> 里的 \\n）。

    微信编辑器会把这些换行解析成空的列表项/空段落；
    但 inline 标签之间的空白（<strong>a</strong> <em>b</em> 的空格）
    是文本分隔不能删，<pre>/<code> 内空白有语义也不能删。
    """
    from bs4 import NavigableString, Tag

    def block_or_none(x) -> bool:
        return x is None or (isinstance(x, Tag) and x.name in _BLOCK_TAGS)

    for s in soup.find_all(string=True):
        if isinstance(s, NavigableString) and not s.strip():
            if s.parent.name in ("pre", "code"):
                continue
            if block_or_none(s.previous_sibling) and block_or_none(s.next_sibling):
                s.extract()


def plain_text(html: str) -> str:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def make_digest(html: str, max_bytes: int = 117) -> str:
    """按 utf-8 字节数截断生成摘要（微信 digest 按字节限制，约 120 字节，
    实测 167 字节报 45004、88 字节通过；117 + "…"3 字节 = 120）。"""
    text = plain_text(html)
    buf = ""
    for ch in text:
        if len((buf + ch).encode("utf-8")) > max_bytes:
            return buf + "…"
        buf += ch
    return buf
