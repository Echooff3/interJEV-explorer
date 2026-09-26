"""JEV's Decisions API: typed answers that decide what a page is made of.

The writer model invents prose; JEV decides structure. Answers come back as
calibrated probabilities, so optional elements are *sampled* against their
probability rather than thresholded: 0.79 on comments means comments appear on
roughly 79% of pages like this one. Re-rolling with a new seed is what makes
the regenerate button produce the same site with different furniture.
"""

import math
import os
import random
import time
from typing import Any

import requests

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "~typesafe/jev-latest"

# choice: one of a set, for things that can only be one way at a time.
CHOICE_QUESTIONS = {
    "archetype": {
        "instructions": "What kind of website would serve this URL?",
        "criteria": {
            "news": "A news story, local paper, or magazine article",
            "shop": "A shop, product listing, or checkout page",
            "forum": "A message board, Q&A, or discussion thread",
            "corporate": "A company marketing, SaaS, or landing page",
            "personal": "A personal blog, hobbyist page, or fan site",
            "reference": "A wiki, documentation, or reference entry",
            "institutional": "A government, school, library, or club site",
        },
    },
    "layout": {
        "instructions": "What page layout would this site use?",
        "criteria": {
            "single_column": "One centered column of content, no sidebar",
            "sidebar_left": "Navigation sidebar on the left, content on the right",
            "sidebar_right": "Content on the left, sidebar of extras on the right",
            "magazine_grid": "A multi-column grid of cards or teasers",
            "dense_table": "Table- or list-driven, data first, minimal styling",
        },
    },
    "palette": {
        "instructions": "What colour treatment would this site use?",
        "criteria": {
            "stark_light": "White background, black text, one accent colour",
            "warm_paper": "Off-white or cream paper tones, serif type",
            "dark_mode": "Dark background with light text",
            "brand_saturated": "A strong saturated brand colour used confidently",
            "garish": "Clashing bright colours, tiled or patterned background",
        },
    },
}

# score: an ordered dial. The fractional answer is the useful part.
SCORE_QUESTIONS = {
    "era": {
        "instructions": "What era does this site's design belong to?",
        "criteria": [
            "1996 hand-coded HTML, tables and visible seams",
            "2008 web 2.0 gradients, rounded corners, glossy buttons",
            "2026 modern minimal, generous whitespace, system fonts",
        ],
    },
    "ad_density": {
        "instructions": "How heavily monetised with advertising is this page?",
        "criteria": [
            "No advertising at all",
            "A couple of restrained, clearly-marked placements",
            "Plastered with ad slots that crowd the content",
        ],
    },
    "text_density": {
        "instructions": "How dense is the text on this page?",
        "criteria": [
            "Sparse: a few short lines, lots of empty space",
            "Balanced: readable paragraphs with room to breathe",
            "Dense: long wall-to-wall body copy, small type",
        ],
    },
}

# noul: independent yes/no propositions, sampled against their probability.
ELEMENT_QUESTIONS = {
    "comments": (
        "Would this page carry a reader comments section?",
        "a reader comments section with 3-6 distinctly-voiced named commenters and timestamps",
    ),
    "paywall": (
        "Would this page interrupt the reader with a subscription paywall?",
        "a subscription paywall or metered-article prompt interrupting the content",
    ),
    "newsletter": (
        "Would this page ask the visitor to join an email newsletter?",
        "an email newsletter signup box with its own pitch copy",
    ),
    "cookie_banner": (
        "Would this page show a cookie-consent banner?",
        "a cookie-consent banner fixed to the bottom of the viewport",
    ),
    "hit_counter": (
        "Would this page display a visitor hit counter or 'last updated' stamp?",
        "a visitor hit counter and a 'last updated' line in the footer",
    ),
    "social_share": (
        "Would this page offer buttons to share the page on social networks?",
        "share buttons for plausible invented social networks",
    ),
    "related": (
        "Would this page recommend other pages on the same site?",
        "a 'related' or 'you might also like' block linking to other pages on this site",
    ),
    "account": (
        "Would this page have a sign-in or account area?",
        "a sign-in / account area in the header",
    ),
    "construction": (
        "Would this page admit that part of it is unfinished?",
        "an 'under construction' notice, built with CSS rather than an image",
    ),
}


