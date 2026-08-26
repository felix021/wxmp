# AGENTS.md — wxmp 开发指南

wxmp：把 Markdown/HTML 文章推送到**微信公众号草稿箱**的 Python CLI（渲染内联样式、图片转传、封面管理、草稿/群发/发布）。单包无服务端，面向个人使用。

## 开发环境

- Python ≥3.10，venv 在 `.venv/`（重建：`python3 -m venv .venv && .venv/bin/pip install -e .`）
- 一切命令走 `.venv/bin/wxmp`（下文简写 `wxmp`）
- 测试：`.venv/bin/python -m pytest tests/`（40 个无网络单测；全绿是提交前提）
- git：github.com/felix021/wxmp（public），分支 main，直接提交推送

## 架构与数据流

```
cli.py                 argparse 子命令：push/preview/drafts/send/publish/themes/config
  └ pipeline.py        build_article()：push 与 preview 共用同一条管线（预览即所得：
                       preview 渲染的就是发给微信的最终字符串，绝不另走 <style>+class 路线）
      ├ meta.py        front-matter/CLI/config 三级合并（CLI > fm > 默认）+ 字段校验
      ├ render.py      markdown-it-py("js-default") + front_matter 插件 → HTML；
      │                sanitize：标签/属性白名单、剥 class/id/script
      │   ├ highlight.py  Pygments 自定义 Formatter，token 直接输出内联 style 的
      │   │               <span>（无 class，主题 CSS 无需覆盖 token 类）
      │   └ inliner.py    主题 CSS → 每元素 style（tinycss2+BeautifulSoup）；
      │                   支持选择器：tag/.class/tag.class/后代/子代/逗号组；
      │                   元素原有内联 style 最后合并（保 token 色 + 用户手写样式）
      ├ images.py      图片分类(local/remote/weixin/data) → Pillow 归一化
      │                (≤1MB jpg/png、exif 转置、格式转码、质量阶梯) → uploadimg 换 src
      └ themes/        default.css / plain.css（纯 CSS 主题）
wechat.py              WeChatClient：stable_token 本地缓存、40001/42001 自动强刷重试、
                       send/publish/freepublish；错误统一转 WeChatError(errcode, hint)
```

## 微信 API 关键事实（改代码前必读，都是实测踩过的坑）

1. **JSON 必须 `ensure_ascii=False`**：requests 的 `json=` 默认把中文转义成 `\uXXXX`，微信会原样存进草稿（标题变 `RTX 5060 Ti 部署...`）。已改为手动序列化 + 显式 Content-Type。
2. **响应强制 `resp.encoding="utf-8"`**：微信 JSON 不带 charset，requests 按 Latin-1 解码导致读取乱码。
3. `draft/add` 的 articles 是**数组**；`draft/update` 的 articles 是**单对象**且需 `index`（第一篇 0）。
4. digest ≤**120 字节**（按字节计，中英混合时字符数远少于 120；111 字/167 字节实测报 45004）。`make_digest` 按字节截断。
5. content ≤20000 字符；内联样式膨胀 4-6 倍，密集代码+表格的长文必超。已做的体积优化（紧凑序列化 `";"` 无空格、li/td 声明上移容器靠继承、字体列表精简）**勿回退**，长文依赖这些进线。
6. `mass/sendall` 无定时参数（定时要本地调度）；成功后**草稿自动删除**；订阅号每天 1 次（45028）。
7. 网络双 session 策略相反，勿统一：微信 API `trust_env=False` + 可选 `api_proxy`（出口 IP 要配白名单）；外链图片下载 `trust_env=True`（走环境代理）。
8. media_id 以 `-` 开头：argparse 需 `--update=<id>` 等号形式或位置参数前置 `--`。
9. **代码块不能依赖原始空格、换行或 `white-space: pre-wrap`**：公众号后台预览/保存会重写 DOM，清空只含普通空格的 span，并折叠原始换行。代码文本必须用 NBSP 表示空格、`<br>` 表示换行，且不要重新引入纯空白高亮 span。

## 配置与数据（本机已就绪，勿动）

- `~/.config/wxmp/config.json`（600）：appid/secret/默认项/api_proxy（指向一个出口 IP 固定的内网代理，其公网出口 IP 已加入公众号后台白名单；具体地址见本机配置文件，勿提交到仓库）
- `~/.config/wxmp/token.json`：token 缓存；`~/.cache/wxmp/materials.json`：封面 sha256→media_id 缓存
- 用户文章在 `~/articles/`；`examples/demo.md` 是渲染回归样例（覆盖全部语法）

## 验证流程

1. 改渲染：`wxmp preview examples/demo.md -o /tmp/p.html` → 浏览器 375px 检查；正文应无 `class=`、元素全带 `style=`
2. 改 API：pytest + `wxmp drafts count`（最轻的真实链路验证，不写数据）
3. 端到端：`push --dry-run` 看汇总 → `push` → `drafts list` 核对 → `drafts delete` 清理
4. 定时发送：`systemd-run --user --on-calendar="... Asia/Shanghai"`（OnCalendar 默认按 **UTC** 解析，必须显式时区；且需 `export XDG_RUNTIME_DIR=/run/user/$(id -u)`，atd 本机未装）

## 约定

- commit message 中文、不署名 co-author；改动即推 origin main
- skill 手册在 `.agents/skills/wxmp/`（`~/.claude/skills/wxmp` 与项目 `.claude/skills/` 软链到它）——命令用法、限制、故障排查表在那里维护，本文件只讲开发
