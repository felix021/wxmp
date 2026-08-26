---
name: wxmp
description: 推送 Markdown/HTML 文章到微信公众号草稿箱（wxmp CLI：内联排版、图片自动转传压缩、封面上传、草稿增删改查）。当用户提到公众号/微信公众号、草稿箱、图文、发文章/推文章/投稿到公众号、把 md 或 html 做成公众号文章，或直接提到 wxmp 时使用——即使用户没有说出 "wxmp" 这个名字。不负责已发布文章的管理和微信小程序。
---

# wxmp — 微信公众号草稿推送

wxmp 是本机的 Python CLI，把 Markdown/HTML 渲染成微信可用的**内联样式** HTML（微信会过滤 class/`<style>`/`<script>`），自动转传图片、上传封面，推送到草稿箱。

- 可执行文件：仓库根目录下的 `.venv/bin/wxmp`（本 skill 即软链自该仓库的 `.agents/skills/wxmp/`；下文简写 `wxmp`）
- 配置已就绪（`~/.config/wxmp/config.json`：appid/secret/api_proxy 固定出口 IP，白名单已配），**不要改动**
- 发布永远由用户在 mp.weixin.qq.com 后台手动完成，工具只到草稿箱

## 标准工作流（新文章）

推送前先整理公众号专用元数据和链接：标题写入 front-matter 或用 `--title` 传入，正文不要再保留同名 h1；从站外资料中选一个作为 `content_source_url`，其余站外链接在正文中显示原始 URL。

```bash
wxmp preview article.md -o /tmp/preview.html   # 1. 离线渲染，浏览器 375px 宽核对
wxmp push article.md --dry-run                 # 2. 完整渲染不发请求，核对汇总
wxmp push article.md                           # 3. 推送，输出 media_id
```

用户后台核对满意后手动发布。确认草稿没有在公众号后台打开或编辑过时，修改后可以原地更新：

```bash
wxmp push article.md --update latest           # 更新最近一条草稿
wxmp push article.md --update=<media_id>       # 指定草稿；id 以 - 开头必须用等号形式
```

### 更新前先判断是否应当新建

微信草稿接口不会返回“是否在后台手工编辑过”的标记，不能仅凭 `drafts list`、`draft/get`、`update_time` 或正文内容可靠判断。即使两条草稿的 API 返回内容完全相同，后台编辑器保存的派生状态也可能不同。

- 上下文明确提到草稿曾在公众号后台打开、编辑或保存，或后台已经出现空列表项、错乱、代码排版异常等现象时，**不要直接执行 `--update`**。先提示这类状态无法通过 API 修复，并询问用户是否创建一条新草稿。
- 用户确认要新建后，运行不带 `--update` 的 `wxmp push`；不要删除旧草稿，除非用户明确要求。
- 用户确认草稿从未在后台打开或编辑过，才按原地更新流程执行。
- 上下文无法判断，但更新失败的后果可能覆盖用户手工修改时，先询问草稿是否在后台编辑过，不要自行假定。

## 命令速查

| 命令 | 用途 |
|---|---|
| `wxmp push <md\|html> [--title/--author/--digest/--cover/--theme/--code-style/--content-source-url]` | 推送草稿（CLI 参数覆盖 front-matter） |
| `wxmp push <file> --dry-run` | 渲染+校验但不发任何请求，输出汇总 |
| `wxmp push <file> --update latest` | 原地更新草稿 |
| `wxmp push <file> --output-content out.html` | 另存最终 content 排查差异 |
| `wxmp preview <file> [-o out] [--width 375]` | 手机宽度本地预览（不联网） |
| `wxmp drafts count / list / delete <media_id>` | 草稿箱管理；验证配置是否通畅跑 `drafts count` |
| `wxmp send <media_id\|latest> [--tag N]` | **群发**给粉丝（订阅号每天 1 次，不可撤回，草稿发后自动删除；仅认证账号） |
| `wxmp publish <media_id\|latest>` / `wxmp publish x --status=<id>` | **发布**到公众号主页（不推粉丝、不占群发次数）/ 查询发布状态 |
| `wxmp themes` / `wxmp themes --code-styles` | 内置主题（default/plain）/ pygments 代码样式 |
| `wxmp config show` | 查看配置 |

`drafts delete` 的 media_id 同样以 `-` 开头，要写 `wxmp drafts delete -- <media_id>`。

## 文章格式

Markdown 顶部 YAML front-matter：

```yaml
---
title: 标题（必填，≤32 字；缺省取正文第一个 h1）
author: 作者（≤16 字）
digest: 摘要（≤120 字节；不填自动截取正文）
cover: cover.png（本地路径，推荐 900×500；缺省用正文第一张图）
theme: default（default/plain/自定义 .css 路径）
code_style: default（pygments 名，暗底代码块配 monokai 等）
content_source_url: https://...（「阅读原文」链接）
---
```

