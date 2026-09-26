import base64
import os

import pytest

from interjev import create_app

from .test_app import FakeJEV
from .test_recorder import ListRecorder


def auth(password):
    return {"Authorization": "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()}


def make_client(**kw):
    return create_app(client_factory=FakeJEV, **kw).test_client()


def test_gallery_is_off_without_a_password(monkeypatch):
    monkeypatch.delenv("GALLERY_PASSWORD", raising=False)
    assert make_client(recorder=ListRecorder()).get("/gallery/").status_code == 404


def test_gallery_requires_the_password(monkeypatch):
    monkeypatch.setenv("GALLERY_PASSWORD", "hunter2")
    client = make_client(recorder=ListRecorder())
    res = client.get("/gallery/")
    assert res.status_code == 401 and "Basic" in res.headers["WWW-Authenticate"]
    assert client.get("/gallery/", headers=auth("nope")).status_code == 401
    assert client.get("/gallery/page/1/raw", headers=auth("nope")).status_code == 401


def test_gallery_explains_when_no_database(monkeypatch):
    monkeypatch.setenv("GALLERY_PASSWORD", "hunter2")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    res = make_client(recorder=ListRecorder()).get("/gallery/", headers=auth("hunter2"))
    assert res.status_code == 503 and b"--capture" in res.data


@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="set TEST_DATABASE_URL to test Postgres")
def test_gallery_shows_recorded_pages(monkeypatch):
    import psycopg

    from interjev.recorder import PostgresRecorder

    dsn = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute("DROP TABLE IF EXISTS searches, pages")
    monkeypatch.setenv("DATABASE_URL", dsn)
    monkeypatch.setenv("GALLERY_PASSWORD", "hunter2")

    rec = PostgresRecorder(dsn)
    client = make_client(recorder=rec)
    client.get("/")
    client.get("/api/search?q=snail racing")
    client.get("/site/snailweekly.net/2026/finals",
               headers={"Referer": "http://localhost/results?q=snail+racing"}).get_data()
    client.get("/site/other.org/").get_data()
    rec.flush()
    with psycopg.connect(dsn) as conn:
        finals_id = conn.execute("SELECT id FROM pages WHERE host = 'snailweekly.net'").fetchone()[0]

    ok = auth("hunter2")
    index = client.get("/gallery/", headers=ok).get_data(as_text=True)
    assert "snail racing" in index and "https://snailweekly.net/2026/finals" in index and "https://other.org/" in index
    assert "<b>1</b> searches" in index and "<b>2</b> pages" in index

    only = client.get("/gallery/?search=snail+racing", headers=ok).get_data(as_text=True)
    assert "https://snailweekly.net/2026/finals" in only and "https://other.org/" not in only
    only = client.get("/gallery/?host=other.org", headers=ok).get_data(as_text=True)
    assert "https://other.org/" in only and "https://snailweekly.net/2026/finals" not in only

    detail = client.get(f"/gallery/page/{finals_id}", headers=ok).get_data(as_text=True)
    assert "Finals" in detail and "“snail racing”" in detail

    raw = client.get(f"/gallery/page/{finals_id}/raw", headers=ok)
    assert raw.headers["Content-Security-Policy"].startswith("sandbox allow-scripts")
    assert '<head><base target="_blank">' in raw.get_data(as_text=True)

    dl = client.get(f"/gallery/page/{finals_id}/source?download=1", headers=ok)
    assert "attachment" in dl.headers["Content-Disposition"]
    assert dl.get_data(as_text=True).startswith("<!DOCTYPE html>")
    assert client.get("/gallery/page/999999", headers=ok).status_code == 404
    rec.close()
