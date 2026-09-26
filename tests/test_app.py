import json
import re

import pytest

from interjev import create_app
from interjev.app import VIBES


class FakeJEV:
    def __init__(self):
        self.calls = []

    def complete(self, messages):
        self.calls.append(("complete", messages))
        return "Sure!\n```json\n" + json.dumps(
            {
                "results": [
                    {"title": "Snail Racing Weekly", "url": "https://snailweekly.net/2026/finals",
                     "display_url": "snailweekly.net › finals", "snippet": "Gary wins again."},
                    {"title": "bad", "url": "javascript:alert(1)"},
                ]
            }
        ) + "\n```"

    def stream(self, messages):
        self.calls.append(("stream", messages))
        page = ('<!DOCTYPE html><html><head><title>Finals</title><style>body{color:teal}</style></head>'
                '<body><a href="/results/2025">Last year</a></body></html>')
        for i in range(0, len(page), 5):
            yield page[i : i + 5]


@pytest.fixture
def jev():
    return FakeJEV()


@pytest.fixture
def client(jev):
    return create_app(client_factory=lambda: jev).test_client()


def test_home_and_shell(client):
    assert b"interJEV" in client.get("/").data
    assert b'name="q"' in client.get("/home").data


def test_search_api_filters_bad_urls(client):
    data = client.get("/api/search?q=snail racing").get_json()
    assert [r["local"] for r in data["results"]] == ["/site/snailweekly.net/2026/finals"]


def test_site_streams_rewrites_and_caches(client, jev):
    client.get("/api/search?q=snail racing")
    res = client.get("/site/snailweekly.net/2026/finals")
    body = res.get_data(as_text=True)
    assert 'href="/site/snailweekly.net/results/2025"' in body
    assert "connect-src 'none'" in res.headers["Content-Security-Policy"]
    prompt = jev.calls[-1][1][-1]["content"]
    assert "URL: https://snailweekly.net/2026/finals" in prompt
    assert "Gary wins again." in prompt  # search snippet carried into the site

    # cached on the second visit
    n = len(jev.calls)
    assert client.get("/site/snailweekly.net/2026/finals").get_data(as_text=True) == body
    assert len(jev.calls) == n

    # next page on the same site gets the stylesheet + known pages + referrer
    client.get("/site/snailweekly.net/results/2025",
               headers={"Referer": "http://localhost/site/snailweekly.net/2026/finals"})
    prompt = jev.calls[-1][1][-1]["content"]
    assert "body{color:teal}" in prompt
    assert "/2026/finals — Finals" in prompt
    assert 'clicking a link on: https://snailweekly.net/2026/finals ("Finals")' in prompt


def test_regen_drops_cache(client, jev):
    client.get("/site/x.com/")
    res = client.get("/site/x.com/?_regen=1")
    assert res.status_code == 302 and res.headers["Location"].endswith("/site/x.com/")
    n = len(jev.calls)
    client.get("/site/x.com/").get_data()
    assert len(jev.calls) == n + 1


def test_post_forms_pass_data_and_skip_cache(client, jev):
    client.post("/site/shop.io/login", data={"user": "gary"}).get_data()
    prompt = jev.calls[-1][1][-1]["content"]
    assert "HTTP method: POST" in prompt and "user = gary" in prompt


def test_go_routes_urls_and_searches(client):
    assert client.get("/go?u=weird-site.org/page").headers["Location"] == "/site/weird-site.org/page"
    assert client.get("/go?u=best pizza").headers["Location"] == "/results?q=best+pizza"
    assert client.get("/go?u=interjev://search?q=hi").headers["Location"] == "/results?q=hi"


def test_lucky_goes_to_first_result(client):
    assert client.get("/lucky?q=snails").headers["Location"] == "/site/snailweekly.net/2026/finals"


def test_lucky_with_no_query_still_vibes(client, jev):
    """An empty box is the point of the button: it must not bounce back home."""
    resp = client.get("/lucky")
    assert resp.headers["Location"].startswith("/site/")
    asked = jev.calls[-1][1][-1]["content"]
    assert any(v in asked for v in VIBES)


def test_vibey_button_skips_field_validation(client):
    """The shared input is `required`, so the button must opt out of it."""
    page = client.get("/home").get_data(as_text=True)
    button = re.search(r'<button[^>]*formaction="/lucky"[^>]*>', page).group(0)
    assert "formnovalidate" in button


def test_missing_config_shows_cannot_display_page():
    from interjev.jev import JEVError

    def broken():
        raise JEVError("OPENROUTER_API_KEY is not set")

    res = create_app(client_factory=broken).test_client().get("/site/x.com/")
    body = res.get_data(as_text=True)
    assert res.status_code == 502
    assert "interJEV Explorer cannot display the webpage" in body
    assert "OPENROUTER_API_KEY is not set" in body
