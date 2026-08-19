---
title: wxmp 功能演示
author: felix021
digest: 这是一篇覆盖 wxmp 全部排版能力的演示文章，包含标题、粗斜体、引用、列表、表格、代码高亮与图片处理。
cover: cover.png
theme: default
code_style: default
content_source_url: https://example.com/original-post
---

# wxmp 功能演示

这是一段普通正文。wxmp 会把 Markdown 渲染成**微信可用的内联样式 HTML**——微信公众号编辑器会过滤 `class`、`<style>` 和 `<script>`，所以所有样式必须写在元素的 `style` 属性里，这个工具帮你自动完成。

## 文字样式

支持**粗体**、*斜体*、~~删除线~~、`行内代码`，以及[超链接](https://example.com)。未认证账号的正文超链接会被微信转为纯文本，这是平台限制。

## 引用

> 这是一段引用文字。微信里引用通常带左侧色条与浅色背景，由主题 CSS 提供样式。
>
> 引用里的第二段。

## 列表

无序列表：

- 第一项
- 第二项
  - 嵌套项

有序列表：

1. 步骤一
2. 步骤二
3. 步骤三

## 表格

| 接口 | 用途 | 限制 |
|---|---|---|
| draft/add | 新增草稿 | 正文 <2万字符 |
| media/uploadimg | 正文图片 | jpg/png <1MB |
| material/add_material | 封面永久素材 | <10MB |

## 代码高亮

```python
def hello(name: str) -> str:
    """支持 docstring 与注释。"""
    greeting = f"Hello, {name}!"
    for i in range(3):
        print(f"{i}: {greeting}")
    return greeting
```

无语言标注的代码块：

```
plain text code block
第二行
```

## 图片

本地图片会被上传到微信图床（正文外链图片会被微信过滤，必须转传）：

![一张演示图](demo-image.png)

## 分割线

---

以上覆盖了 wxmp 支持的全部常用语法。用 `wxmp preview examples/demo.md` 即可在本地预览效果。
