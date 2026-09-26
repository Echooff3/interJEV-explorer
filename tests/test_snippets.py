import json
import re

from interjev import assemble, blueprint as bp, components as C
from interjev.copy import PAIR, MockCopyWriter, build_prompt


def make_blueprint(elements=1.0, **choices):
    answers = {
        "palette": {"choice": choices.get("palette", "stark_light")},
        "layout": {"choice": choices.get("layout", "single_column")},
        "era": {"score": choices.get("era", 2.0)},
        "text_density": {"score": 1.0},
        "ad_density": {"score": choices.get("ads", 0.0)},
    }
    for name in C.VARIANT_QUESTIONS:
        answers["variant_" + name] = {"choice": next(iter(C.COMPONENTS[name]))}
    for key in bp.ELEMENT_QUESTIONS:
        answers[key] = {"type": "noul", "noul": elements}
    return bp.Blueprint({"answers": answers}, "seed", 0)


def test_skeleton_contains_no_unresolved_placeholders():
    html = assemble.assemble(make_blueprint()).html
    assert not re.search(r"\{[a-z0-9_]+\}", html)


def test_every_slot_in_the_skeleton_is_requested_from_the_model():
    built = assemble.assemble(make_blueprint())
    in_html = set(re.findall(r'data-slot="([a-z0-9_]+)"', built.html))
    requested = {key for key, _ in built.slots}
    assert in_html == requested


def test_rolled_out_elements_produce_no_markup():
    """The stylesheet always ships every rule; only the body should change."""
    off = assemble.assemble(make_blueprint(elements=0.0))
    body = off.html.split("</head>", 1)[1]
    assert '<section class="comments">' not in body
    assert "Subscribe" not in body
    assert off.components == ["masthead:wordmark", "nav:horizontal", "article:standard",
                              "footer:columns"]

    on = assemble.assemble(make_blueprint(elements=1.0))
    on_body = on.html.split("</head>", 1)[1]
    assert '<section class="comments">' in on_body
    assert "Subscribe" in on_body


def test_layout_choice_changes_the_grid_and_sidebar():
    plain = assemble.assemble(make_blueprint(layout="single_column"))
    sided = assemble.assemble(make_blueprint(layout="sidebar_left"))
    assert "<aside>" not in plain.html
    assert "<aside>" in sided.html


def test_palette_and_era_drive_the_stylesheet():
    dark = assemble.assemble(make_blueprint(palette="dark_mode")).stylesheet
    paper = assemble.assemble(make_blueprint(palette="warm_paper")).stylesheet
    assert C.PALETTES["dark_mode"]["bg"] in dark
    assert dark != paper


def test_fill_escapes_copy_and_sets_the_title():
    html = '<title></title><span data-slot="headline" style="--w:95%"></span>'
    out = assemble.fill(html, {"headline": "Tom & <script>x</script>"}, "Tom")
    assert "<script>x</script>" not in out
    assert "&lt;script&gt;" in out
    assert "<title>Tom</title>" in out


def test_unfilled_slots_keep_their_placeholder():
    html = '<span data-slot="headline" style="--w:95%"></span>'
    assert assemble.fill(html, {}) == html


def test_variant_questions_cover_every_multi_variant_component():
    q = assemble.variant_questions()
    for name in C.VARIANT_QUESTIONS:
        assert set(q["variant_" + name]["criteria"]) == set(C.COMPONENTS[name])


def test_pair_parser_yields_pairs_as_they_complete():
    buffer, cursor, out = "", 0, []
    for piece in ['{"a": "one', '", "b": "he said \\"hi\\"", "c": "thr', 'ee"}']:
        buffer += piece
        for m in PAIR.finditer(buffer, cursor):
            cursor = m.end()
            out.append((m.group(1), json.loads('"' + m.group(2) + '"')))
    assert out == [("a", "one"), ("b", 'he said "hi"'), ("c", "three")]


def test_mock_writer_fills_every_requested_slot():
    built = assemble.assemble(make_blueprint())
    messages = build_prompt("https://x.test/a", built.slots)
    produced = {k for k, _ in MockCopyWriter().stream(messages)}
    assert {key for key, _ in built.slots} <= produced


def test_copy_prompt_never_asks_for_html():
    built = assemble.assemble(make_blueprint())
    system = build_prompt("https://x.test/a", built.slots)[0]["content"]
    assert "Never HTML" in system
