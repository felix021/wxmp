"""微信服务端 API 客户端：stable_token 缓存、素材上传、草稿管理。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from wxmp.config import CONFIG_DIR
from wxmp.errors import ConfigError, WeChatError, errcode_hint

API_BASE = "https://api.weixin.qq.com"
TOKEN_EARLY_EXPIRY = 300  # 提前 300 秒视为过期


class WeChatClient:
    def __init__(self, appid: str, secret: str,
                 token_path: Path | None = None, api_proxy: str = ""):
        if not appid or not secret:
            raise ConfigError(
                "缺少 appid/secret：先执行 wxmp config set appid ... 和 wxmp config set secret ...，"
                "或设置环境变量 WXMP_APPID / WXMP_SECRET"
            )
        self.appid = appid
        self.secret = secret
        self.token_path = token_path or (CONFIG_DIR / "token.json")
        self.session = requests.Session()
        # 不读环境变量代理（出口 IP 必须与公众号 IP 白名单匹配，要可控）；
        # 本机公网 IP 不固定时可配置 api_proxy 指向出口 IP 固定的代理。
        self.session.trust_env = False
        if api_proxy:
            self.session.proxies = {"http": api_proxy, "https": api_proxy}
        self._token: str | None = None
        self._token_expires = 0.0

    # ---- access_token ----

    def get_access_token(self, *, force: bool = False) -> str:
        now = time.time()
        if not force:
            if self._token and now < self._token_expires:
                return self._token
            cached = self._load_token_cache()
            if cached and now < cached[1]:
                self._token, self._token_expires = cached
                return self._token
        resp = self.session.post(
            f"{API_BASE}/cgi-bin/stable_token",
            data=json.dumps({
                "grant_type": "client_credential",
                "appid": self.appid,
                "secret": self.secret,
                "force_refresh": bool(force),
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        data = self._check_json(resp)
        if "access_token" not in data:
            raise WeChatError(
                int(data.get("errcode", -1)),
                data.get("errmsg", f"stable_token 响应缺少 access_token: {data}"),
                errcode_hint(int(data.get("errcode", -1)), data.get("errmsg", "")),
            )
        self._token = data["access_token"]
        self._token_expires = now + int(data.get("expires_in", 7200)) - TOKEN_EARLY_EXPIRY
        self._save_token_cache()
        return self._token

    def _load_token_cache(self) -> tuple[str, float] | None:
        try:
            data = json.loads(self.token_path.read_text(encoding="utf-8"))
            rec = data.get(self.appid)
            if rec:
                return rec["token"], rec["expires"]
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def _save_token_cache(self) -> None:
        try:
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            data: dict = {}
            try:
                data = json.loads(self.token_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            data[self.appid] = {"token": self._token, "expires": self._token_expires}
            tmp = self.token_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.chmod(tmp, 0o600)
            tmp.replace(self.token_path)
        except OSError:
            pass  # 缓存写失败不致命，仅多取一次 token

    # ---- 请求基础设施 ----

    def _check_json(self, resp: requests.Response) -> dict:
        if resp.status_code >= 500:
            raise WeChatError(-1, f"HTTP {resp.status_code}（微信服务端错误），请稍后重试")
        # 微信返回 UTF-8 JSON 但常不带 charset 声明，requests 会按 Latin-1 解码导致乱码
        resp.encoding = "utf-8"
        try:
            return resp.json()
        except ValueError:
            snippet = resp.text[:120].replace("\n", " ")
            raise WeChatError(
                -1,
                f"微信返回非 JSON 响应（疑似网络劫持或代理问题）: {snippet!r}",
                "wxmp 对 api.weixin.qq.com 默认直连；若配置了 api_proxy 请确认代理可用",
            ) from None

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json_body: dict | None = None, files: dict | None = None,
                 _retried: bool = False) -> dict:
        base_params = dict(params or {})
        base_params["access_token"] = self.get_access_token()
        # 关键：微信要求 JSON 直接传 UTF-8 字符串，勿用 \uXXXX 转义
        # （requests 的 json= 默认 ensure_ascii=True，中文会变 二 字面文本）
        data = None
        headers = None
        if json_body is not None:
            data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json"}
        resp = self.session.request(
            method, f"{API_BASE}{path}", params=base_params,
            data=data, headers=headers, files=files, timeout=30,
        )
        data = self._check_json(resp)
        errcode = data.get("errcode", 0)
        if errcode:
            if errcode in (40001, 42001) and not _retried:
                self.get_access_token(force=True)
                return self._request(method, path, params=params, json_body=json_body,
                                     files=files, _retried=True)
            raise WeChatError(errcode, data.get("errmsg", ""),
                              errcode_hint(errcode, data.get("errmsg", "")))
        return data

    # ---- 素材 ----

    def upload_content_image(self, payload: bytes, filename: str) -> str:
        """正文图片：仅 jpg/png <1MB，返回 mmbiz url，不占素材库限额。"""
        ctype = "image/png" if filename.endswith(".png") else "image/jpeg"
        data = self._request(
            "POST", "/cgi-bin/media/uploadimg",
            files={"media": (filename, payload, ctype)},
        )
        if "url" not in data:
            raise WeChatError(-1, f"uploadimg 响应缺少 url: {data}")
        return data["url"]

    def add_material(self, payload: bytes, filename: str) -> tuple[str, str]:
        """永久素材（封面用）：返回 (media_id, url)。"""
        ctype = "image/png" if filename.endswith(".png") else "image/jpeg"
        data = self._request(
            "POST", "/cgi-bin/material/add_material",
            params={"type": "image"},
            files={"media": (filename, payload, ctype)},
        )
        if "media_id" not in data:
            raise WeChatError(-1, f"add_material 响应缺少 media_id: {data}")
        return data["media_id"], data.get("url", "")

    # ---- 草稿 ----

    def draft_add(self, article: dict) -> str:
        data = self._request("POST", "/cgi-bin/draft/add",
                             json_body={"articles": [article]})
        if "media_id" not in data:
            raise WeChatError(-1, f"draft/add 响应缺少 media_id: {data}")
        return data["media_id"]

    def draft_update(self, media_id: str, article: dict, index: int = 0) -> None:
        """更新已有草稿。注意 articles 是单对象（与新增的数组不同），index 定位篇目。"""
        self._request("POST", "/cgi-bin/draft/update",
                      json_body={"media_id": media_id, "index": index,
                                 "articles": article})

    def draft_count(self) -> int:
        return int(self._request("GET", "/cgi-bin/draft/count").get("total_count", 0))

    def draft_batchget(self, offset: int = 0, count: int = 5,
                       no_content: bool = True) -> dict:
        return self._request("POST", "/cgi-bin/draft/batchget",
                             json_body={"offset": offset, "count": count,
                                        "no_content": 1 if no_content else 0})

    def draft_delete(self, media_id: str) -> None:
        self._request("POST", "/cgi-bin/draft/delete", json_body={"media_id": media_id})
