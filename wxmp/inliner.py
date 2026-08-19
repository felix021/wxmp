"""CSS -> 内联 style 引擎（tinycss2 解析 + BeautifulSoup 匹配）。

支持的选择器：tag、.class、tag.class、.a.b、后代（A B）、子代（A > B）、逗号组。
不支持：id/属性选择器、伪类/伪元素、兄弟组合器（+ ~）、@规则（跳过并回调警告）。
"""

from __future__ import annotations

import re

import tinycss2
from bs4 import BeautifulSoup, Tag

_PART_RE = re.compile(r"^([a-zA-Z][\w-]*|\*)?((?:\.[\w-]+)*)$")

# 简写属性序列化时排在长写属性之前，保证长写（如 margin-top）能覆盖简写（margin）
_SHORTHANDS = {
    "animation", "background", "border", "border-radius", "columns", "flex",
    "flex-flow", "font", "gap", "grid", "grid-area", "grid-column", "grid-row",
    "list-style", "margin", "offset", "outline", "overflow", "padding",
    "place-content", "place-items", "place-self", "text-emphasis", "transition",
}


def _noop(msg: str) -> None:
    pass


def _parse_selector(sel: str) -> list | None:
    """选择器文本 -> [(组合器 None|' '|'>', (tag, classes)), ...]；不支持则 None。"""
    if re.search(r"[#\[+~:]", sel):
        return None
    sel = re.sub(r"\s*>\s*", " > ", sel.strip())
    chain: list[tuple[str | None, tuple]] = []
    comb: str | None = None
    for tok in sel.split():
        if tok == ">":
            if not chain:
                return None
            comb = ">"
            continue
        m = _PART_RE.match(tok)
        if not m:
            return None
        tag = m.group(1)
        classes = tuple(c for c in re.findall(r"\.([\w-]+)", tok))
        chain.append((comb, (tag, classes)))
        comb = " "
    return chain or None


def _part_matches(el: Tag, part: tuple) -> bool:
    tag, classes = part
    if tag not in (None, "*") and el.name != tag.lower():
        return False
    el_classes = el.get("class") or []
    return all(c in el_classes for c in classes)


def _chain_matches(el: Tag, chain: list) -> bool:
    def match_at(el: Tag, idx: int) -> bool:
        comb, part = chain[idx]
        if not _part_matches(el, part):
            return False
        if idx == 0:
            return True
        if comb == ">":
            parent = el.parent
            return isinstance(parent, Tag) and match_at(parent, idx - 1)
        anc = el.parent
        while isinstance(anc, Tag):
            if match_at(anc, idx - 1):
                return True
            anc = anc.parent
        return False

    return match_at(el, len(chain) - 1)


def _specificity(chain: list) -> tuple[int, int]:
    n_cls = sum(len(part[1]) for _, part in chain)
    n_tag = sum(1 for _, (tag, _) in chain if tag not in (None, "*"))
    return (n_cls, n_tag)


def _parse_rules(css: str, on_warning) -> list:
    rules = []
    for rule in tinycss2.parse_blocks_contents(css):
        if isinstance(rule, tinycss2.ast.AtRule):
            on_warning(f"跳过不支持的 @规则 @{rule.at_keyword}")
            continue
        if not isinstance(rule, tinycss2.ast.QualifiedRule):
            continue
        decls = {}
        for d in tinycss2.parse_declaration_list(rule.content):
            if isinstance(d, tinycss2.ast.Declaration):
                val = tinycss2.serialize(d.value).strip()
                if val:
                    decls[d.name.lower()] = val
        if not decls:
            continue
        sel_text = tinycss2.serialize(rule.prelude).strip()
        chains, ok = [], True
        for sel in sel_text.split(","):
            sel = sel.strip()
            if not sel:
                continue
            chain = _parse_selector(sel)
            if chain is None:
                on_warning(f"跳过不支持的选择器 {sel!r}")
                ok = False
                break
            chains.append(chain)
        if ok and chains:
            rules.append((chains, decls, len(rules)))
    return rules


def _parse_inline_style(style: str) -> dict:
    out = {}
    for chunk in (style or "").split(";"):
        if ":" in chunk:
            k, _, v = chunk.partition(":")
            k, v = k.strip().lower(), v.strip()
            if k and v:
                out[k] = v
    return out


def _prop_rank(name: str) -> tuple[int, str]:
    return (0 if name in _SHORTHANDS else 1, name)


def _serialize(decls: dict) -> str:
    # 紧凑格式（";" 无空格）：微信 2 万字符上限下，内联样式体积是稀缺资源
    return ";".join(f"{k}:{decls[k]}" for k in sorted(decls, key=_prop_rank))


def inline_css(html: str, css: str, *, on_warning=None) -> str:
    """把 css 规则内联进 html 每个元素的 style 属性。

    元素原有内联 style 的声明最后合并（可覆盖主题），保证代码高亮的
    token 颜色和用户手写样式优先于主题规则。
    """
    if on_warning is None:
        on_warning = _noop
    soup = BeautifulSoup(html, "html.parser")
    rules = _parse_rules(css, on_warning)
    for el in soup.find_all(True):
        collected = []  # (specificity, 规则顺序, declarations)
        for chains, decls, order in rules:
            best = None
            for ch in chains:
                if _chain_matches(el, ch):
                    s = _specificity(ch)
                    if best is None or s > best:
                        best = s
            if best is not None:
                collected.append((best, order, decls))
        own = _parse_inline_style(el.get("style") or "")
        if not collected and not own:
            continue
        collected.sort(key=lambda t: (t[0], t[1]))
        merged: dict = {}
        for _, _, decls in collected:
            merged.update(decls)
        merged.update(own)
        if merged:
            el["style"] = _serialize(merged)
    return str(soup)