微信公众号后台会单独显示素材标题。使用 front-matter 或 `--title` 后，正文开头不要再放同名 `# 标题`，否则读者会连续看到两次标题。一个 Markdown 文件还要用于博客时，单独生成公众号稿，或在推送前移除正文 h1。

正文链接按微信能力处理：

- 公众号站内文章链接可以保留为 Markdown 超链接。
- 站外只能选一个链接写入 `content_source_url`，显示为文末的「阅读原文」。
- 其他站外参考资料不要写成 `[名称](URL)`，微信会剥掉或限制链接；改成 `名称：https://完整地址`，让原始 URL 留在正文里供读者复制。

HTML 文件同样支持，元数据走 CLI 参数。图片：本地路径/外链/data URI 均自动转传微信图床（超 1MB 自动压缩、gif/webp/bmp 转码）；已是 `mmbiz.qpic.cn` 的跳过。

## 微信平台硬限制（推送前自查，工具会拦但最好提前规划）

1. **正文 ≤20000 字符**：内联样式让体积膨胀 4-6 倍，密集代码块+表格的技术长文几乎必超（一篇 27KB 的部署文内联后 12.4 万字符）。
   解法（按优先级）：① 删大代码块，正文只留关键参数，完整版放 gist 并设 `content_source_url` 指向它（文首 blockquote 写明"完整命令见阅读原文"+ 明文 URL）；② 精简表格行列；③ 必要时拆篇。微信 2 万字符上限无法绕过。
2. **标题 ≤32 字**、**作者 ≤16 字**、**摘要 ≤120 字节**（微信按字节计，中英混合时字符数远少于 120；工具按字节自动截断）。
3. **正文链接受限**：只把公众号站内文章写成可点击链接；站外链接只有 `content_source_url` 对应的「阅读原文」可以点击。其他站外资料必须在正文贴出完整原始 URL，不能只把地址藏在 Markdown 链接文本里。
4. 素材被群发后会自动移出草稿箱。
5. **发送 API 无定时参数**：定时发送用本地调度。本机方案（atd 未装、用户级 systemd 按 UTC 解析 OnCalendar，两个坑都踩过）：
   ```bash
   export XDG_RUNTIME_DIR=/run/user/$(id -u)
   systemd-run --user --on-calendar="2026-08-20 09:50:00 Asia/Shanghai" --unit=wxmp-send-<名> \
     bash -c '<wxmp绝对路径> send -- <media_id> > <日志> 2>&1'
   systemctl --user list-timers | grep wxmp        # 核对触发时间（时区！）
   systemctl --user stop wxmp-send-<名>.timer       # 取消
   ```
   注意用具体 media_id（latest 可能被新草稿顶掉）；后台若开「API 群发保护」会进管理员审批（89504）。

## 排版定制

- 内置主题是纯 CSS（选择器支持 tag/.class/后代/子代/逗号组），自定义主题参考 `examples/custom-theme.css`（仓库根相对）
- 主题 CSS 的 `pre` 背景要配 `code_style`：浅底配 default/friendly，暗底配 monokai
- 中文加粗写法 `**……）**的`（全角标点结尾紧跟汉字）会被 CommonMark 按字面输出——工具已自动修复（渲染失败时把边界标点移出加粗重渲染），仍有残留时会警告；写文章时可不必特意避开
- 体积紧张时的已知手段（已内置）：紧凑序列化、继承优化（li/td 字号颜色上移容器）；进一步要压就从内容下手

## 故障排查

| 报错 | 含义 |
|---|---|
| `40164 invalid ip` | 出口 IP 不在白名单（提示里带微信看到的 IP）；检查 api_proxy |
| `48001` | 当前公众号没有草稿接口权限，常见于未认证账号 |
| `45004 description size` | 摘要超 120 字节 |
| `40001/42001` | token 失效（工具已自动强刷重试一次，持续出现查 appid/secret 配对） |
| `40125` | secret 错误或已重置 |
| 草稿里中文变 `二` 转义文本 | 历史 bug 已修（JSON 必须 ensure_ascii=False）；若复现查 wechat.py 序列化 |
| `drafts list` 乱码 | 历史 bug 已修（响应强制 utf-8 解码） |
| 草稿在后台显示异常（空列表项/错乱）但 API 拉回 content 正常 | 草稿曾在后台编辑器打开过，编辑器派生状态已坏：**删除草稿重新 push 新建**（`--update` 覆盖 content 也治不好显示），新草稿即正常 |
