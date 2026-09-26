"""interJEV Explorer: a browser for websites that JEV imagines on demand."""

import json
import random
import re
import threading
import time
import uuid
from collections import OrderedDict
from urllib.parse import urlencode, urlsplit

from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from markupsafe import escape

from . import assemble
from . import blueprint as bp
from . import copy as copywriter
from . import gallery, prompts
from .jev import JEVError, get_client
from .rewrite import (
    StreamRewriter,
    extract_stylesheet,
    extract_title,
    normalize_url,
    to_fake,
    to_local,
)
from .recorder import make_recorder
from .store import Store

# Generated pages may not reach the real internet. Inline styles/scripts and
# data: images are fine; everything else must come from this server.
SITE_CSP = (
    "default-src 'self'; style-src 'self' 'unsafe-inline'; "
    "script-src 'unsafe-inline'; img-src 'self' data:; font-src data:; "
    "connect-src 'none'; form-action 'self'; frame-ancestors 'self'"
)


# Hydration for the snippet pipeline: the skeleton ships first, then each slot
# is filled as its copy finishes streaming.
HYDRATE_JS = """<script>
function __j(k,v){var n=document.querySelectorAll('[data-slot="'+k+'"]');
for(var i=0;i<n.length;i++){n[i].textContent=v;n[i].classList.add('done','settled');}
if(k==='headline'||k==='site_name')__t();}
function __t(){var h=document.querySelector('[data-slot="headline"]'),
s=document.querySelector('[data-slot="site_name"]'),
a=h?h.textContent:'',b=s?s.textContent:'';
document.title=a?(b?a+' \u2014 '+b:a):b;}
function __jdone(){var n=document.querySelectorAll('[data-slot]');
for(var i=0;i<n.length;i++)n[i].classList.add('done');}
</script>"""

# "I'm Feeling Vibey" with an empty box picks one of these rather than refusing.
VIBES = [
    "haunted lighthouse bed and breakfast",
    "competitive snail racing league",
    "1998 geocities fan page for toasters",
    "society for the preservation of roundabouts",
    "amateur lichen photography quarterly",
    "underground escalator enthusiasts forum",
    "mail order sea monkey conspiracy",
    "regional crisp flavour rankings",
    "abandoned funicular railways of europe",
    "competitive hedge maze design",
    "vintage fire alarm collectors guild",
    "the last remaining pneumatic tube network",
]

VISITOR_COOKIE = "jev_vid"
RECORD_COOKIE = "jev_record"  # "off" when the visitor opted out on the startup notice


