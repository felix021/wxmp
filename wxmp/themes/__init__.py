"""内置主题加载：按内置名或 .css 文件路径加载主题。"""

from importlib import resources
from pathlib import Path

from wxmp.errors import RenderError

BUILTIN_THEMES = ("default", "plain")


def list_themes() -> list[str]:
    return list(BUILTIN_THEMES)


def _builtin_css(name: str) -> str:
    return (resources.files("wxmp.themes") / f"{name}.css").read_text(encoding="utf-8")


def load_theme(name_or_path: str) -> tuple[str, str]:
    """返回 (主题名, css 文本)。支持内置名或 .css 路径。"""
    if not name_or_path:
        name_or_path = "default"
    p = Path(name_or_path).expanduser()
    if p.suffix.lower() == ".css" or p.exists():
        if not p.is_file():
            raise RenderError(f"主题文件不存在: {p}")
        return p.stem, p.read_text(encoding="utf-8")
    if name_or_path in BUILTIN_THEMES:
        return name_or_path, _builtin_css(name_or_path)
    raise RenderError(
        f"未知主题 {name_or_path!r}：内置主题有 {'/'.join(BUILTIN_THEMES)}，或传入 .css 文件路径"
    )
