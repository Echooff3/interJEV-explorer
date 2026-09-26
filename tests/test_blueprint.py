import pytest

from interjev import blueprint as bp


def make(answers, seed="seed"):
    return bp.Blueprint({"model": "m", "answers": answers, "usage": {}}, seed, 0)


def test_noul_is_sampled_not_thresholded():
    """A 0.5 probability must not always resolve the same way."""
    answers = {k: {"type": "noul", "noul": 0.5} for k in bp.ELEMENT_QUESTIONS}
    verdicts = {
        tuple(make(answers, f"seed-{i}").elements[k]["included"] for k in bp.ELEMENT_QUESTIONS)
        for i in range(25)
    }
    assert len(verdicts) > 1


def test_sampling_is_stable_for_a_seed():
    answers = {k: {"type": "noul", "noul": 0.5} for k in bp.ELEMENT_QUESTIONS}
    a, b = make(answers, "same"), make(answers, "same")
    assert a.elements == b.elements


@pytest.mark.parametrize("probability,expected", [(0.0, False), (1.0, True)])
def test_certain_probabilities_are_respected(probability, expected):
    answers = {k: {"type": "noul", "noul": probability} for k in bp.ELEMENT_QUESTIONS}
    assert all(v["included"] is expected for v in make(answers).elements.values())


def test_score_phrase_blends_adjacent_levels():
    answers = {"era": {"type": "score", "score": 1.5,
                       "legend": {"0": "old", "1": "middling", "2": "new"}}}
    phrase = make(answers)._score_phrase("era")
    assert "middling" in phrase and "new" in phrase

    answers["era"]["score"] = 1.95
    assert make(answers)._score_phrase("era") == "new"


def test_identity_is_inherited_and_marked():
    answers = {"archetype": {"type": "choice", "choice": "shop", "probabilities": {}},
               "layout": {"type": "choice", "choice": "magazine_grid", "probabilities": {}}}
    page = make(answers)
    page.adopt_identity({"archetype": {"type": "choice", "choice": "news", "probabilities": {}}})

    assert page._choice("archetype") == "news"
    assert page._choice("layout") == "magazine_grid"
    rows = {r["key"]: r for r in page.inspector()["rows"]}
    assert rows["archetype"]["inherited"] is True
    assert rows["layout"]["inherited"] is False


def test_directives_split_included_from_omitted():
    answers = {k: {"type": "noul", "noul": 1.0 if k == "comments" else 0.0}
               for k in bp.ELEMENT_QUESTIONS}
    text = make(answers).prompt_text()
    include, omit = text.split("Do NOT include:")
    assert "comments section" in include
    assert "paywall" in omit


def test_questions_payload_covers_every_type():
    q = bp.build_questions()
    assert {v["type"] for v in q.values()} == {"choice", "score", "noul"}
    assert len(q) == len(bp.CHOICE_QUESTIONS) + len(bp.SCORE_QUESTIONS) + len(bp.ELEMENT_QUESTIONS)
