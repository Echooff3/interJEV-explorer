"""Turn a JEV blueprint into a finished page skeleton, with no model involved.

This runs in microseconds and emits the whole document except the words: real
markup, real CSS, and a shimmer placeholder for every text slot. The copy model
fills those slots afterwards, so the page's structure never depends on which
model the router happened to pick.
"""

import re
from dataclasses import dataclass, field

from . import components as C

PLACEHOLDER = re.compile(r"\{([a-z0-9_]+)\}")

# Shimmer widths, so a loading page has believable proportions instead of
# a column of identical grey bars.
WIDTHS = {
    "site_name": "8em", "tagline": "16em", "dateline": "12em", "kicker": "7em",
    "headline": "95%", "standfirst": "85%", "byline": "20em", "subhead": "55%",
    "account_label": "5em", "ad_label": "10em", "counter_note": "14em",
    "news_title": "40%", "pay_title": "45%", "side_title": "60%",
    "foot_legal": "22em", "construction_note": "24em", "cookie_text": "28em",
}
WIDTH_BY_PREFIX = {
    "nav_": "5em", "share_": "6em", "related_": "80%", "side_": "70%",
    "c1_name": "8em", "c2_name": "8em", "c3_name": "8em",
}

HINTS = {
    "site_name": "the site's name (no tagline)",
    "tagline": "a short masthead tagline",
    "dateline": "a date line, e.g. 'Tuesday 14 October 2025'",
    "kicker": "a 1-3 word section label above the headline",
    "headline": "the page's headline",
    "standfirst": "a one-sentence summary under the headline",
    "byline": "a byline with an invented author name and a role",
    "subhead": "a subheading partway through the article",
    "counter_note": "a short 'last updated' line",
    "cookie_text": "one sentence of cookie-consent boilerplate",
    "construction_note": "a short 'this section is unfinished' line",
    "ad_label": "placeholder ad text, e.g. 'Advertisement'",
    "foot_about": "one sentence describing the site, for the footer",
    "foot_legal": "a copyright line",
    "account_label": "a sign-in link label",
}


@dataclass
class Assembled:
    html: str = ""
    slots: "list[tuple[str, str]]" = field(default_factory=list)  # (key, hint)
    stylesheet: str = ""
    components: "list[str]" = field(default_factory=list)  # for the inspector


def _width(key: str) -> str:
    if key in WIDTHS:
        return WIDTHS[key]
    for prefix, w in WIDTH_BY_PREFIX.items():
        if key.startswith(prefix) or key == prefix:
            return w
    return "100%"


def _render(name: str, variant: str, seen: dict, order: list) -> str:
    spec = (C.COMPONENTS.get(name) or {}).get(variant)
    if not spec:
        return ""

    def sub(match):
        key = match.group(1)
        if key in C.COMPONENTS:  # a nested component, e.g. the footer's counter
            return seen.pop("__pending_" + key, "")
        if key not in seen:
            seen[key] = True
            hint = HINTS.get(key) or f"{key.replace('_', ' ')} for the {name} block"
            order.append((key, hint))
        tag = "div" if key.startswith("body_") or key.endswith("_text") else "span"
        return f'<{tag} data-slot="{key}" style="--w:{_width(key)}"></{tag}>'

    return PLACEHOLDER.sub(sub, spec["html"])


def _variant(bp, name: str) -> str:
    variants = C.COMPONENTS[name]
    chosen = (bp.answers.get("variant_" + name) or {}).get("choice")
    return chosen if chosen in variants else next(iter(variants))


def assemble(bp, title_slot: str = "headline") -> Assembled:
    palette = (bp.answers.get("palette") or {}).get("choice") or "stark_light"
    layout = (bp.answers.get("layout") or {}).get("choice") or "single_column"
    era = int(round(float((bp.answers.get("era") or {}).get("score", 2))))
    density = float((bp.answers.get("text_density") or {}).get("score", 1))
    ads = float((bp.answers.get("ad_density") or {}).get("score", 0))
    on = {k: v["included"] for k, v in bp.elements.items()}

    seen: dict = {}
    order: list = []
    used: list = []

    def part(name, variant=None):
        variant = variant or _variant(bp, name)
        html = _render(name, variant, seen, order)
        if html:
            used.append(f"{name}:{variant}")
        return html

    # The counter lives inside the footer template, so render it first.
    if on.get("hit_counter"):
        seen["__pending_hit_counter"] = _render("hit_counter", "classic", seen, order)
        used.append("hit_counter:classic")

    head = [part("masthead")]
    if on.get("account"):
        head.append(part("account", "header_links"))
    head.append(part("nav"))
    if ads >= 0.5:
        head.append(part("ads", "leaderboard"))

    main = []
    if on.get("construction"):
        main.append(part("construction", "notice"))
    main.append(part("article"))
    if on.get("social_share"):
        main.append(part("social_share", "links"))
    if on.get("paywall"):
        main.append(part("paywall", "metered"))
    if on.get("newsletter"):
        main.append(part("newsletter", "inline"))
    if on.get("related"):
        main.append(part("related"))
    if on.get("comments"):
        main.append(part("comments", "threaded"))

    sidebar = part("sidebar", "links") if layout in ("sidebar_left", "sidebar_right") else ""
    body = f'<div class="main">{"".join(main)}</div>'
    if sidebar:
        body = (sidebar + body) if layout == "sidebar_left" else (body + sidebar)

    tail = [part("footer", "columns")]
    if on.get("cookie_banner"):
        tail.append(part("cookie_banner", "bottom"))

    css = C.stylesheet(palette, era, density)
    html = (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title></title><style>" + css + "</style></head><body>"
        + "".join(head)
        + f'<div class="wrap"><div class="layout {layout}">{body}</div></div>'
        + "".join(tail)
    )
    return Assembled(html=html, slots=order, stylesheet=css, components=used)


def variant_questions() -> dict:
    """Extra `choice` questions so JEV picks the markup, not just the mood."""
    questions = {}
    for name, instructions in C.VARIANT_QUESTIONS.items():
        questions["variant_" + name] = {
            "type": "choice",
            "instructions": instructions,
            "criteria": {k: v["label"] for k, v in C.COMPONENTS[name].items()},
        }
    return questions


EMPTY_SLOT = re.compile(r'<(span|div) data-slot="([a-z0-9_]+)"[^>]*></\1>')


def fill(html: str, values: dict, title: str = "") -> str:
    """Bake the streamed copy into the skeleton, for the back/forward cache."""
    from markupsafe import escape

    def sub(match):
        tag, key = match.group(1), match.group(2)
        value = values.get(key)
        if value is None:
            return match.group(0)
        return f'<{tag} data-slot="{key}">{escape(value)}</{tag}>'

    out = EMPTY_SLOT.sub(sub, html)
    if title:
        out = out.replace("<title></title>", f"<title>{escape(title)}</title>", 1)
    return out
