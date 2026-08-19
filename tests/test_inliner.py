from wxmp.inliner import inline_css


def test_basic_tag_selector():
    out = inline_css("<p>hi</p>", "p { color: red; }")
    assert 'style="color:red"' in out


def test_class_and_tag_class():
    out = inline_css('<p class="note">a</p><p>b</p>', "p.note { color: red; }")
    assert 'style="color:red"' in out
    assert '<p>b</p>' in out


def test_descendant_and_child():
    html = "<blockquote><p>x</p></blockquote><section><p>y</p></section>"
    out = inline_css(html, "blockquote p { color: red; }")
    # blockquote 里外的 p 都不带样式（section 未命中规则）
    assert out.count('style="color:red"') == 1

    out2 = inline_css(html, "blockquote > p { color: red; }")
    assert out2.count('style="color:red"') == 1


def test_comma_group():
    out = inline_css("<h1>a</h1><h2>b</h2>", "h1, h2 { color: red; }")
    assert out.count("color:red") == 2


def test_specificity_order():
    # .x 规则在前，但 tag 规则 specificity 低，class 胜出
    html = '<p class="x">t</p>'
    out = inline_css(html, "p { color: blue; }\np.x { color: red; }")
    assert "color:red" in out and "color:blue" not in out
    # 同 specificity 时源顺序后者覆盖
    out2 = inline_css(html, "p { color: blue; }\np { color: red; }")
    assert "color:red" in out2 and "color:blue" not in out2


def test_existing_inline_style_wins():
    # 元素原有内联 style 覆盖主题（保 pygments token 颜色的关键）
    out = inline_css('<span style="color:#123456">x</span>', "span { color: red; }")
    assert "color:#123456" in out and "color:red" not in out


def test_shorthand_orders_before_longhand():
    out = inline_css('<p>x</p>', "p { margin-top: 1px; margin: 2px; }")
    style = out.split('style="')[1].split('"')[0]
    assert style.index("margin:") < style.index("margin-top:")


def test_unsupported_selector_warns_and_skips():
    warned = []
    out = inline_css("<p>x</p>", "p:hover { color: red; }", on_warning=warned.append)
    assert warned and "style=" not in out


def test_at_rule_skipped():
    warned = []
    out = inline_css("<p>x</p>", "@media screen { p { color: red; } }", on_warning=warned.append)
    assert warned and "style=" not in out
