"""错误体系：所有面向用户的异常与人话提示表。"""


class WxmpError(Exception):
    """用户可见错误。msg 已是面向用户的中文说明。"""


class ConfigError(WxmpError):
    """appid/secret 缺失、配置文件损坏等。"""


class RenderError(WxmpError):
    """Markdown/HTML 解析失败、front-matter 非法等。"""


class ValidationError(WxmpError):
    """title/digest/content 超出微信限制。"""


class ImageError(WxmpError):
    """图片下载失败、格式不支持、压缩后仍超限等。"""


class WeChatError(WxmpError):
    """微信 API 返回 errcode != 0。"""

    def __init__(self, errcode: int, errmsg: str, hint: str = ""):
        self.errcode = errcode
        self.errmsg = errmsg
        self.hint = hint
        msg = f"微信接口错误 {errcode}: {errmsg}"
        if hint:
            msg += f"\n  提示: {hint}"
        super().__init__(msg)


GLOBAL_ERRCODE_DOC = (
    "https://developers.weixin.qq.com/doc/offiaccount/"
    "Getting_Started/Explanation_global_error_codes.html"
)

# errcode -> 人话提示；None 表示用动态函数生成
ERRCODE_HINTS: dict[int, str] = {
    40001: "access_token 无效（已自动刷新重试过一次），请确认 appid 与 secret 属于同一个公众号",
    40013: "appid 不合法：应使用该公众号的 AppID（wx 开头），见 设置与开发→基本配置",
    40125: "secret 不合法或已在后台重置，请更新配置（wxmp config set secret ... 或环境变量 WXMP_SECRET）",
    40005: "文件类型不合法：正文图片仅支持 jpg/png，封面另支持 bmp/gif",
    45001: "媒体文件超过大小限制",
    40007: "media_id 无效",
    41005: "缺少 media_id 参数",
    48001: "api 功能未授权：草稿接口需要已认证的订阅号/服务号，个人未认证账号不可用",
    45009: "接口调用次数超过限额，次日重置（wxmp 已做本地 token 缓存，频繁出现请检查脚本是否反复获取 token）",
    -1: "微信系统繁忙，请稍后重试",
}


def errcode_hint(errcode: int, errmsg: str = "") -> str:
    if errcode == 40164:
        import re

        m = re.search(r"invalid ip ([\d.]+)", errmsg, re.I)
        ip = m.group(1) if m else "x.x.x.x"
        return (
            f"调用方 IP {ip} 不在白名单内：请到 公众平台→设置与开发→基本配置→IP 白名单 "
            f"添加该地址。注意挂代理时出口 IP 会变（wxmp 已对 api.weixin.qq.com 强制直连，"
            f"若仍不对请检查系统级透明代理）"
        )
    if errcode in (40001, 42001):
        return "access_token 已过期或无效（已自动刷新重试过一次）；若反复出现请确认 appid 与 secret 是否配对"
    return ERRCODE_HINTS.get(errcode, f"详见全局错误码文档: {GLOBAL_ERRCODE_DOC}")
