# interJEV Explorer

A browser for an internet that doesn't exist. Nothing here is a real website:
you search, **JEV** makes up the results, and when you click one JEV writes
that site's HTML on the spot. Every link on a generated page leads to another
generated page. It's the same idea as the VibeOS demo, applied to the web.

```
┌ Ĵ interJEV Explorer ← → ↻ ⌂  Address [ https://www.snailweekly.net/2026/finals ] ✨ ┐
│ interJEV Explorer is not currently your default browser...            [Yes] [No]  │
│                                                                                   │
│   page HTML streamed from JEV, links rewritten back to JEV                        │
│                                                                                   │
│ Done                                    🌐 interJEV | Protected Mode: On  🔍 100% │
└───────────────────────────────────────────────────────────────────────────────────┘
```

A few nods to Internet Explorer, the browser of yesteryear, are built in:

- The logo is a blue italic **J** with a gold orbit ring. The ring spins while
  a page loads, like IE's old throbber.
- An IE-style status bar at the bottom says "Waiting for …", "Opening page …"
  and "Done". It shows a link's fake URL when you hover over it, and ends with
  the "🌐 interJEV | Protected Mode: On" zone and 🔍 100% zoom.
- The window title reads "Page Title - interJEV Explorer".
- The first time you open it, it asks whether you'd like to make interJEV
  Explorer your default browser.
- On startup, a "Security Alert" dialog asks visitors whether their session
  may be recorded, with **Yes, record** and **No, don't record** buttons.
- When JEV can't be reached, you get "interJEV Explorer cannot display the
  webpage" with "Most likely causes" and a **Diagnose Connection Problems**
  button.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in OPENROUTER_API_KEY and JEV_MODEL