def build_questions(extra: dict | None = None) -> dict:
    questions: dict[str, dict] = {}
    for key, q in CHOICE_QUESTIONS.items():
        questions[key] = {"type": "choice", **q}
    for key, q in SCORE_QUESTIONS.items():
        questions[key] = {"type": "score", **q}
    for key, (instructions, _) in ELEMENT_QUESTIONS.items():
        questions[key] = {"type": "noul", "instructions": instructions}
    questions.update(extra or {})
    return questions


# Decided once per site, then inherited, so every page of a site looks related.
IDENTITY_KEYS = ("archetype", "layout", "palette", "era")


class BlueprintError(RuntimeError):
    pass


class Blueprint:
    """A decided page structure, plus the raw answers for the inspector."""

    def __init__(self, response: dict, seed: str, duration_ms: int,
                 extra_choices: dict | None = None):
        self.extra_choices = extra_choices or {}
        self.answers: dict[str, Any] = response.get("answers") or {}
        self.model = response.get("model") or ""
        self.usage = response.get("usage") or {}
        self.seed = seed
        self.duration_ms = duration_ms
        self.inherited: set[str] = set()

        rng = random.Random(seed)
        self.elements: dict[str, dict] = {}
        for key in ELEMENT_QUESTIONS:
            probability = float((self.answers.get(key) or {}).get("noul", 0.0))
            # rng is drawn for every element so the roll sequence is stable per seed.
            self.elements[key] = {"probability": probability, "included": rng.random() < probability}

    def identity(self) -> dict:
        return {k: self.answers[k] for k in IDENTITY_KEYS if k in self.answers}

    def adopt_identity(self, stored: dict) -> None:
        self.answers.update(stored)
        self.inherited = set(stored)

    def _choice(self, key: str) -> str:
        return (self.answers.get(key) or {}).get("choice") or ""

    def _score_phrase(self, key: str) -> str:
        answer = self.answers.get(key) or {}
        labels = SCORE_QUESTIONS[key]["criteria"]
        legend = answer.get("legend") or {}
        if legend:
            labels = [legend.get(str(i), labels[i]) for i in range(len(labels))]
        score = float(answer.get("score", 0.0))
        low = max(0, min(len(labels) - 1, int(math.floor(score))))
        high = min(len(labels) - 1, low + 1)
        frac = score - low
        if high == low or frac < 0.15:
            return labels[low]
        if frac > 0.85:
            return labels[high]
        nearer, further = (labels[high], labels[low]) if frac > 0.5 else (labels[low], labels[high])
        return f'mostly "{nearer}", with some "{further}"'

    def directives(self) -> list[str]:
        lines = []
        archetype = self._choice("archetype")
        if archetype:
            lines.append(f"Site type: {CHOICE_QUESTIONS['archetype']['criteria'].get(archetype, archetype)}")
        layout = self._choice("layout")
        if layout:
            lines.append(f"Layout: {CHOICE_QUESTIONS['layout']['criteria'].get(layout, layout)}")
        palette = self._choice("palette")
        if palette:
            lines.append(f"Colour: {CHOICE_QUESTIONS['palette']['criteria'].get(palette, palette)}")
        for key, label in (("era", "Era"), ("ad_density", "Advertising"), ("text_density", "Text density")):
            if key in self.answers:
                lines.append(f"{label}: {self._score_phrase(key)}")

        include = [ELEMENT_QUESTIONS[k][1] for k, v in self.elements.items() if v["included"]]
        omit = [ELEMENT_QUESTIONS[k][1] for k, v in self.elements.items() if not v["included"]]
        if include:
            lines.append("Include these elements: " + "; ".join(include) + ".")
        if omit:
            lines.append("Do NOT include: " + "; ".join(omit) + ".")
        return lines

    def prompt_text(self) -> str:
        return "\n".join("- " + line for line in self.directives())

    def inspector(self) -> dict:
        """What the drawer renders: every question, its answer, and the roll."""
        rows = []
        for key, q in CHOICE_QUESTIONS.items():
            answer = self.answers.get(key)
            if not answer:
                continue
            rows.append({
                "key": key,
                "type": "choice",
                "question": q["instructions"],
                "chosen": answer.get("choice"),
                "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities") or {},
                "labels": q["criteria"],
                "inherited": key in self.inherited,
            })
        for key, q in self.extra_choices.items():
            answer = self.answers.get(key)
            if not answer:
                continue
            rows.append({
                "key": key,
                "type": "choice",
                "question": q["instructions"],
                "chosen": answer.get("choice"),
                "confidence": answer.get("confidence"),
                "probabilities": answer.get("probabilities") or {},
                "labels": q["criteria"],
                "inherited": key in self.inherited,
            })
        for key, q in SCORE_QUESTIONS.items():
            answer = self.answers.get(key)
            if not answer:
                continue
            legend = answer.get("legend") or {str(i): l for i, l in enumerate(q["criteria"])}
            rows.append({
                "key": key,
                "type": "score",
                "question": q["instructions"],
                "score": answer.get("score"),
                "max": len(q["criteria"]) - 1,
                "phrase": self._score_phrase(key),
                "confidence": answer.get("confidence"),
                "legend": legend,
                "probabilities": answer.get("probabilities") or {},
                "inherited": key in self.inherited,
            })
        for key, (instructions, directive) in ELEMENT_QUESTIONS.items():
            if key not in self.answers:
                continue
            rows.append({
                "key": key,
                "type": "noul",
                "question": instructions,
                "probability": self.elements[key]["probability"],
                "included": self.elements[key]["included"],
            })
        return {
            "model": self.model,
            "seed": self.seed,
            "duration_ms": self.duration_ms,
            "cost": self.usage.get("cost"),
            "input_tokens": self.usage.get("input_tokens"),
            "rows": rows,
        }


