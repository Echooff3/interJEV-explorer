"""The snippet library: real markup that JEV picks between.

The writer model never produces HTML here. Every tag and every CSS rule comes
from this file; the model only fills the text slots a component declares. That
takes page structure off the router and makes a site's look a function of
JEV's typed answers rather than of whatever model happened to serve the call.

A component is an HTML template with {slot} placeholders. Each slot named in
`slots` is rendered as a shimmer placeholder first and hydrated when its copy
arrives. Slots suffixed with a number are repeats of the same idea.
"""

# --- theme -----------------------------------------------------------------
# palette (from JEV's `palette` choice) -> CSS custom properties.
PALETTES = {
    "stark_light": {
        "bg": "#ffffff", "fg": "#14161a", "muted": "#606775", "rule": "#e3e6ea",
        "accent": "#0b5fd0", "card": "#f7f8fa", "shadow": "0 1px 2px rgba(0,0,0,.06)",
    },
    "warm_paper": {
        "bg": "#faf6ef", "fg": "#2b2418", "muted": "#7a6a52", "rule": "#e4dac6",
        "accent": "#9a5b1f", "card": "#f3ebdd", "shadow": "0 1px 2px rgba(120,90,40,.10)",
    },
    "dark_mode": {
        "bg": "#14161b", "fg": "#e7e9ee", "muted": "#9aa2b1", "rule": "#2a2e37",
        "accent": "#5aa9ff", "card": "#1c1f26", "shadow": "0 1px 2px rgba(0,0,0,.5)",
    },
    "brand_saturated": {
        "bg": "#ffffff", "fg": "#141a2e", "muted": "#5b6480", "rule": "#dfe3ef",
        "accent": "#5b21d6", "card": "#f2f0ff", "shadow": "0 2px 6px rgba(91,33,214,.12)",
    },
    "garish": {
        "bg": "#fffbe6", "fg": "#10007a", "muted": "#7a2f00", "rule": "#ff8a00",
        "accent": "#d5006d", "card": "#e8ffe8", "shadow": "2px 2px 0 #10007a",
    },
    "newsprint": {
        "bg": "#fdfdfb", "fg": "#1a1a1a", "muted": "#5f5f5f", "rule": "#c9c9c4",
        "accent": "#333333", "card": "#f4f4f0", "shadow": "none",
    },
    "pastel_soft": {
        "bg": "#fdf7fb", "fg": "#3d3350", "muted": "#8a7fa0", "rule": "#ecdff0",
        "accent": "#c084c8", "card": "#f7eefa", "shadow": "0 2px 10px rgba(180,140,200,.15)",
    },
    "neon_terminal": {
        "bg": "#05070a", "fg": "#33ff9e", "muted": "#1f9c68", "rule": "#123a2a",
        "accent": "#4df3ff", "card": "#0a1016", "shadow": "0 0 8px rgba(51,255,158,.25)",
    },
    "geocities": {
        "bg": "#000080", "fg": "#ffff00", "muted": "#00ffcc", "rule": "#ff00ff",
        "accent": "#00ff00", "card": "#800080", "shadow": "3px 3px 0 #ff0000",
        "extra": """
body { background-image:
    repeating-linear-gradient(45deg,#000080 0 12px,#1a1aa0 12px 24px),
    radial-gradient(circle at 20% 30%,#fff 0 1px,transparent 1px);
  background-size:34px 34px,90px 90px; text-align:center;
  font-family:"Comic Sans MS","Chalkboard SE",cursive; }
.wrap { background:#800080; border:6px ridge #00ff00; padding:14px; }
h1 { color:#ff0; text-shadow:2px 2px 0 #f0f,-2px -2px 0 #0ff;
  background:linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f);
  -webkit-background-clip:text; letter-spacing:.04em; }
h2 { color:#0f0; text-decoration:underline wavy #ff0; }
a { color:#00ffff; font-weight:700; }
a:visited { color:#ff00ff; }
hr { border:0; height:6px; background:repeating-linear-gradient(90deg,#f00 0 10px,#ff0 10px 20px,#0f0 20px 30px); }
.card,.note { border:4px outset #0ff; background:#004040; }
.byline,.tagline,.footer { color:#0ff; }
.kicker { color:#ff0; background:#f0f; display:inline-block; padding:2px 8px; }
.counter { background:#000; color:#0f0; border:2px inset #888; }
@keyframes jevblink { 50% { opacity:.15; } }
@keyframes jevslide { from { transform:translateX(100%); } to { transform:translateX(-100%); } }
.construction, .note strong { animation:jevblink 1s steps(1) infinite; color:#ff0 !important; }
.masthead { overflow:hidden; }
.masthead .tagline { display:inline-block; white-space:nowrap;
  animation:jevslide 11s linear infinite; }
[data-slot] { color:inherit; }
""",
    },
}

