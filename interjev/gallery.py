"""/gallery: a password-protected place to review what people searched and what JEV made.

Reads from the Postgres tables written in capture mode. Set GALLERY_PASSWORD
to turn it on; the browser's login prompt accepts any username.
"""

import hmac
import os
import re
from datetime import datetime
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, render_template, request

PAGE_SIZE = 24

# Stored pages are model-written HTML. Serve them in an opaque-origin sandbox
# so their scripts can't reach the gallery (or anything else on this origin),
# and open their links in a new tab, where they go through the startup notice.
RAW_CSP = (
    "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox; "
    "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'unsafe-inline'; "
    "img-src 'self' data:; font-src data:; connect-src 'none'; form-action 'self'"
)

bp = Blueprint("gallery", __name__, url_prefix="/gallery")


@bp.before_request
def require_password():
    password = os.environ.get("GALLERY_PASSWORD", "")
    if not password:
        abort(404)
    auth = request.authorization
    given = (auth.password or "") if auth else ""
    if not hmac.compare_digest(given.encode(), password.encode()):
        return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="interJEV Gallery"'})


def connect():
    """A short-lived connection per request; the gallery is low-traffic."""
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        return None
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10)


def search_referrer(query: str) -> str:
    return "interjev://search?" + urlencode({"q": query})


@bp.app_template_filter("when")
def when(value: datetime) -> str:
    return value.strftime("%b %d, %H:%M UTC") if value else ""


@bp.app_template_filter("search_query")
def search_query(referrer: str | None) -> str | None:
    """interjev://search?q=snail+racing -> snail racing"""
    if not referrer or not referrer.startswith("interjev://search?"):
        return None
    from urllib.parse import parse_qs

    return parse_qs(referrer.split("?", 1)[1]).get("q", [None])[0]


@bp.get("/")
def index():
    conn = connect()
    if conn is None:
        return render_template("gallery/off.html"), 503

    filters = {k: request.args.get(k, "").strip() for k in ("q", "host", "visitor", "search")}
    try:
        page = max(int(request.args.get("page", "1")), 1)
    except ValueError:
        page = 1

    where, params = [], []
    if filters["q"]:
        where.append("(url ILIKE %s OR title ILIKE %s)")
        params += [f"%{filters['q']}%"] * 2
    if filters["host"]:
        where.append("host = %s")
        params.append(filters["host"].lower())
    if filters["visitor"]:
        where.append("visitor_id = %s")
        params.append(filters["visitor"])
    if filters["search"]:
        where.append("referrer = %s")
        params.append(search_referrer(filters["search"]))
    clause = ("WHERE " + " AND ".join(where)) if where else ""

    with conn:
        stats = conn.execute(
            """SELECT (SELECT count(*) FROM searches) AS searches,
                      (SELECT count(*) FROM pages) AS pages,
                      (SELECT count(*) FROM pages WHERE created_at > now() - interval '24 hours') AS pages_24h,
                      (SELECT count(DISTINCT visitor_id) FROM
                          (SELECT visitor_id FROM searches UNION SELECT visitor_id FROM pages) v) AS visitors"""
        ).fetchone()
        top = conn.execute(
            """SELECT min(query) AS query, count(*) AS n FROM searches
               GROUP BY lower(query) ORDER BY n DESC, max(created_at) DESC LIMIT 12"""
        ).fetchall()
        recent = conn.execute(
            """SELECT created_at, query, cached, error, visitor_id,
                      coalesce(jsonb_array_length(results), 0) AS n_results
               FROM searches ORDER BY id DESC LIMIT 12"""
        ).fetchall()
        rows = conn.execute(
            f"""SELECT id, created_at, url, host, title, referrer, method, duration_ms, error, visitor_id
                FROM pages {clause} ORDER BY id DESC LIMIT %s OFFSET %s""",
            params + [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE],
        ).fetchall()

    active = {k: v for k, v in filters.items() if v}

    def qs(**changes):
        """This page's URL with some filters changed (None removes one)."""
        params = dict(active)
        for key, value in changes.items():
            if value in (None, ""):
                params.pop(key, None)
            else:
                params[key] = value
        return "?" + urlencode(params) if params else request.path

    return render_template(
        "gallery/index.html",
        stats=stats,
        top=top,
        recent=recent,
        pages=rows[:PAGE_SIZE],
        page=page,
        has_next=len(rows) > PAGE_SIZE,
        filters=filters,
        active=active,
        qs=qs,
    )


def fetch_page(page_id: int):
    conn = connect()
    if conn is None:
        abort(503)
    with conn:
        row = conn.execute("SELECT * FROM pages WHERE id = %s", (page_id,)).fetchone()
    if row is None:
        abort(404)
    return row


@bp.get("/page/<int:page_id>")
def detail(page_id: int):
    return render_template("gallery/page.html", p=fetch_page(page_id))


@bp.get("/page/<int:page_id>/raw")
def raw(page_id: int):
    html = fetch_page(page_id)["html"] or ""
    base = '<base target="_blank">'
    html, n = re.subn(r"(<head\b[^>]*>)", r"\1" + base, html, count=1, flags=re.IGNORECASE)
    if not n:
        html = base + html
    return Response(html, mimetype="text/html", headers={"Content-Security-Policy": RAW_CSP,
                                                         "Cache-Control": "private, max-age=3600"})


@bp.get("/page/<int:page_id>/source")
def source(page_id: int):
    p = fetch_page(page_id)
    download = request.args.get("download")
    headers = {"Content-Security-Policy": "default-src 'none'"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="interjev-page-{page_id}.html"'
    return Response(p["html"] or "", mimetype="text/plain" if not download else "text/html", headers=headers)
