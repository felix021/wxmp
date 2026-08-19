"""本地预览页：以手机宽度渲染最终 content 字符串（所见即所得）。"""

from __future__ import annotations

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ margin: 0; background: #4a4a4a; font-family: -apple-system, BlinkMacSystemFont,
      "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif; }}
.phone {{ max-width: {width}px; margin: 24px auto; background: #fff; }}
.phone header {{ padding: 18px 20px 14px; border-bottom: 1px solid #eee; }}
.phone header h1 {{ font-size: 20px; line-height: 1.4; margin: 0; }}
.phone header .meta {{ font-size: 12px; color: #999; margin-top: 6px; }}
.content {{ padding: 8px 18px 32px; }}
.banner {{ text-align: center; font-size: 12px; color: #fff; padding: 6px;
          background: #8a8a8a; }}
</style>
</head>
<body>
<div class="phone">
  <div class="banner">wxmp 预览（手机宽度 {width}px，内容与推送草稿一致）</div>
  <header>
    <h1>{title}</h1>
    <div class="meta">{meta}</div>
  </header>
  <div class="content">
{content}
  </div>
</div>
</body>
</html>
"""


def render_preview_page(content_html: str, title: str, *, width: int = 375,
                        meta_line: str = "") -> str:
    return _TEMPLATE.format(
        title=title, width=width, meta=meta_line, content=content_html
    )