class Decider:
    def __init__(self, api_key: str, model: str, timeout: int = 30):
        if not api_key:
            raise BlueprintError("OPENROUTER_API_KEY is not set")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def decide(self, state: str, seed: str, extra: dict | None = None) -> Blueprint:
        started = time.monotonic()
        resp = requests.post(
            DECISIONS_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/echooff3/interJEV-explorer",
                "X-Title": "interJEV Explorer",
            },
            json={"model": self.model, "state": state, "questions": build_questions(extra)},
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            raise BlueprintError(f"Decisions API returned {resp.status_code}: {resp.text[:300]}")
        elapsed = int((time.monotonic() - started) * 1000)
        return Blueprint(resp.json(), seed, elapsed, extra_choices=extra)


class MockDecider:
    """Canned answers so JEV_BLUEPRINT works alongside JEV_MOCK."""

    def decide(self, state: str, seed: str, extra: dict | None = None) -> Blueprint:
        rng = random.Random(state)
        archetype = rng.choice(list(CHOICE_QUESTIONS["archetype"]["criteria"]))
        layout = rng.choice(list(CHOICE_QUESTIONS["layout"]["criteria"]))
        palette = rng.choice(list(CHOICE_QUESTIONS["palette"]["criteria"]))
        answers: dict[str, Any] = {
            "archetype": {"type": "choice", "choice": archetype, "confidence": 0.8,
                          "probabilities": {archetype: 0.8}},
            "layout": {"type": "choice", "choice": layout, "confidence": 0.6,
                       "probabilities": {layout: 0.6}},
            "palette": {"type": "choice", "choice": palette, "confidence": 0.6,
                        "probabilities": {palette: 0.6}},
        }
        for key in SCORE_QUESTIONS:
            answers[key] = {"type": "score", "score": round(rng.uniform(0, 2), 2), "confidence": 0.5}
        for key in ELEMENT_QUESTIONS:
            answers[key] = {"type": "noul", "noul": round(rng.random(), 2)}
        for key, q in (extra or {}).items():
            pick = rng.choice(list(q["criteria"]))
            answers[key] = {"type": "choice", "choice": pick, "confidence": 0.5,
                            "probabilities": {pick: 0.5}}
        return Blueprint({"model": "mock-decisions", "answers": answers}, seed, 0,
                         extra_choices=extra)


def enabled() -> bool:
    return os.environ.get("JEV_BLUEPRINT", "").lower() in ("1", "true", "yes", "on")


def get_decider():
    if os.environ.get("JEV_MOCK", "").lower() in ("1", "true", "yes"):
        return MockDecider()
    return Decider(
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        model=os.environ.get("JEV_DECISIONS_MODEL", DEFAULT_MODEL),
    )