# era (JEV's fractional `era` score, rounded) -> typography and chrome.
ERAS = {
    0: {  # 1996
        "font": 'Times New Roman, Times, serif', "h_font": 'Times New Roman, serif',
        "radius": "0", "maxw": "760px", "border": "2px outset", "h1": "30px",
        "base": "16px", "lh": "1.35", "gap": "10px", "caps": "none",
    },
    1: {  # 2008
        "font": '"Lucida Grande", Tahoma, Verdana, sans-serif', "h_font": '"Trebuchet MS", sans-serif',
        "radius": "6px", "maxw": "900px", "border": "1px solid", "h1": "30px",
        "base": "13px", "lh": "1.5", "gap": "14px", "caps": "none",
    },
    2: {  # 2026
        "font": 'system-ui, -apple-system, "Segoe UI", sans-serif', "h_font": 'inherit',
        "radius": "10px", "maxw": "720px", "border": "1px solid", "h1": "42px",
        "base": "17px", "lh": "1.65", "gap": "22px", "caps": "none",
    },
}


def stylesheet(palette: str, era_level: int, text_density: float) -> str:
    p = PALETTES.get(palette) or PALETTES["stark_light"]
    e = ERAS.get(era_level) or ERAS[2]
    # Denser text means tighter leading and a wider measure.
    lh = round(float(e["lh"]) - 0.12 * max(0.0, text_density - 1.0), 2)
    extra = p.get("extra", "")
    return f"""
:root {{
  --bg:{p['bg']}; --fg:{p['fg']}; --muted:{p['muted']}; --rule:{p['rule']};
  --accent:{p['accent']}; --card:{p['card']}; --shadow:{p['shadow']};
  --radius:{e['radius']}; --maxw:{e['maxw']}; --gap:{e['gap']};
}}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg);
  font:{e['base']}/{lh} {e['font']}; }}
.wrap {{ max-width:var(--maxw); margin:0 auto; padding:0 18px; }}
a {{ color:var(--accent); }}
h1,h2,h3 {{ font-family:{e['h_font']}; line-height:1.15; margin:0 0 .4em; }}
h1 {{ font-size:{e['h1']}; letter-spacing:-.015em; }}
h2 {{ font-size:1.35em; }}
p {{ margin:0 0 1em; }}
hr {{ border:0; border-top:1px solid var(--rule); margin:var(--gap) 0; }}
.masthead {{ border-bottom:{e['border']} var(--rule); padding:18px 0; }}
.masthead .row {{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
.brandname {{ font-family:{e['h_font']}; font-weight:700; font-size:1.7em; letter-spacing:-.02em; }}
.tagline {{ color:var(--muted); font-size:.85em; }}
nav.bar {{ display:flex; gap:16px; flex-wrap:wrap; padding:10px 0; border-bottom:1px solid var(--rule);
  font-size:.9em; text-transform:uppercase; letter-spacing:.06em; }}
nav.bar a {{ text-decoration:none; }}
nav.side {{ display:flex; flex-direction:column; gap:8px; }}
.layout {{ display:grid; gap:calc(var(--gap) * 1.4); padding:var(--gap) 0; }}
.layout.sidebar_left {{ grid-template-columns: 220px minmax(0,1fr); }}
.layout.sidebar_right {{ grid-template-columns: minmax(0,1fr) 260px; }}
.layout.magazine_grid > .main {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:var(--gap); }}
@media (max-width:700px) {{ .layout {{ grid-template-columns:1fr !important; }} }}
.kicker {{ color:var(--accent); text-transform:uppercase; letter-spacing:.1em; font-size:.75em; font-weight:700; }}
.standfirst {{ font-size:1.15em; color:var(--muted); }}
.byline {{ color:var(--muted); font-size:.85em; padding:10px 0; border-top:1px solid var(--rule);
  border-bottom:1px solid var(--rule); margin-bottom:var(--gap); }}
.card {{ background:var(--card); border:{e['border']} var(--rule); border-radius:var(--radius);
  padding:14px; box-shadow:var(--shadow); }}
.note {{ background:var(--card); border-left:3px solid var(--accent); padding:12px 14px;
  border-radius:var(--radius); margin:var(--gap) 0; }}
.comments li {{ list-style:none; border-top:1px solid var(--rule); padding:12px 0; }}
.comments ul {{ padding:0; margin:0; }}
.cname {{ font-weight:700; }}
.ctime {{ color:var(--muted); font-size:.8em; margin-left:6px; }}
.footer {{ border-top:1px solid var(--rule); margin-top:var(--gap); padding:18px 0;
  color:var(--muted); font-size:.85em; }}
.ad {{ border:1px dashed var(--rule); color:var(--muted); text-align:center; padding:18px;
  border-radius:var(--radius); font-size:.8em; letter-spacing:.08em; text-transform:uppercase; }}
.banner {{ position:fixed; left:0; right:0; bottom:0; background:var(--card); border-top:1px solid var(--rule);
  padding:12px 16px; display:flex; gap:12px; align-items:center; justify-content:center;
  flex-wrap:wrap; font-size:.9em; box-shadow:var(--shadow); }}
.btn {{ background:var(--accent); color:#fff; border:0; border-radius:var(--radius);
  padding:8px 14px; font:inherit; cursor:pointer; text-decoration:none; display:inline-block; }}
.counter {{ font-family:ui-monospace,Menlo,monospace; background:var(--fg); color:var(--bg);
  padding:2px 8px; border-radius:3px; letter-spacing:.2em; }}
.share a {{ display:inline-block; margin-right:10px; font-size:.85em; }}
{extra}

/* Suspense: every slot is a shimmer until its copy streams in. */
[data-slot]:empty:not(.done)::after {{
  content:""; display:inline-block; width:var(--w,100%); height:1em; vertical-align:-.15em;
  border-radius:4px; background:linear-gradient(90deg,var(--rule) 25%,var(--card) 50%,var(--rule) 75%);
  background-size:220% 100%; animation:jevshim 1.15s ease-in-out infinite;
}}
@keyframes jevshim {{ from {{ background-position:220% 0; }} to {{ background-position:-20% 0; }} }}
@media (prefers-reduced-motion:reduce) {{ [data-slot]:empty:not(.done)::after {{ animation:none; }} }}
[data-slot] {{ transition:opacity .18s ease; }}
[data-slot].settled {{ animation:jevfade .25s ease; }}
@keyframes jevfade {{ from {{ opacity:.25; }} to {{ opacity:1; }} }}
"""


