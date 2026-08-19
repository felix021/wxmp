"""wxmp 命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wxmp import __version__, pipeline, preview, themes
from wxmp.config import load_config, mask_secret, save_config
from wxmp.errors import (
    ImageError, RenderError, ValidationError, WxmpError,
)
from wxmp.meta import to_draft_article
from wxmp.wechat import WeChatClient

EXIT_OK = 0
EXIT_RENDER = 2
EXIT_IMAGE = 3
EXIT_CONFIG_API = 4


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wxmp",
        description="把 Markdown/HTML 文章推送到微信公众号草稿箱",
    )
    parser.add_argument("--version", action="version", version=f"wxmp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--title", help="标题（≤32字），覆盖 front-matter")
        p.add_argument("--author", help="作者（≤16字）")
        p.add_argument("--digest", help="摘要（≤120字），缺省自动截取正文")
        p.add_argument("--cover", help="封面图片路径，上传为微信永久素材")
        p.add_argument("--theme", help="排版主题：内置名(default/plain)或 .css 路径")
        p.add_argument("--code-style", help="代码高亮样式（pygments 样式名，如 monokai）")
        p.add_argument("--content-source-url", help="「阅读原文」链接")

    p_push = sub.add_parser("push", help="渲染并推送到草稿箱")
    p_push.add_argument("file", help="Markdown 或 HTML 文件")
    add_common(p_push)
    p_push.add_argument("--no-digest", action="store_true",
                        help="不生成摘要，交给微信取正文前 54 字")
    p_push.add_argument("--update", metavar="MEDIA_ID|latest",
                        help="更新已有草稿（原地修改）而非新建；latest=最近一条草稿。"
                             "media_id 以 - 开头，请用 --update=xxx 等号形式")
    p_push.add_argument("--dry-run", action="store_true",
                        help="完整渲染但不发起任何微信请求，输出汇总")
    p_push.add_argument("--output-content", metavar="PATH",
                        help="把最终 content HTML 另存一份，便于比对")
    p_push.add_argument("--verbose", action="store_true", help="出错时显示堆栈")

    p_prev = sub.add_parser("preview", help="生成手机宽度本地预览（不调微信 API）")
    p_prev.add_argument("file", help="Markdown 或 HTML 文件")
    p_prev.add_argument("-o", "--output", help="输出路径（默认 <文件名>.preview.html）")
    p_prev.add_argument("--width", type=int, default=375, help="预览宽度 px（默认 375）")
    add_common(p_prev)
    p_prev.add_argument("--no-digest", action="store_true")
    p_prev.add_argument("--verbose", action="store_true")

    p_drafts = sub.add_parser("drafts", help="草稿箱管理")
    drafts_sub = p_drafts.add_subparsers(dest="drafts_cmd", required=True)
    drafts_sub.add_parser("count", help="草稿总数")
    p_list = drafts_sub.add_parser("list", help="最近草稿列表")
    p_list.add_argument("--limit", type=int, default=10)
    p_del = drafts_sub.add_parser("delete", help="删除草稿")
    p_del.add_argument("media_id")

    p_send = sub.add_parser(
        "send", help="群发草稿给粉丝（订阅号每天 1 次；不可撤回，草稿发后自动删除）")
    p_send.add_argument("media_id", help="草稿 media_id（以 - 开头时前置 --），或 latest")
    p_send.add_argument("--tag", type=int, help="发给指定标签用户（缺省发给全部粉丝）")

    p_pub = sub.add_parser(
        "publish", help="发布草稿到公众号主页（不推送粉丝、不占群发次数）")
    p_pub.add_argument("media_id", help="草稿 media_id（以 - 开头时前置 --），或 latest")
    p_pub.add_argument("--status", metavar="PUBLISH_ID", help="查询发布状态而非提交发布")

    p_themes = sub.add_parser("themes", help="列出可用主题")
    p_themes.add_argument("--code-styles", action="store_true",
                          help="列出 pygments 代码高亮样式")

    p_cfg = sub.add_parser("config", help="查看/设置配置")
    cfg_sub = p_cfg.add_subparsers(dest="config_cmd", required=True)
    cfg_sub.add_parser("show", help="显示当前配置")
    p_set = cfg_sub.add_parser("set", help="设置配置项")
    p_set.add_argument("key", choices=["appid", "secret", "default_theme",
                                       "default_code_style", "image_max_width",
                                       "download_proxy", "api_proxy"])
    p_set.add_argument("value")

    return parser


def _opts_from_args(args) -> dict:
    keys = ("title", "author", "digest", "cover", "theme", "code_style",
            "content_source_url")
    opts = {k: getattr(args, k, None) for k in keys}
    opts["no_digest"] = getattr(args, "no_digest", False)
    return opts


def _cmd_preview(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise RenderError(f"文件不存在: {path}")
    cfg = load_config()
    built = pipeline.build_article(path, _opts_from_args(args), cfg, client=None)
    out = Path(args.output) if args.output else path.with_suffix(".preview.html")
    meta_line = " / ".join(filter(None, [built.meta.author, built.theme_name]))
    page = preview.render_preview_page(
        built.content_html, built.meta.title or "(无标题)",
        width=args.width, meta_line=meta_line,
    )
    out.write_text(page, encoding="utf-8")
    for line in built.report:
        print(line)
    for w in built.warnings:
        print(f"警告: {w}", file=sys.stderr)
    print(f"预览已生成: {out}（浏览器打开查看）")
    return EXIT_OK


def _cmd_push(args) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise RenderError(f"文件不存在: {path}")
    cfg = load_config()
    client = None if args.dry_run else WeChatClient(
        cfg.appid, cfg.secret, api_proxy=cfg.api_proxy)
    built = pipeline.build_article(path, _opts_from_args(args), cfg, client=client)

    if args.output_content:
        Path(args.output_content).write_text(built.content_html, encoding="utf-8")
        print(f"content 已另存: {args.output_content}")

    for line in built.report:
        print(line)
    for w in built.warnings:
        print(f"警告: {w}", file=sys.stderr)

    m = built.meta
    n_chars = len(built.content_html)
    if args.dry_run:
        print("--- dry-run 汇总（未发起任何微信请求）---")
        print(f"标题: {m.title} ({len(m.title)}字)")
        print(f"作者: {m.author or '(空)'}")
        print(f"摘要: {m.digest or '(空，交给微信取正文前54字)'}")
        print(f"正文: {n_chars} 字符（上限 20000）")
        print(f"封面: {m.cover or '(未指定，将用正文第一张图)'}")
        print(f"主题: {built.theme_name}")
        return EXIT_OK

    thumb = pipeline.ensure_thumb(client, built, path.parent, built.report)
    article = to_draft_article(m, built.content_html, thumb)
    if args.update:
        target = args.update
        if target == "latest":
            items = client.draft_batchget(offset=0, count=1).get("item", [])
            if not items:
                raise ConfigError("草稿箱为空，没有可更新的草稿")
            target = items[0]["media_id"]
        client.draft_update(target, article)
        print(f"草稿已更新 media_id={target}")
    else:
        media_id = client.draft_add(article)
        print(f"草稿已创建 media_id={media_id}")
    print("请到 mp.weixin.qq.com → 草稿箱 查看，确认无误后手动发布。")
    return EXIT_OK


def _cmd_drafts(args) -> int:
    cfg = load_config()
    client = WeChatClient(cfg.appid, cfg.secret, api_proxy=cfg.api_proxy)
    if args.drafts_cmd == "count":
        print(client.draft_count())
    elif args.drafts_cmd == "list":
        data = client.draft_batchget(offset=0, count=max(1, min(args.limit, 20)))
        items = data.get("item", [])
        if not items:
            print("(草稿箱为空)")
        for it in items:
            arts = it.get("content", {}).get("news_item", [])
            title = arts[0].get("title", "?") if arts else "(无图文)"
            print(f"{it.get('media_id')}  {it.get('update_time', '')}  {title}")
    elif args.drafts_cmd == "delete":
        client.draft_delete(args.media_id)
        print(f"已删除草稿 {args.media_id}")
    return EXIT_OK


def _resolve_media_id(client, media_id: str) -> str:
    if media_id == "latest":
        items = client.draft_batchget(offset=0, count=1).get("item", [])
        if not items:
            raise ConfigError("草稿箱为空，没有可用的草稿")
        return items[0]["media_id"]
    return media_id


def _cmd_send(args) -> int:
    cfg = load_config()
    client = WeChatClient(cfg.appid, cfg.secret, api_proxy=cfg.api_proxy)
    media_id = _resolve_media_id(client, args.media_id)
    print(f"群发中 media_id={media_id} "
          f"({'标签 ' + str(args.tag) if args.tag else '全部粉丝'})…")
    data = client.mass_sendall(media_id, tag_id=args.tag)
    print(f"群发任务已提交 msg_id={data['msg_id']}")
    print("注意：仅代表任务提交成功；草稿已自动移出草稿箱；结果以公众号后台为准。")
    return EXIT_OK


def _cmd_publish(args) -> int:
    cfg = load_config()
    client = WeChatClient(cfg.appid, cfg.secret, api_proxy=cfg.api_proxy)
    if args.status:
        data = client.freepublish_get(args.status)
        print(data)
        return EXIT_OK
    media_id = _resolve_media_id(client, args.media_id)
    publish_id = client.freepublish_submit(media_id)
    print(f"发布已提交 publish_id={publish_id}")
    print(f"查询状态：wxmp publish latest --status={publish_id}")
    return EXIT_OK


def _cmd_themes(args) -> int:
    if args.code_styles:
        from wxmp.highlight import list_code_styles

        for name in list_code_styles():
            print(name)
        return EXIT_OK
    print("内置主题:")
    for name in themes.list_themes():
        print(f"  {name}")
    print("自定义: wxmp preview x.md --theme my.css")
    return EXIT_OK


def _cmd_config(args) -> int:
    if args.config_cmd == "show":
        cfg = load_config()
        print(f"appid             = {cfg.appid or '(未设置)'}")
        print(f"secret            = {mask_secret(cfg.secret) or '(未设置)'}")
        print(f"default_theme     = {cfg.default_theme}")
        print(f"default_code_style= {cfg.default_code_style}")
        print(f"image_max_width   = {cfg.image_max_width}")
        print(f"download_proxy    = {cfg.download_proxy}")
        print(f"api_proxy         = {cfg.api_proxy or '(直连)'}")
        print(f"配置文件: ~/.config/wxmp/config.json")
        return EXIT_OK
    cfg = load_config()
    key, value = args.key, args.value
    if key in ("appid", "secret", "default_theme", "default_code_style",
               "download_proxy", "api_proxy"):
        setattr(cfg, key, value)
    elif key == "image_max_width":
        setattr(cfg, key, int(value))
    save_config(cfg)
    print(f"已设置 {key}（写入 ~/.config/wxmp/config.json）")
    return EXIT_OK


_HANDLERS = {
    "push": _cmd_push,
    "preview": _cmd_preview,
    "drafts": _cmd_drafts,
    "send": _cmd_send,
    "publish": _cmd_publish,
    "themes": _cmd_themes,
    "config": _cmd_config,
}


def _exit_code(e: WxmpError) -> int:
    if isinstance(e, (RenderError, ValidationError)):
        return EXIT_RENDER
    if isinstance(e, ImageError):
        return EXIT_IMAGE
    return EXIT_CONFIG_API


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    verbose = getattr(args, "verbose", False)
    try:
        return _HANDLERS[args.command](args)
    except WxmpError as e:
        if verbose:
            raise
        print(f"wxmp: {e}", file=sys.stderr)
        return _exit_code(e)
    except KeyboardInterrupt:
        print("wxmp: 已中断", file=sys.stderr)
        return 130
