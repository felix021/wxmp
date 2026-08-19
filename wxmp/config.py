"""配置读写：~/.config/wxmp/config.json，环境变量 WXMP_APPID/WXMP_SECRET 优先。"""

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

CONFIG_DIR = Path("~/.config/wxmp").expanduser()
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class Config:
    appid: str = ""
    secret: str = ""
    default_theme: str = "default"
    default_code_style: str = "default"
    image_max_width: int = 1080  # px，正文图最大宽度（微信 2x 显示宽度）
    download_proxy: str = "env"  # env=跟随环境变量代理 | none=直连 | http://... 指定
    # 微信 API 出口代理：本机公网 IP 不固定时，指向一个出口 IP 固定的代理，
    # 该 IP 加入公众号后台 IP 白名单即可长期稳定。空 = 直连。
    api_proxy: str = ""


def load_config() -> Config:
    cfg = Config()
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            from wxmp.errors import ConfigError

            raise ConfigError(f"配置文件损坏，请检查或删除 {CONFIG_PATH}: {e}") from e
        known = {f.name for f in fields(Config)}
        for k, v in data.items():
            if k in known:
                setattr(cfg, k, v)
    # 环境变量覆盖（凭据不落盘场景）
    cfg.appid = os.environ.get("WXMP_APPID", cfg.appid) or cfg.appid
    cfg.secret = os.environ.get("WXMP_SECRET", cfg.secret) or cfg.secret
    return cfg


def save_config(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(CONFIG_PATH)


def mask_secret(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 6:
        return "***"
    return f"{s[:3]}***{s[-3:]}"
