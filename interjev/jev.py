"""Client for talking to JEV through OpenRouter's OpenAI-compatible API."""

import json
import os
import time
from typing import Iterator

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class JEVError(RuntimeError):
    pass


class JEV:
    """Thin wrapper around OpenRouter chat completions."""

    def __init__(self, api_key: str, model: str, temperature: float = 0.9, timeout: int = 180):
        if not api_key:
            raise JEVError("OPENROUTER_API_KEY is not set")
        if not model:
            raise JEVError("JEV_MODEL is not set (the OpenRouter model id for JEV)")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "JEV":
        return cls(
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            model=os.environ.get("JEV_MODEL", ""),
            temperature=float(os.environ.get("JEV_TEMPERATURE", "0.9")),
        )

    def _payload(self, messages: list[dict], stream: bool) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": stream,
        }

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optional attribution headers recognised by OpenRouter.
            "HTTP-Referer": "https://github.com/echooff3/interJEV-explorer",
            "X-Title": "interJEV Explorer",
        }

    def complete(self, messages: list[dict]) -> str:
        resp = requests.post(
            OPENROUTER_URL,
            headers=self._headers(),
            json=self._payload(messages, stream=False),
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise JEVError(f"OpenRouter returned {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise JEVError(f"Unexpected OpenRouter response: {json.dumps(data)[:500]}") from exc

    def stream(self, messages: list[dict]) -> Iterator[str]:
        resp = requests.post(
            OPENROUTER_URL,
            headers=self._headers(),
            json=self._payload(messages, stream=True),
            timeout=self.timeout,
            stream=True,
        )
        if resp.status_code != 200:
            raise JEVError(f"OpenRouter returned {resp.status_code}: {resp.text[:500]}")
        resp.encoding = "utf-8"
        with resp:
            for line in resp.iter_lines(decode_unicode=True):
                # SSE: skip keep-alive comments (": OPENROUTER PROCESSING") and blanks.
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk:
                    raise JEVError(f"OpenRouter stream error: {chunk['error']}")
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta", {}).get("content")
                    if delta:
                        yield delta


class MockJEV:
    """Offline stand-in so the app can be clicked through without an API key."""

    model = "mock"

    def complete(self, messages: list[dict]) -> str:
        query = messages[-1]["content"].removeprefix("Search query: ")[:60]
        results = [
            {
                "title": f"Mock result {i} for {query!r}",
                "url": f"https://www.mock-site-{i}.com/",
                "display_url": f"www.mock-site-{i}.com",
                "snippet": "Set OPENROUTER_API_KEY and JEV_MODEL to let JEV invent real-looking results.",
            }
            for i in range(1, 6)
        ]
        return json.dumps({"results": results})

    def stream(self, messages: list[dict]) -> Iterator[str]:
        page = (
            "```html\n<!DOCTYPE html><html><head><title>Mock page</title>"
            "<style>body{font-family:sans-serif;max-width:720px;margin:40px auto;padding:0 16px}</style>"
            "</head><body><h1>Mock page</h1><p>JEV is running in mock mode.</p>"
            '<p><a href="/about">About</a> · <a href="https://www.another-mock.org/news">Another site</a></p>'
            '<form action="/search"><input name="q"><button>Go</button></form>'
            '<img src="/logo.png" alt="Company logo"></body></html>\n```'
        )
        for i in range(0, len(page), 40):
            time.sleep(0.02)
            yield page[i : i + 40]


def get_client():
    if os.environ.get("JEV_MOCK", "").lower() in ("1", "true", "yes"):
        return MockJEV()
    return JEV.from_env()
