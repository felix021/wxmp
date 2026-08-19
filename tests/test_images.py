import io
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from wxmp.errors import ImageError
from wxmp.images import collect_images, normalize_image


def _png(w=50, h=50, mode="RGB"):
    img = Image.new(mode, (w, h), "#336699")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_collect_classification(tmp_path: Path):
    html = (
        '<img src="local.png"/>'
        '<img src="https://mmbiz.qpic.cn/some.jpg"/>'
        '<img src="https://example.com/a.png"/>'
        '<img src="data:image/png;base64,iVBOR"/>'
    )
    soup = BeautifulSoup(html, "html.parser")
    refs = collect_images(soup, tmp_path)
    kinds = {r.kind for r in refs}
    assert kinds == {"local", "weixin", "remote", "data"}
    local = next(r for r in refs if r.kind == "local")
    assert local.path == (tmp_path / "local.png").resolve()


def test_normalize_passthrough_small_png():
    data = _png()
    payload, ext, notes = normalize_image(data, "a.png", max_width=1080)
    assert payload == data and ext == "png"  # 合规图原样返回保画质


def test_normalize_resizes_and_converts():
    # 宽超限的无透明 PNG → 缩放 + 转 jpg（无透明统一 JPEG，体积更小）
    data = _png(w=2000, h=100)
    payload, ext, _ = normalize_image(data, "big.png", max_width=1080)
    img = Image.open(io.BytesIO(payload))
    assert img.width == 1080 and ext == "jpg"


def test_normalize_webp_converts():
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), "#123456").save(buf, "WEBP")
    payload, ext, notes = normalize_image(buf.getvalue(), "a.webp", max_width=1080)
    assert ext == "jpg" and any("webp" in n for n in notes)


def test_normalize_alpha_keeps_png():
    data = _png(mode="RGBA")
    payload, ext, notes = normalize_image(data, "a.png", max_width=1080)
    assert ext == "png"


def test_normalize_huge_image_compresses_under_limit():
    # 构造难以压缩的大图：宽超限 + 噪声，最终必须 <1MB
    import random

    random.seed(7)
    img = Image.new("RGB", (3000, 2000))
    px = img.load()
    for y in range(0, 2000, 2):
        for x in range(0, 3000, 2):
            c = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            px[x, y] = c
            if x + 1 < 3000:
                px[x + 1, y] = c
    buf = io.BytesIO()
    img.save(buf, "PNG")
    assert buf.tell() > 1024 * 1024
    payload, ext, _ = normalize_image(buf.getvalue(), "huge.png", max_width=1080)
    assert len(payload) <= 1024 * 1024


def test_normalize_svg_rejected():
    with pytest.raises(ImageError, match="SVG"):
        normalize_image(b'<svg xmlns="x"></svg>', "a.svg", max_width=100)
