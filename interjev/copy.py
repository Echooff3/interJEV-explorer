"""Fills the assembled skeleton's text slots, and nothing else.

The model here never sees HTML and never emits it. It is handed a list of slot
keys and returns a flat JSON object of plain strings, which is cheap, easy to
validate, and lets a small fast model do work that would otherwise need a
frontier one. Pairs are yielded as they complete so the page hydrates
progressively rather than all at once.
"""

import json
import os
import re
from typing import Iterator

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

# Matches one finished "key": "value" pair in a flat JSON object.
PAIR = re.compile(r'"([A-Za-z0-9_]+)"\s*:\s*"((?:[^"\\]|\\.)*)"')

SYSTEM = """\
You write the words for one page of a fictional website on interJEV, an \
alternate internet. The page's layout, styling and structure are already \
decided and are not your concern.

Rules:
- Return ONLY a JSON object. No markdown fences, no commentary.
- Use exactly the keys you are given, all of them, in the order given.
- Every value is plain text. Never HTML, never markdown, never a URL.
- Write specific, believable content: real-sounding names, places, dates, \
numbers, prices. Never hint that the site is fictional or generated.
- Keys starting with body_ are full paragraphs of 40-90 words. Keys ending in \
_text are 1-3 sentences. Everything else is short — a label, name or line.
- Keep every value consistent with the others: one site, one story, one voice.
"""


class CopyError(RuntimeError):
    pass


def build_prompt(url: str, slots: list, *, site_notes=None, directives=None,
                 brief=None, referrer=None, form=None) -> list:
    parts = [f"URL: {url}"]
    if site_notes:
        parts.append("What is known about this site:\n" + site_notes)
    if brief:
        parts.append("This site has already been established as:\n" + brief)
    if referrer:
        parts.append(f'The visitor arrived from: {referrer[0]} ("{referrer[1]}")')
    if form:
        parts.append("They submitted: " + ", ".join(f"{k}={v}" for k, v in form.items()))
    if directives:
        parts.append("The page's structure has already been decided:\n" + directives)

    listing = "\n".join(f'  "{key}": {hint}' for key, hint in slots)
    parts.append(
        'First key must be "_brief": one sentence on what this page is about, which '
        "you then keep to. After that, these keys in this order:\n" + listing
    )
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": "\n\n".join(parts)}]


class CopyWriter:
    def __init__(self, api_key: str, model: str, timeout: int = 180):
        if not api_key:
            raise CopyError("OPENROUTER_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def stream(self, messages: list) -> Iterator[tuple]:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/echooff3/interJEV-explorer",
                     "X-Title": "interJEV Explorer"},
            json={"model": self.model, "messages": messages, "temperature": 0.9,
                  "response_format": {"type": "json_object"}, "stream": True},
            timeout=self.timeout,
            stream=True,
        )
        if resp.status_code != 200:
            raise CopyError(f"OpenRouter returned {resp.status_code}: {resp.text[:300]}")
        resp.encoding = "utf-8"
        buffer = ""
        cursor = 0
        with resp:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk:
                    raise CopyError(f"OpenRouter stream error: {chunk['error']}")
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta", {}).get("content")
                if not delta:
                    continue
                buffer += delta
                for match in PAIR.finditer(buffer, cursor):
                    cursor = match.end()
                    try:
                        value = json.loads('"' + match.group(2) + '"')
                    except json.JSONDecodeError:
                        value = match.group(2)
                    yield match.group(1), value


class MockCopyWriter:
    model = "mock-copy"

    def stream(self, messages: list) -> Iterator[tuple]:
        listing = messages[-1]["content"].rsplit("these keys in this order:\n", 1)[-1]
        yield "_brief", "A mock page, generated without an API key."
        for line in listing.splitlines():
            key = line.strip().split('"')
            if len(key) > 1:
                yield key[1], f"Mock {key[1].replace('_', ' ')}"


def get_writer():
    if os.environ.get("JEV_MOCK", "").lower() in ("1", "true", "yes"):
        return MockCopyWriter()
    return CopyWriter(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=os.environ.get("JEV_COPY_MODEL", DEFAULT_MODEL),
    )


def enabled() -> bool:
    return os.environ.get("JEV_SNIPPETS", "").lower() in ("1", "true", "yes", "on")
