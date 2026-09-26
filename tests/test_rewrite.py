from interjev.rewrite import Rewriter, StreamRewriter, to_fake, to_local


def test_to_local_and_back():
    assert to_local("https://www.acme.com/a/b?x=1") == "/site/www.acme.com/a/b?x=1"
    assert to_local("acme.com") == "/site/acme.com/"
    assert to_local("ftp://acme.com") is None
    assert to_fake("www.acme.com", "a/b", "x=1") == "https://www.acme.com/a/b?x=1"


def test_rewrites_links_forms_and_images():
    rw = Rewriter("https://shop.example-widgets.com/products/list")
    out = rw.rewrite(
        '<a href="/about" target="_blank">About</a>'
        '<a href="detail?id=3&amp;c=2">Detail</a>'
        "<a href='https://other-site.org/news'>Other</a>"
        '<a href="#top">Top</a><a href="mailto:hi@x.com">Mail</a>'
        '<form method="post" action="/cart/add"><input name="sku"></form>'
        '<img src="/img/logo.png" alt="Widget Co logo" srcset="a.png 2x" />'
    )
    assert 'href="/site/shop.example-widgets.com/about"' in out
    assert "target" not in out
    assert 'href="/site/shop.example-widgets.com/products/detail?id=3&amp;c=2"' in out
    assert 'href="/site/other-site.org/news"' in out
    assert 'href="#top"' in out and 'href="mailto:hi@x.com"' in out
    assert 'action="/site/shop.example-widgets.com/cart/add"' in out
    assert 'src="/placeholder.svg?text=Widget+Co+logo"' in out
    assert "srcset" not in out


def test_stream_rewriter_handles_split_tags_and_fences():
    page = '```html\n<!DOCTYPE html><html><body><a href="/deep/page">Go</a><p>x &gt; y</p></body></html>\n```'
    sr = StreamRewriter("https://a-site.net/")
    out = "".join(sr.feed(page[i : i + 7]) for i in range(0, len(page), 7)) + sr.finish()
    assert out.startswith("<!DOCTYPE html>")
    assert out.endswith("</html>")
    assert 'href="/site/a-site.net/deep/page"' in out
    assert sr.html == out
