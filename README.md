# interJEV Explorer

A browser for an internet that doesn't exist. Nothing here is a real website:
you search, **JEV** makes up the results, and when you click one JEV writes
that site's HTML on the spot. Every link on a generated page leads to another
generated page. It's the same idea as the VibeOS demo, applied to the web.

```
┌ interJEV ← → ↻ ⌂ [ https://www.snailweekly.net/2026/finals ] ✨ ┐
│                                                                  │
│   page HTML streamed from JEV, links rewritten back to JEV       │
└──────────────────────────────────────────────────────────────────┘
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in OPENROUTER_API_KEY and JEV_MODEL
python -m interjev          # http://127.0.0.1:5000
```

JEV runs on [OpenRouter](https://openrouter.ai). Set `JEV_MODEL` to the
OpenRouter model id you want JEV to use (it's on the model's page, e.g.
`provider/model-name`).

To try the UI without an API key, run `JEV_MOCK=1 python -m interjev`, which
serves canned responses.

## How it works

| Route | What happens |
| --- | --- |
| `/` | Browser shell: address bar, back/forward/reload/home, ✨ regenerate, and an iframe. |
| `/home` | The interJEV search page (static). |
| `/results?q=` | Results page. It calls `/api/search`, where JEV returns results as JSON. |
| `/site/<host>/<path>` | JEV writes the page for `https://<host>/<path>` and streams it to the browser as it's generated. |
| `/go?u=` | Handles the address bar: a URL goes to that site, anything else is searched. |
| `/lucky?q=` | "I'm Feeling Vibey": goes straight to the first result. |

- **Links stay inside interJEV.** `interjev/rewrite.py` rewrites every `<a href>`
  and `<form action>` while the page streams, whether the link is absolute,
  root-relative or relative. `https://foo.com/bar` becomes `/site/foo.com/bar`.
  Image `src`s point at a generated SVG placeholder, and a Content-Security-Policy
  stops generated pages from loading anything from the real internet.
- **Forms work.** GET forms (searches, filters) turn into query strings on the
  fake URL. For POST forms (logins, comments, checkout), the submitted fields
  are passed to JEV, which writes the page that comes back.
- **Sites stay consistent.** For each site, `interjev/store.py` keeps:
  - the search snippet that led there
  - the pages you've already seen on it
  - the first page's stylesheet

  All of this goes into JEV's prompt, so later pages on the same site look and
  read like the same site. The page you came from is passed in as well.
- **Back/forward are stable.** GET pages are cached in memory, so going back
  shows the same page instead of a new one. The ✨ button discards the cached
  copy and has JEV write the page again.

Prompts live in `interjev/prompts.py`, so that's where to go to change JEV's
personality.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