def create_app(client_factory=get_client, recorder=None) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(gallery.bp)
    store = Store()
    recorder = recorder or make_recorder()

    def record(table: str, **fields) -> None:
        if recording_allowed():
            recorder.record(table, **fields)

    def recording_allowed() -> bool:
        return request.cookies.get(RECORD_COOKIE) != "off"

    def outside_shell():
        """A page opened directly in a tab skips the startup notice, so reopen it inside the shell."""
        if request.headers.get("Sec-Fetch-Dest") == "document":
            return redirect("/?" + urlencode({"start": request.full_path.rstrip("?")}))
        return None
    search_cache: dict[str, list[dict]] = {}
    search_lock = threading.Lock()
    blueprint_cache: "OrderedDict[str, dict]" = OrderedDict()  # local path -> inspector payload
    blueprint_lock = threading.Lock()

    def remember_blueprint(local: str, payload: dict) -> None:
        with blueprint_lock:
            blueprint_cache[local] = payload
            blueprint_cache.move_to_end(local)
            while len(blueprint_cache) > 200:
                blueprint_cache.popitem(last=False)

    # ---- chrome, home, results -------------------------------------------

    @app.get("/")
    def shell():
        start = request.args.get("start", "/home")
        if not start.startswith("/") or start.startswith("//"):
            start = "/home"
        resp = app.make_response(render_template("shell.html", start=start, blueprint=bp.enabled()))
        if not request.cookies.get(VISITOR_COOKIE):
            # Anonymous id so analytics can tell one visitor's searches from another's.
            resp.set_cookie(VISITOR_COOKIE, uuid.uuid4().hex, max_age=365 * 86400, samesite="Lax", httponly=True)
        return resp

    @app.post("/api/recording")
    def set_recording():
        allowed = bool((request.get_json(silent=True) or {}).get("record"))
        resp = jsonify({"recording": allowed})
        # A session cookie: the notice asks again every time the browser opens.
        resp.set_cookie(RECORD_COOKIE, "on" if allowed else "off", samesite="Lax", httponly=True)
        return resp

    @app.get("/home")
    def home():
        return outside_shell() or render_template("home.html")

    @app.get("/results")
    def results():
        q = request.args.get("q", "").strip()
        if not q:
            return redirect("/home")
        return outside_shell() or render_template("results.html", q=q)

    @app.get("/go")
    def go():
        """Address-bar entry: a URL goes to that site, anything else is a search."""
        raw = request.args.get("u", "").strip()
        if not raw or raw.lower() in ("interjev://home", "interjev://"):
            return redirect("/home")
        if raw.lower().startswith("interjev://search"):
            return redirect("/results?" + (urlsplit(raw).query or ""))
        looks_like_url = " " not in raw and re.search(r"^[\w.-]+://|^[\w-]+(\.[\w-]+)+(:\d+)?(/|$)", raw)
        if looks_like_url:
            local = to_local(raw)
            if local:
                return redirect(local)
        return redirect("/results?" + urlencode({"q": raw}))

    @app.get("/lucky")
    def lucky():
        # An empty box is the whole point of this button: vibe them somewhere.
        q = request.args.get("q", "").strip() or random.choice(VIBES)
        try:
            items = run_search(q)
        except JEVError as exc:
            return error_page(str(exc))
        if not items:
            return redirect("/results?" + urlencode({"q": q}))
        return redirect(items[0]["local"])

    # ---- search ------------------------------------------------------------

    def run_search(q: str) -> list[dict]:
        key = q.lower()
        with search_lock:
            cached = search_cache.get(key)
        if cached is not None:
            record("searches", visitor_id=visitor_id(), query=q, results=cached, cached=True)
            return cached
        started = time.monotonic()
        model = None
        try:
            client = client_factory()
            model = getattr(client, "model", None)
            raw = client.complete(prompts.search_messages(q))
            items = parse_results(raw)
        except JEVError as exc:
            record("searches", visitor_id=visitor_id(), query=q, model=model,
                            duration_ms=elapsed_ms(started), error=str(exc))
            raise
        record("searches", visitor_id=visitor_id(), query=q, results=items, model=model,
                        duration_ms=elapsed_ms(started))
        for item in items:
            host = urlsplit(item["url"]).hostname
            store.add_note(host, f"Search result for \"{q}\": {item['title']} — {item['snippet']}")
        with search_lock:
            search_cache[key] = items
        return items

    @app.get("/api/search")
    def api_search():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"results": []})
        try:
            return jsonify({"results": run_search(q)})
        except JEVError as exc:
            return jsonify({"error": str(exc)}), 502

    # ---- generated sites -------------------------------------------------

    @app.route("/site/<host>/", defaults={"path": ""}, methods=["GET", "POST"])
    @app.route("/site/<host>/<path:path>", methods=["GET", "POST"])
    def site(host: str, path: str):
        host = host.lower()
        args = request.args.to_dict(flat=True)
        regen = args.pop("_regen", None)
        query = urlencode(args) if args else ""
        url = to_fake(host, path, query)
        clean_local = to_local(url)

        if regen:
            store.drop_page(url)
            return redirect(clean_local)
        if request.method == "GET" and (bounce := outside_shell()):
            return bounce

        headers = {
            "Content-Security-Policy": SITE_CSP,
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        }

        form = request.form.to_dict(flat=True) if request.method == "POST" else None
        if request.method == "GET":
            cached = store.get_page(url)
            if cached is not None:
                return Response(cached, mimetype="text/html", headers=headers)

        try:
            client = client_factory()
        except JEVError as exc:
            return error_page(str(exc))

        site_info = store.site(host)
        referrer = referrer_info()
        request_method = request.method
        recording = recording_allowed()  # decided now: the generator runs after the request
        event = {
            "visitor_id": visitor_id(),
            "url": url,
            "host": host,
            "method": request_method,
            "form": form,
            "referrer": referrer[0] if referrer else search_referrer(),
            "model": getattr(client, "model", None),
        }

        page_blueprint = None
        if bp.enabled():
            try:
                page_blueprint = bp.get_decider().decide(
                    state=blueprint_state(url, request.method, site_info, referrer, form),
                    seed=uuid.uuid4().hex,
                    extra=assemble.variant_questions() if copywriter.enabled() else None,
                )
                if site_info.identity:
                    page_blueprint.adopt_identity(site_info.identity)
                else:
                    store.set_identity(host, page_blueprint.identity())
                remember_blueprint(clean_local, page_blueprint.inspector())
            except Exception as exc:
                # A blueprint is an enhancement; never let it stop the page.
                app.logger.warning("blueprint failed for %s: %s", url, exc)
                page_blueprint = None

        if copywriter.enabled() and page_blueprint is not None:
            return snippet_page(url, host, path, page_blueprint, site_info,
                                referrer, form, headers, event, recording)

        messages = prompts.page_messages(
            url,
            method=request.method,
            form=form,
            site_notes="\n".join(site_info.notes) or None,
            known_pages=[(p, t) for p, t in site_info.pages.items() if p != "/" + path] or None,
            stylesheet=site_info.stylesheet or None,
            referrer=referrer,
            blueprint=page_blueprint.prompt_text() if page_blueprint else None,
        )


        def generate():
            rw = StreamRewriter(url)
            started = time.monotonic()
            try:
                for chunk in client.stream(messages):
                    out = rw.feed(chunk)
                    if out:
                        yield out
                tail = rw.finish()
                if tail:
                    yield tail
            except Exception as exc:  # surface failures inside the page
                if recording:
                    recorder.record("pages", **event, html=rw.html, duration_ms=elapsed_ms(started), error=str(exc))
                yield (
                    '<div style="font:14px sans-serif;background:#fee;color:#900;'
                    'border:1px solid #c66;padding:12px;margin:12px">'
                    f"<b>interJEV Explorer cannot display the rest of this webpage.</b> {escape(str(exc))}</div>"
                )
                return
            page = rw.html
            if recording:
                recorder.record("pages", **event, title=extract_title(page), html=page,
                                duration_ms=elapsed_ms(started), error=None if page.strip() else "empty page")
            if not page.strip():
                yield "<p>JEV returned an empty page. Try regenerating.</p>"
                return
            if request_method == "GET":
                store.put_page(url, page)
            store.record_visit(host, "/" + path, extract_title(page), extract_stylesheet(page))

        return Response(generate(), mimetype="text/html", headers=headers)

    def snippet_page(url, host, path, page_blueprint, site_info, referrer, form,
                     headers, event, recording):
        """Skeleton and CSS from the library, words streamed into it afterwards."""
        built = assemble.assemble(page_blueprint)
        remember_blueprint(to_local(url), {**page_blueprint.inspector(),
                                           "components": built.components,
                                           "slots": len(built.slots)})
        messages = copywriter.build_prompt(
            url, built.slots,
            site_notes="\n".join(site_info.notes) or None,
            directives=page_blueprint.prompt_text(),
            referrer=referrer,
            form=form,
        )
        writer = copywriter.get_writer()
        event = {**event, "model": getattr(writer, "model", None)}
        request_method = request.method

        def generate():
            started = time.monotonic()
            rw = StreamRewriter(url)
            skeleton = rw.feed(built.html) + rw.finish()
            yield skeleton
            yield HYDRATE_JS
            values = {}
            try:
                for key, value in writer.stream(messages):
                    if key == "_brief":
                        store.add_note(host, value)
                        continue
                    values[key] = value
                    yield ("<script>__j(" + json.dumps(key) + "," + json.dumps(value) + ")</script>")
            except Exception as exc:
                yield ("<script>__jdone()</script>"
                       '<div class="note"><b>interJEV Explorer could not finish this page.</b> '
                       + str(escape(str(exc))) + "</div>")
                if recording:
                    recorder.record("pages", **event, html=assemble.fill(built.html, values),
                                    duration_ms=elapsed_ms(started), error=str(exc))
                yield "</body></html>"
                return
            yield "<script>__jdone()</script></body></html>"

            title = values.get("headline") or values.get("site_name") or ""
            page = assemble.fill(built.html, values, title) + "</body></html>"
            if recording:
                recorder.record("pages", **event, title=title, html=page,
                                duration_ms=elapsed_ms(started),
                                error=None if values else "no copy returned")
            if request_method == "GET":
                store.put_page(url, page)
            store.record_visit(host, "/" + path, title, built.stylesheet)

        return Response(generate(), mimetype="text/html", headers=headers)

    def blueprint_state(url, method, site_info, referrer, form) -> str:
        """What JEV sees when it decides the page's structure."""
        parts = [f"URL: {url}", f"HTTP method: {method}"]
        if site_info.notes:
            parts.append("What is known about this site:\n" + "\n".join(site_info.notes))
        if referrer:
            parts.append(f'Arrived from: {referrer[0]} ("{referrer[1]}")')
        if form:
            parts.append("Submitted form fields: " + ", ".join(form))
        if site_info.pages:
            parts.append("Other pages seen on this site: " + ", ".join(site_info.pages))
        return "\n\n".join(parts)

    @app.get("/api/blueprint")
    def api_blueprint():
        local = request.args.get("u", "")
        with blueprint_lock:
            payload = blueprint_cache.get(local)
        if payload is None:
            return jsonify({"blueprint": None}), 404
        return jsonify({"blueprint": payload})

    def referrer_info():
        ref = request.referrer or ""
        m = re.search(r"/site/([^/?#]+)(/[^?#]*)?(?:\?([^#]*))?", ref)
        if not m:
            return None
        ref_url = to_fake(m.group(1), m.group(2) or "/", m.group(3) or "")
        cached = store.get_page(ref_url)
        return ref_url, extract_title(cached) if cached else ""

    def search_referrer():
        """interjev://search?q=... when the visitor came from a results page (for analytics)."""
        ref = urlsplit(request.referrer or "")
        return f"interjev://search?{ref.query}" if ref.path == "/results" else None

    def visitor_id():
        return request.cookies.get(VISITOR_COOKIE)

    # ---- misc ------------------------------------------------------------

    @app.get("/healthz")
    def healthz():
        return "ok"

    @app.get("/placeholder.svg")
    def placeholder():
        text = request.args.get("text", "image")[:80]
        hue = sum(map(ord, text)) % 360
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400" preserveAspectRatio="xMidYMid slice">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0" stop-color="hsl({hue},55%,70%)"/><stop offset="1" stop-color="hsl({(hue + 60) % 360},55%,45%)"/>
</linearGradient></defs>
<rect width="640" height="400" fill="url(#g)"/>
<text x="320" y="200" font-family="sans-serif" font-size="24" fill="rgba(255,255,255,.9)" text-anchor="middle" dominant-baseline="middle">{escape(text)}</text>
</svg>"""
        return Response(svg, mimetype="image/svg+xml", headers={"Cache-Control": "max-age=86400"})

    @app.get("/favicon.ico")
    def favicon():
        return redirect(url_for("static", filename="logo.svg"))

    def error_page(message: str):
        return render_template("error.html", message=message), 502

    return app


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def parse_results(raw: str) -> list[dict]:
    """Pull the results list out of JEV's reply, tolerating fences and chatter."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        raise JEVError("JEV did not return JSON search results")
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise JEVError(f"JEV returned malformed JSON: {exc}") from exc
    items = data.get("results", []) if isinstance(data, dict) else []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = normalize_url(str(item.get("url", "")))
        if not url:
            continue
        parts = urlsplit(url)
        out.append(
            {
                "title": str(item.get("title") or parts.hostname)[:200],
                "url": url,
                "display_url": str(item.get("display_url") or (parts.hostname + parts.path))[:120],
                "snippet": str(item.get("snippet") or "")[:400],
                "local": to_local(url),
            }
        )
    return out
