import json
from unittest.mock import MagicMock

import pytest
import requests

from wxmp.errors import WeChatError
from wxmp.wechat import WeChatClient


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def make_client(tmp_path, token_responses=None, api_responses=None):
    client = WeChatClient("wxid", "secret", token_path=tmp_path / "token.json")
    client.session = MagicMock(spec=requests.Session)
    client.session.post.side_effect = (
        token_responses or [FakeResponse({"access_token": "T1", "expires_in": 7200})]
    )
    client.session.request.side_effect = api_responses or []
    return client


def test_token_cached(tmp_path):
    client = make_client(tmp_path)
    assert client.get_access_token() == "T1"
    assert client.get_access_token() == "T1"
    assert client.session.post.call_count == 1  # 缓存生效，只取一次
    # 落盘缓存可跨实例复用
    client2 = WeChatClient("wxid", "secret", token_path=tmp_path / "token.json")
    client2.session = MagicMock(spec=requests.Session)
    assert client2.get_access_token() == "T1"
    assert client2.session.post.call_count == 0


def test_errcode_raises_with_hint(tmp_path):
    client = make_client(
        tmp_path,
        api_responses=[FakeResponse({"errcode": 40125, "errmsg": "invalid secret"})],
    )
    with pytest.raises(WeChatError) as ei:
        client.draft_count()
    assert ei.value.errcode == 40125
    assert "secret" in ei.value.hint


def test_auto_retry_on_expired_token(tmp_path):
    client = make_client(
        tmp_path,
        token_responses=[
            FakeResponse({"access_token": "T1", "expires_in": 7200}),
            FakeResponse({"access_token": "T2", "expires_in": 7200}),
        ],
        api_responses=[
            FakeResponse({"errcode": 42001, "errmsg": "access_token expired"}),
            FakeResponse({"errcode": 0, "total_count": 3}),
        ],
    )
    assert client.draft_count() == 3
    assert client.session.request.call_count == 2  # 重试了一次
    assert client.get_access_token() == "T2"


def test_40164_hint_contains_ip(tmp_path):
    client = make_client(
        tmp_path,
        api_responses=[
            FakeResponse({"errcode": 40164, "errmsg": "invalid ip 1.2.3.4 ipv6 ::ffff, not in whitelist"}),
        ],
    )
    with pytest.raises(WeChatError) as ei:
        client.draft_count()
    assert "1.2.3.4" in ei.value.hint and "白名单" in ei.value.hint


def test_non_json_response(tmp_path):
    resp = FakeResponse(None)
    client = make_client(tmp_path, api_responses=[resp])
    with pytest.raises(WeChatError, match="非 JSON"):
        client.draft_count()


def test_request_body_not_unicode_escaped(tmp_path):
    """微信要求 JSON 直接传 UTF-8（勿 \\uXXXX 转义，否则中文变字面转义文本）。"""
    client = make_client(
        tmp_path,
        api_responses=[FakeResponse({"errcode": 0, "media_id": "M"})],
    )
    client.draft_add({"title": "中文标题", "content": "<p>正文</p>",
                      "thumb_media_id": "T"})
    kwargs = client.session.request.call_args.kwargs
    body = kwargs["data"]
    assert isinstance(body, bytes)
    assert "中文标题".encode("utf-8") in body
    assert b"\\u" not in body
    assert kwargs["headers"]["Content-Type"] == "application/json"
