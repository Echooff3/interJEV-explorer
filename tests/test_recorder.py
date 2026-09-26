import io
import json
import os

import pytest

from interjev import create_app
from interjev.recorder import ConsoleRecorder, make_recorder

from .test_app import FakeJEV


class ListRecorder:
    def __init__(self):
        self.events = []

    def record(self, table, **fields):
        self.events.append((table, fields))


def test_console_recorder_writes_json_lines():
    out = io.StringIO()
    ConsoleRecorder(out).record("searches", query="snails", results=[{"title": "x"}])
    prefix, line = out.getvalue().split(" ", 1)
    assert prefix == "[interjev]"
    event = json.loads(line)
    assert event["event"] == "search" and event["query"] == "snails"


def test_capture_requires_database_url(monkeypatch):
    monkeypatch.setenv("JEV_CAPTURE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        make_recorder()


def test_app_records_searches_and_generated_pages():
    rec = ListRecorder()
    client = create_app(client_factory=FakeJEV, recorder=rec).test_client()
    client.get("/")  # sets the visitor cookie
    vid = client.get_cookie("jev_vid").value

    client.get("/api/search?q=snail racing")
    client.get("/api/search?q=snail racing")
    client.get("/site/snailweekly.net/2026/finals",
               headers={"Referer": "http://localhost/results?q=snail+racing"}).get_data()
    client.get("/site/snailweekly.net/2026/finals").get_data()  # cached: not a new creation
    client.post("/site/snailweekly.net/login", data={"user": "gary"}).get_data()

    searches = [f for t, f in rec.events if t == "searches"]
    assert [s.get("cached", False) for s in searches] == [False, True]
    assert searches[0]["query"] == "snail racing" and searches[0]["visitor_id"] == vid
    assert searches[0]["results"][0]["url"] == "https://snailweekly.net/2026/finals"

    pages = [f for t, f in rec.events if t == "pages"]
    assert len(pages) == 2
    assert pages[0]["url"] == "https://snailweekly.net/2026/finals"
    assert pages[0]["title"] == "Finals" and "<title>Finals</title>" in pages[0]["html"]
    assert pages[0]["error"] is None and pages[0]["visitor_id"] == vid
    assert pages[0]["referrer"] == "interjev://search?q=snail+racing"
    assert pages[1]["method"] == "POST" and pages[1]["form"] == {"user": "gary"}


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to test Postgres")
def test_postgres_recorder_round_trip():
    import psycopg

    from interjev.recorder import PostgresRecorder

    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS searches, pages")

    rec = PostgresRecorder(dsn)
    app = create_app(client_factory=FakeJEV, recorder=rec).test_client()
    app.get("/api/search?q=snail racing")
    app.post("/site/snailweekly.net/login", data={"user": "gary"}).get_data()
    rec.close()

    with psycopg.connect(dsn) as conn:
        q, results, cached = conn.execute("SELECT query, results, cached FROM searches").fetchone()
        assert q == "snail racing" and results[0]["title"] == "Snail Racing Weekly" and cached is False
        url, method, form, title, html = conn.execute(
            "SELECT url, method, form, title, html FROM pages").fetchone()
        assert (url, method, form, title) == ("https://snailweekly.net/login", "POST", {"user": "gary"}, "Finals")
        assert html.startswith("<!DOCTYPE html>")