def _slot(key: str, width: str = "", tag: str = "span") -> str:
    style = f' style="--w:{width}"' if width else ""
    return f'<{tag} data-slot="{key}"{style}></{tag}>'


# --- components ------------------------------------------------------------
# Each entry: variant key -> {"label": for JEV, "slots": [...], "html": template}
# Templates use {slot_key} which is replaced by a shimmer placeholder.

COMPONENTS = {
    "masthead": {
        "wordmark": {
            "label": "A large wordmark with a tagline underneath and a date line",
            "slots": ["site_name", "tagline", "dateline"],
            "html": """<header class="masthead"><div class="wrap"><div class="row">
<div><div class="brandname">{site_name}</div><div class="tagline">{tagline}</div></div>
<div class="tagline">{dateline}</div></div></div></header>""",
        },
        "compact": {
            "label": "A small single-line brand bar, name on the left only",
            "slots": ["site_name", "dateline"],
            "html": """<header class="masthead"><div class="wrap"><div class="row">
<div class="brandname">{site_name}</div><div class="tagline">{dateline}</div>
</div></div></header>""",
        },
    },
    "nav": {
        "horizontal": {
            "label": "A horizontal row of section links under the masthead",
            "slots": ["nav_1", "nav_2", "nav_3", "nav_4", "nav_5"],
            "html": """<div class="wrap"><nav class="bar">
<a href="/">{nav_1}</a><a href="/section-2">{nav_2}</a><a href="/section-3">{nav_3}</a>
<a href="/section-4">{nav_4}</a><a href="/section-5">{nav_5}</a></nav></div>""",
        },
        "none": {"label": "No navigation bar at all", "slots": [], "html": ""},
    },
    "article": {
        "standard": {
            "label": "Kicker, headline, standfirst, byline, then body paragraphs",
            "slots": ["kicker", "headline", "standfirst", "byline", "body_1", "body_2", "body_3", "body_4"],
            "html": """<article>
<div class="kicker">{kicker}</div>
<h1>{headline}</h1>
<p class="standfirst">{standfirst}</p>
<div class="byline">{byline}</div>
<p>{body_1}</p><p>{body_2}</p>
<h2>{subhead}</h2>
<p>{body_3}</p><p>{body_4}</p>
</article>""",
            "extra_slots": ["subhead"],
        },
        "plain": {
            "label": "Just a headline and body paragraphs, no kicker or standfirst",
            "slots": ["headline", "body_1", "body_2", "body_3"],
            "html": """<article><h1>{headline}</h1>
<p>{body_1}</p><p>{body_2}</p><p>{body_3}</p></article>""",
        },
    },
    "related": {
        "cards": {
            "label": "A row of cards linking to other pages on this site",
            "slots": ["related_1", "related_2", "related_3"],
            "html": """<section><h2>More from this site</h2>
<div class="layout magazine_grid"><div class="main">
<div class="card"><a href="/story-a">{related_1}</a></div>
<div class="card"><a href="/story-b">{related_2}</a></div>
<div class="card"><a href="/story-c">{related_3}</a></div>
</div></div></section>""",
        },
        "list": {
            "label": "A simple bulleted list of links",
            "slots": ["related_1", "related_2", "related_3"],
            "html": """<section><h2>Related</h2><ul>
<li><a href="/story-a">{related_1}</a></li>
<li><a href="/story-b">{related_2}</a></li>
<li><a href="/story-c">{related_3}</a></li></ul></section>""",
        },
    },
    "comments": {
        "threaded": {
            "label": "A comments section with named commenters and timestamps",
            "slots": ["c1_name", "c1_text", "c2_name", "c2_text", "c3_name", "c3_text"],
            "html": """<section class="comments"><h2>Comments</h2><ul>
<li><span class="cname">{c1_name}</span><span class="ctime">3 hours ago</span><p>{c1_text}</p></li>
<li><span class="cname">{c2_name}</span><span class="ctime">yesterday</span><p>{c2_text}</p></li>
<li><span class="cname">{c3_name}</span><span class="ctime">2 days ago</span><p>{c3_text}</p></li>
</ul><form method="post" action="/comment"><p><textarea name="body" rows="3" cols="40"
placeholder="Add a comment"></textarea></p><button class="btn" type="submit">Post comment</button></form></section>""",
        },
    },
    "newsletter": {
        "inline": {
            "label": "An inline email signup box with its own pitch",
            "slots": ["news_title", "news_pitch"],
            "html": """<section class="note"><h2>{news_title}</h2><p>{news_pitch}</p>
<form method="post" action="/subscribe"><input name="email" placeholder="you@example.com">
<button class="btn" type="submit">Subscribe</button></form></section>""",
        },
    },
    "paywall": {
        "metered": {
            "label": "A metered-article prompt interrupting the page",
            "slots": ["pay_title", "pay_body"],
            "html": """<section class="card"><h2>{pay_title}</h2><p>{pay_body}</p>
<a class="btn" href="/subscribe">See subscription options</a></section>""",
        },
    },
    "cookie_banner": {
        "bottom": {
            "label": "A consent banner fixed to the bottom of the viewport",
            "slots": ["cookie_text"],
            "html": """<div class="banner"><span>{cookie_text}</span>
<a class="btn" href="/privacy?consent=all">Accept all</a>
<a href="/privacy">Manage</a></div>""",
        },
    },
    "hit_counter": {
        "classic": {
            "label": "A visitor counter and last-updated stamp in the footer",
            "slots": ["counter_note"],
            "html": """<p>{counter_note} &mdash; visitors: <span class="counter">0041287</span></p>""",
        },
    },
    "social_share": {
        "links": {
            "label": "A row of share links for invented social networks",
            "slots": ["share_1", "share_2", "share_3"],
            "html": """<div class="share"><a href="/share/a">{share_1}</a>
<a href="/share/b">{share_2}</a><a href="/share/c">{share_3}</a></div>""",
        },
    },
    "account": {
        "header_links": {
            "label": "A sign-in and register pair in the header area",
            "slots": ["account_label"],
            "html": """<div class="wrap" style="text-align:right;padding:6px 18px;font-size:.85em">
<a href="/login">{account_label}</a> &middot; <a href="/register">Register</a></div>""",
        },
    },
    "construction": {
        "notice": {
            "label": "An 'under construction' notice built from CSS",
            "slots": ["construction_note"],
            "html": """<div class="note"><strong>&#9888; {construction_note}</strong></div>""",
        },
    },
    "ads": {
        "leaderboard": {
            "label": "A wide banner ad slot above the content",
            "slots": ["ad_label"],
            "html": """<div class="wrap"><div class="ad">{ad_label}</div></div>""",
        },
    },
    "sidebar": {
        "links": {
            "label": "A sidebar of section links and a small blurb",
            "slots": ["side_title", "side_1", "side_2", "side_3", "side_blurb"],
            "html": """<aside><div class="card"><h2>{side_title}</h2>
<nav class="side"><a href="/a">{side_1}</a><a href="/b">{side_2}</a><a href="/c">{side_3}</a></nav>
<hr><p>{side_blurb}</p></div></aside>""",
        },
    },
    "footer": {
        "columns": {
            "label": "A footer with a short about line and legal links",
            "slots": ["foot_about", "foot_legal"],
            "html": """<footer class="footer"><div class="wrap"><p>{foot_about}</p>
<p><a href="/about">About</a> &middot; <a href="/contact">Contact</a> &middot;
<a href="/privacy">Privacy</a></p><p>{foot_legal}</p>{hit_counter}</div></footer>""",
        },
    },
}

# Which components JEV is asked to pick a variant for (others have one variant).
VARIANT_QUESTIONS = {
    "masthead": "Which masthead would this site use?",
    "nav": "Which navigation would this site use?",
    "article": "How would this page present its main content?",
    "related": "How would this site present links to its other pages?",
}
