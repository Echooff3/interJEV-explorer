"""Keep the visitor inside interJEV.

Generated pages link to fictional URLs like https://www.acme-widgets.com/about.
These helpers map such URLs onto local routes (/site/www.acme-widgets.com/about)
so every click and form submission comes back to JEV, and they swap image
sources for local placeholders so nothing is fetched from the real internet.
"""

import html
import re
from urllib.parse import quote, urlencode, urljoin, urlsplit

SKIP_SCHEMES = ("#", "javascript:", "data:", "mailto:", "tel:", "about:", "blob:")

_TAG_RE = re.compile(r"<(a|area|form|img)\b([^>]*)>", re.IGNORECASE)
_ATTR_RE = re.compile(
    r"""(\s)([a-zA-Z_:][-a-zA-Z0-9_:.]*)(\s*=\s*("[^"]*"|'[^']*'|[^\s>]+))?"""
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.IGNORECASE | re.DOTALL)
_FENCE_RE = re.compile(r"\s*```[a-zA-Z]*\s*$")


def normalize_url(url: str) -> str | None:
    """Turn user or model input into an absolute https URL, or None if it isn't web-ish."""
    url = url.strip()
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)", url):  # "host:8080" is not a scheme
        url = "https://" + url
    parts = urlsplit(url)
    try:
        parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    return url


def to_local(url: str) -> str | None:
    """https://host/path?q=1 -> /site/host/path?q=1"""
    url = normalize_url(url)
    if url is None:
        return None
    parts = urlsplit(url)
    host = parts.hostname.lower()
    if parts.port:
        host = f"{host}:{parts.port}"
    local = f"/site/{host}{quote(parts.path or '/', safe='/%:@!$&()*+,;=-._~')}"
    if parts.query:
        local += "?" + parts.query
    return local


def to_fake(host: str, path: str, query: str = "") -> str:
    """Inverse of to_local: rebuild the fictional URL the visitor is 'on'."""
    url = f"https://{host}/{path.lstrip('/')}"
    if query:
        url += "?" + query
    return url


def placeholder_src(alt: str, src: str) -> str:
    label = alt.strip() or src.rsplit("/", 1)[-1].split("?")[0] or "image"
    return "/placeholder.svg?" + urlencode({"text": label[:80]})


class Rewriter:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def resolve(self, href: str) -> str | None:
        href = href.strip()
        if not href or href.lower().startswith(SKIP_SCHEMES):
            return None
        return to_local(urljoin(self.base_url, href))

    def _rewrite_tag(self, match: re.Match) -> str:
        tag, attrs = match.group(1), match.group(2)
        tag_l = tag.lower()
        self_closing = attrs.rstrip().endswith("/")
        if self_closing:
            attrs = attrs.rstrip()[:-1]

        parsed: list[tuple[str, str | None]] = []
        for m in _ATTR_RE.finditer(attrs):
            name, raw = m.group(2), m.group(4)
            if raw is not None and raw[:1] in "\"'":
                raw = raw[1:-1]
            parsed.append((name, html.unescape(raw) if raw is not None else None))

        alt = next((v for k, v in parsed if k.lower() == "alt" and v), "")
        out = []
        for name, value in parsed:
            key = name.lower()
            if key == "target" and tag_l in ("a", "area", "form"):
                continue  # keep navigation inside the interJEV frame
            if value is not None and key in ("href", "action") and tag_l in ("a", "area", "form"):
                value = self.resolve(value) or value
            elif value is not None and key == "src" and tag_l == "img":
                if not value.startswith("data:"):
                    value = placeholder_src(alt, value)
            elif key in ("srcset",) and tag_l == "img":
                continue
            if value is None:
                out.append(f" {name}")
            else:
                out.append(f' {name}="{html.escape(value, quote=True)}"')
        return f"<{tag}{''.join(out)}{' /' if self_closing else ''}>"

    def rewrite(self, fragment: str) -> str:
        return _TAG_RE.sub(self._rewrite_tag, fragment)


class StreamRewriter:
    """Rewrite HTML as it streams in, only ever touching complete tags.

    Also drops anything before the first '<' (e.g. a ```html fence) and a
    trailing fence at the end.
    """

    def __init__(self, base_url: str):
        self.rewriter = Rewriter(base_url)
        self.buf = ""
        self.started = False
        self.raw = []  # everything emitted, for caching

    def _emit(self, text: str) -> str:
        out = self.rewriter.rewrite(text)
        self.raw.append(out)
        return out

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        if not self.started:
            i = self.buf.find("<")
            if i == -1:
                return ""
            self.buf = self.buf[i:]
            self.started = True
        cut = self.buf.rfind(">")
        if cut == -1:
            return ""
        text, self.buf = self.buf[: cut + 1], self.buf[cut + 1 :]
        return self._emit(text)

    def finish(self) -> str:
        rest = _FENCE_RE.sub("", self.buf) if self.started else ""
        self.buf = ""
        return self._emit(rest) if rest else ""

    @property
    def html(self) -> str:
        return "".join(self.raw)


def extract_title(page: str) -> str:
    m = _TITLE_RE.search(page)
    return html.unescape(m.group(1)).strip()[:120] if m else ""


def extract_stylesheet(page: str, limit: int = 4000) -> str:
    css = "\n".join(s.strip() for s in _STYLE_RE.findall(page))
    return css[:limit]
