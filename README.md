# wxmp

把本地 Markdown / HTML 文章推送到**微信公众号草稿箱**的命令行工具。自动完成排版（样式内联）、图片转传、封面上传，推完后在 mp.weixin.qq.com 草稿箱里核对、手动发布。

```bash
wxmp preview article.md      # 本地手机宽度预览（不联网调 API）
wxmp push article.md         # 推送到草稿箱
wxmp push article.md --dry-run   # 完整渲染但不发任何请求，看汇总
```

## 使用前提

1. **获取凭据**：mp.weixin.qq.com → 设置与开发 → 基本配置 → 记下 AppID，生成/重置 AppSecret（需管理员扫码）。
2. **IP 白名单**：微信只允许白名单内的 IP 调用 API。
   - 本机公网 IP 固定：把出口 IP（`curl ifconfig.me`）加进白名单即可，wxmp 默认对 `api.weixin.qq.com` 直连。
   - 本机公网 IP 不固定（如家宽）：配置一个出口 IP 固定的代理，把该代理出口 IP 加白名单：
     ```bash
     wxmp config set api_proxy http://<代理地址>:<端口>
     ```
3. **账号类型**：草稿/素材接口需要**已认证的订阅号或服务号**；未认证账号调用会遇到 48001（api unauthorized）。
4. 写入凭据：
   ```bash
   wxmp config set appid wx1234...
   wxmp config set secret <secret>
   ```
   或用环境变量 `WXMP_APPID` / `WXMP_SECRET`（不想把 secret 落盘时）。配置文件在 `~/.config/wxmp/config.json`（600 权限）。

## 安装

```bash
git clone <repo> && cd weixin-mp
pipx install .          # 推荐；或 pip install --user .
# 开发：python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/wxmp ...
```

需要 Python ≥ 3.10。

## 快速上手

1. 写 Markdown（front-matter 指定元数据）：

   ```markdown
   ---
   title: 我的文章标题
   author: 张三
   cover: cover.png
   digest: 可选摘要，不填自动截取正文
   theme: default
   code_style: default
   content_source_url: https://example.com/src
   ---

   # 正文从这里开始

   支持 **粗体**、[链接](...)、表格、代码高亮、![图片](pic.png) …
   ```

2. 预览：`wxmp preview article.md`，浏览器打开生成的 `article.preview.html`（375px 手机宽度，内容与草稿完全一致）。
3. 推送：`wxmp push article.md`，成功后到公众号后台"草稿箱"核对，手动发布。

HTML 文件同样支持（`wxmp push article.html`），元数据走命令行参数（`--title` 等）。

## front-matter 字段

| 字段 | 说明 | 限制 |
|---|---|---|
| title | 标题（必填，兜底取正文第一个 h1） | ≤32 字 |
| author | 作者 | ≤16 字 |
| digest | 摘要；缺省自动截取正文 110 字；`--no-digest` 则交给微信取前 54 字 | ≤120 字 |
| cover | 封面图片路径（相对文章目录）；缺省用正文第一张图 | 推荐 900×500 |
| theme | 排版主题：`default` / `plain` / 自定义 .css 路径 | — |
| code_style | 代码高亮样式（pygments 名，如 `monokai`，`wxmp themes --code-styles` 列出全部） | — |
| content_source_url | 「阅读原文」链接 | ≤1KB |
| need_open_comment | 0/1 是否打开评论 | — |
| only_fans_can_comment | 0/1 仅粉丝可评论 | — |

CLI 参数优先级高于 front-matter（`--title --author --digest --cover --theme --code-style --content-source-url`）。

## 自定义主题

主题就是一份普通 CSS，工具会把规则**内联**到每个元素的 `style` 属性（微信会过滤 class/`<style>`/`<script>`）。参考 `examples/custom-theme.css`。

支持的选择器：`tag`、`.class`、`tag.class`、后代（`A B`）、子代（`A > B`）、逗号组。不支持 id/属性/伪类选择器和 `@` 规则。同一元素别混用简写与长写属性（如同时写 `margin` 和 `margin-top`）。

**代码块配色**：token 颜色由 `code_style`（pygments）决定，`pre` 背景色要配套——浅色样式（`default`/`friendly`）配浅底，暗色样式（`monokai`/`dracula`）配暗底。

## 其他命令

```bash
wxmp drafts count              # 草稿数量（也是验证凭据/白名单是否配好的最简单方式）
wxmp drafts list               # 最近草稿
wxmp drafts delete <media_id>  # 删除草稿
wxmp themes [--code-styles]    # 列出主题 / 代码高亮样式
wxmp config show               # 查看配置
wxmp push x.md --output-content out.html   # 另存最终 content，便于排查微信端过滤差异
```

## 微信平台限制（工具已自动处理的）

- 正文里的**外链图片会被微信过滤**，wxmp 自动把本地/外链图片转传到微信图床（自动压缩到 1MB 内、gif/webp/bmp 自动转码）。
- 样式必须内联（工具自动做）；正文 <2 万字符（内联样式膨胀体积，超长请拆篇）、<1MB。
- 已是 `mmbiz.qpic.cn` 的图片自动跳过（可重复推送）；注意他人文章里的 mmbiz 图片有防盗链，请保存到本地再引用。
- 未认证账号正文中的超链接会被微信转为纯文本（平台限制）。
- 封面上传为永久素材（有 sha256 缓存避免重复占额度）；素材被群发后会自动移出草稿箱。

## 开发

```bash
.venv/bin/python -m pytest tests/    # 35 个无网络单测
```

模块结构：`cli.py`（命令）→ `pipeline.py`（push/preview 共用编排）→ `render.py`（markdown-it-py + Pygments 内联高亮）/`inliner.py`（CSS 内联引擎）/`images.py`（图片归一化转传）→ `wechat.py`（API 客户端 + stable_token 缓存）。

## License

MIT