python -m interjev          # http://127.0.0.1:5000
```

`python -m interjev` runs gunicorn. Add `--dev` to use Flask's development
server instead (Windows always uses it).

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

## The blueprint

With `JEV_BLUEPRINT=1`, the page a site serves isn't left entirely to the
writer model. Before a word of HTML is written, the URL and what's known about
the site go to JEV's [Decisions API](https://openrouter.ai/api/alpha/decisions),
which answers a fixed set of typed questions. Those answers are injected into
the writer's prompt as art direction it must follow.

Each question type does a different job:

| Type | Used for | Example |
| --- | --- | --- |
| `choice` | Things that can only be one way at a time | `archetype` → news, shop, forum, … |
| `score` | Ordered dials, read as a fraction | `era` → `1.94 / 2`, mostly 2026 modern |
| `noul` | Independent optional elements | `comments` → `0.47` |

The `noul` answers are **sampled, not thresholded**. A 0.47 on comments means
comments appear on roughly 47% of pages like that one, so the furniture varies
between pages the way a real slice of the web does, and the variation is tied
to the content rather than to `random.random()`. Each generation draws a new
seed, which is what makes ✨ regenerate produce the same site with different
bones.

Layout, colour, archetype and era are decided once per site and then inherited,
so later pages on a site look related to the first one. Advertising density,
text density and every element roll are decided per page.

Open the **⌸ JEV blueprint** panel in the status bar to watch it happen: every
question, the probability JEV assigned to each option, its confidence, and
which elements the roll let in. A blueprint costs about $0.00005 and adds
roughly 400ms before the page starts streaming. If the call fails the page is
generated the normal way.

Set `JEV_DECISIONS_MODEL` to change the decisions model (default
`~typesafe/jev-latest`). Note this is a *different* model from `JEV_MODEL`:
decisions models are served on their own endpoint and can't be used for
chat completions, or vice versa.

## Building pages from snippets

With `JEV_SNIPPETS=1` (which needs `JEV_BLUEPRINT=1`), no model writes HTML at
all. Every tag and every CSS rule comes from `interjev/components.py`, and the
model is only allowed to supply words.

1. JEV picks the page's structure *and* which markup variant each component
   uses — `variant_masthead`, `variant_article`, and so on, asked in the same
   single decisions call as everything else.
2. `interjev/assemble.py` builds the whole document from those answers in
   microseconds: layout, components, and a stylesheet derived from the
   `palette` choice and the `era` and `text_density` scores.
3. The skeleton ships immediately, with a shimmer placeholder in every text
   slot. **First byte lands in about 0.35s**, fully laid out.
4. `interjev/copy.py` asks a small, cheap model for a flat JSON object of plain
   strings — one per slot, no HTML. Pairs are parsed out of the stream as they
   complete, so each slot fills the moment its words arrive.

The first key the model returns is `_brief`, a one-sentence statement of what
the page is about. It is not rendered; it is stored as a site note so later
pages on the same site stay consistent with it.

Because the copy model never produces markup, it can be small: the default is
`deepseek/deepseek-v4-flash` at about $0.0001 a page. Set `JEV_COPY_MODEL` to
change it. Avoid reasoning models — they leak their thinking into the JSON.

What this buys you is that a page's structure no longer depends on which model
served the request, and a bad response degrades into a few unfilled slots
rather than a broken document. What it costs is variety: pages are as different
as the library is large, so adding variants to `COMPONENTS` is how the
alternate internet gets more interesting.

## Recording searches and pages

Every search and every page JEV creates is recorded, unless the visitor opts
out. Each record includes the
query or URL, the results or full HTML, the model, how long it took, any
error, and an anonymous visitor id.

- **Default:** each event is printed to the console as one JSON line starting
  with `[interjev]`. On Railway, these appear in the deploy logs.
- **`--capture`** (or `JEV_CAPTURE=1`)**:** events are written to Postgres at
  `DATABASE_URL`. The `searches` and `pages` tables are created on startup.
  Writes happen on a background thread, so pages never wait on the database.
  If a write fails, that event is printed to the console instead.

**Opting out.** The startup notice asks every visitor whether to record their
session:

- Nothing loads until they choose. If they choose **No**, the server logs
  nothing for them, either to the console or to Postgres.
- The choice is stored in a cookie that ends when the browser closes, so the
  notice asks again next time.
- While a session is being recorded, a blinking **● REC** badge shows at the
  top right. Clicking it reopens the notice so visitors can opt out partway
  through.
- A generated link opened directly in a new tab is sent back through the
  browser frame, so the notice can't be skipped that way.

### The gallery

Set `GALLERY_PASSWORD` and open `/gallery` to browse what's been recorded. It
only works with `--capture`, since it reads from Postgres. Your browser will
ask you to log in: any username works, and the password is `GALLERY_PASSWORD`.
If the variable isn't set, the gallery is turned off.

- **Main page:** totals (searches, pages, visitors), top and recent searches,
  and a grid of live previews of every page JEV has built. You can filter by
  text, by site, by the search that led there, or by visitor, which shows one
  person's whole session.
- **Page view:** the page's details (model, time taken, any form data, the
  search it came from, errors), a full-size preview, and buttons to view or
  download the HTML.

Stored pages are written by the model, so previews run in a locked-down
sandbox: their scripts can't reach the gallery or anything else on the site.
Clicking a link in a preview opens a new tab in interJEV Explorer, which starts
with the recording notice like any other visit.

To dig into the data directly, some queries to start with:

```sql
-- What are people searching for?
SELECT query, count(*) FROM searches GROUP BY query ORDER BY count DESC;

-- The latest pages JEV built, and which search led there
SELECT created_at, url, title, referrer, duration_ms FROM pages ORDER BY id DESC LIMIT 50;

-- Pull one page's HTML to look at
SELECT html FROM pages WHERE id = 42;
```

## Deploying on Railway

1. Create a project from this repo. `railway.json` sets the start command
   (`python -m interjev`) and the `/healthz` health check.
2. Add variables `OPENROUTER_API_KEY` and `JEV_MODEL`.
3. To store events in Postgres:
   - Add a **Postgres** service to the project.
   - On the app service, add the variable `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`.
   - Add `JEV_CAPTURE=1`, or change the start command to `python -m interjev --capture`.
4. Optionally set `GALLERY_PASSWORD` to turn on `/gallery`.

Without step 3, everything is still recorded to the deploy logs.

The app runs as a single process with many threads, because the page cache
and each site's memory live in memory. Don't scale it to multiple replicas.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
# optional: also test against a real Postgres (its tables get dropped)
TEST_DATABASE_URL=postgresql://localhost/interjev_test pytest
```
