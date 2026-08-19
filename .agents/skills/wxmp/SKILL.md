---
name: wxmp
description: 推送 Markdown/HTML 文章到微信公众号草稿箱（wxmp CLI：内联排版、图片自动转传压缩、封面上传、草稿增删改查）。当用户提到公众号/微信公众号、草稿箱、图文、发文章/推文章/投稿到公众号、把 md 或 html 做成公众号文章，或直接提到 wxmp 时使用——即使用户没有说出 "wxmp" 这个名字。不负责已发布文章的管理和微信小程序。
---

# wxmp — 微信公众号草稿推送

wxmp 是本机的 Python CLI，把 Markdown/HTML 渲染成微信可用的**内联样式** HTML（微信会过滤 class/`<style>`/`<script>`），自动转传图片、上传封面，推送到草稿箱。

- 可执行文件：`/home/felix021/code/weixin-mp/.venv/bin/wxmp`（源码同目录，下文简写 `wxmp`）
- 配置已就绪（`~/.config/wxmp/config.json`：appid/secret/api_proxy 固定出口 IP，白名单已配），**不要改动**
- 发布永远由用户在 mp.weixin.qq.com 后台手动完成，工具只到草稿箱

## 标准工作流（新文章）

```bash
wxmp preview article.md -o /tmp/preview.html   # 1. 离线渲染，浏览器 375px 宽核对
wxmp push article.md --dry-run                 # 2. 完整渲染不发请求，核对汇总
wxmp push article.md                           # 3. 推送，输出 media_id
```

用户后台核对满意后手动发布。**修改后重推用原地更新，不要新建**：

```bash
wxmp push article.md --update latest           # 更新最近一条草稿
wxmp push article.md --update=<media_id>       # 指定草稿；id 以 - 开头必须用等号形式
```

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

HTML 文件同样支持，元数据走 CLI 参数。图片：本地路径/外链/data URI 均自动转传微信图床（超 1MB 自动压缩、gif/webp/bmp 转码）；已是 `mmbiz.qpic.cn` 的跳过。

## 微信平台硬限制（推送前自查，工具会拦但最好提前规划）

1. **正文 ≤20000 字符**：内联样式让体积膨胀 4-6 倍，密集代码块+表格的技术长文几乎必超（一篇 27KB 的部署文内联后 12.4 万字符）。
   解法（按优先级）：① 删大代码块，正文只留关键参数，完整版放 gist 并设 `content_source_url` 指向它（文首 blockquote 写明"完整命令见阅读原文"+ 明文 URL）；② 精简表格行列；③ 必要时拆篇。微信 2 万字符上限无法绕过。
2. **标题 ≤32 字**、**作者 ≤16 字**、**摘要 ≤120 字节**（微信按字节计，中英混合时字符数远少于 120；工具按字节自动截断）。
3. 未认证账号：正文超链接会被剥成纯文本；遇 48001 = 账号无草稿接口权限。
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

- 内置主题是纯 CSS（选择器支持 tag/.class/后代/子代/逗号组），自定义主题参考 `/home/felix021/code/weixin-mp/examples/custom-theme.css`
- 主题 CSS 的 `pre` 背景要配 `code_style`：浅底配 default/friendly，暗底配 monokai
- 体积紧张时的已知手段（已内置）：紧凑序列化、继承优化（li/td 字号颜色上移容器）；进一步要压就从内容下手

## 故障排查

| 报错 | 含义 |
|---|---|
| `40164 invalid ip` | 出口 IP 不在白名单（提示里带微信看到的 IP）；检查 api_proxy |
| `45004 description size` | 摘要超 120 字节 |
| `40001/42001` | token 失效（工具已自动强刷重试一次，持续出现查 appid/secret 配对） |
| `40125` | secret 错误或已重置 |
| 草稿里中文变 `二` 转义文本 | 历史 bug 已修（JSON 必须 ensure_ascii=False）；若复现查 wechat.py 序列化 |
| `drafts list` 乱码 | 历史 bug 已修（响应强制 utf-8 解码） |
