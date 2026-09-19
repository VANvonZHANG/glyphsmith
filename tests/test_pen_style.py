# tests/test_pen_style.py
import re

import pytest

from glyphsmith.pen.style import ENDING_WORDS, Style, StyleError

GOOD = """
name: probe
genre: serif
endings_source: data
width_profile:
  horizontal:    [[0.0, 4.0], [1.0, 4.5]]
  vertical:      [[0.0, 12.0], [1.0, 11.0]]
  left-falling:  [[0.0, 9.0], [1.0, 0.8]]
  right-falling: [[0.0, 5.0], [1.0, 1.0]]
  rising:        [[0.0, 7.0], [1.0, 0.8]]
endings:
  flat: {}
  join-h: {}
  tip: {min_width: 0.15}
  corner-ul: {join: miter}
  corner-ur: {join: miter}
  join-v: {}
  hook: {length: 2.5, width: 1.0}
  heel-ll: {length: 0.1}
  heel-lr: {length: 0.1}
  heel-ll-old: {length: 0.1}
  heel-ll-new: {length: 0.1}
  cap-t: {}
decorations:
  wedge: {on: horizontal, at: tail, shape: triangle, size: 3.0}
caps: {default: butt}
joins: {default: miter, bend: round}
rules: []
"""


def write(tmp_path, text, name="probe.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_a_valid_style(tmp_path):
    s = Style.load(write(tmp_path, GOOD))
    assert s.name == "probe" and s.genre == "serif"
    assert s.endings_source == "data"
    assert set(s.width_profile) == {"horizontal", "vertical", "left-falling",
                                    "right-falling", "rising"}
    assert s.decorations["wedge"]["size"] == 3.0


def test_a_bare_on_key_is_not_yaml_1_1_true(tmp_path):
    # PyYAML is YAML 1.1, where the bare key `on` resolves to True, and the file
    # would fail as "unknown key True" instead of naming `on`.
    s = Style.load(write(tmp_path, GOOD))
    assert s.decorations["wedge"]["on"] == "horizontal"


def test_ending_words_are_the_gsf_union_of_twelve():
    assert len(ENDING_WORDS) == 12
    assert "heel-ll-old" in ENDING_WORDS and "corner-ur" in ENDING_WORDS


@pytest.mark.parametrize("mutate,needle", [
    (lambda t: t.replace("genre: serif", "genre: serif\nbogus_key: 1"), "bogus_key"),
    (lambda t: t.replace("hook: {length: 2.5, width: 1.0}", "hookk: {length: 3.0}"), "hookk"),
    (lambda t: t.replace("  rising:        [[0.0, 7.0], [1.0, 0.8]]\n", ""), "rising"),
    (lambda t: t.replace("  cap-t: {}", ""), "cap-t"),
    (lambda t: t.replace("endings_source: data", "endings_source: whatever"), "endings_source"),
    (lambda t: t.replace("[[0.0, 4.0], [1.0, 4.5]]", "[[0.0, -4.0], [1.0, 4.5]]"), "horizontal"),
    (lambda t: t.replace("caps: {default: butt}", "caps: {default: squarish}"), "squarish"),
    (lambda t: t.replace("joins: {default: miter, bend: round}",
                         "joins: {default: miter, bend: roound}"), "roound"),
    (lambda t: t.replace("rules: []", "rules: [{when: {rel: meets}, then: {explode: 1}}]"), "explode"),
    (lambda t: t.replace("rules: []", "rules: [{when: {rel: hugs}, then: {suppress: wedge}}]"), "hugs"),
    (lambda t: t.replace("rules: []", "rules: [{when: {rel: meets}, then: {suppress: sparkle}}]"), "sparkle"),
    # A scalar where the twelve-word table belongs. The block is cut along with
    # the key, or the leftover indented lines are a YAML syntax error and the
    # mapping check is never reached.
    (lambda t: re.sub(r"(?m)^endings:\n(?:  \S.*\n)*", "endings: 5\n", t),
     "endings: expected a mapping"),
    # `scale` takes a per-word table, not a factor: a number here would reach
    # `.items()` and escape as an AttributeError naming nothing.
    (lambda t: t.replace("rules: []",
                         "rules: [{when: {rel: meets}, then: {scale: 2.0}}]"),
     "then.scale: expected a mapping"),
    # `scale` multiplies a number that is already on a Decoration, so its params
    # are exactly the numeric Decoration fields. The ending vocabulary is wider:
    # `shape`/`min_width`/`miter_limit` used to reach `_dc_replace(d, **upd)` and
    # escaped as `TypeError: Decoration.__init__() got an unexpected keyword
    # argument`, and `join: 0.5` as "can't multiply sequence by non-int".
    (lambda t: t.replace("rules: []",
                         "rules: [{when: {rel: meets}, then: {scale: {hook: {shape: 1.0}}}}]"),
     "shape"),
    (lambda t: t.replace("rules: []",
                         "rules: [{when: {rel: meets}, then: {scale: {hook: {min_width: 0.5}}}}]"),
     "min_width"),
    (lambda t: t.replace("rules: []",
                         "rules: [{when: {rel: meets}, then: {scale: {hook: {miter_limit: 3.0}}}}]"),
     "miter_limit"),
    (lambda t: t.replace("rules: []",
                         "rules: [{when: {rel: meets}, then: {scale: {hook: {join: 0.5}}}}]"),
     "join"),
])
def test_validation_is_loud(tmp_path, mutate, needle):
    with pytest.raises(StyleError) as e:
        Style.load(write(tmp_path, mutate(GOOD)))
    assert needle in str(e.value), f"message must name the offending key: {e.value}"


def test_scale_accepts_every_numeric_decoration_field(tmp_path):
    # The three params a scale can act on, in both the scalar and the ladder
    # form; anything else is rejected above.
    for field, value in (("length", "0.5"),
                         ("size", "{by: distance, steps: [[0, 0.5]]}"),
                         ("width", "0.5")):
        text = GOOD.replace(
            "rules: []",
            "rules: [{when: {rel: meets}, then: {scale: {hook: {"
            + field + ": " + value + "}}}}]")
        s = Style.load(write(tmp_path, text))
        assert field in s.rules[0]["then"]["scale"]["hook"]


def test_clamp_false_is_rejected_because_the_ladder_always_clamps(tmp_path):
    # `ladder` clamps by construction (its first entry's factor applies below it
    # and its last above), so `clamp: false` is unrepresentable; accepting it
    # would let the author believe it did something.
    text = GOOD.replace(
        "rules: []",
        "rules: [{when: {rel: meets}, then: {scale: {hook: "
        "{length: {by: distance, steps: [[0, 0.5]], clamp: false}}}}}]")
    with pytest.raises(StyleError) as e:
        Style.load(write(tmp_path, text))
    assert "clamp" in str(e.value) and "always clamps" in str(e.value)

    # `clamp: true` stays legal, as documentation of what already happens.
    ok = GOOD.replace(
        "rules: []",
        "rules: [{when: {rel: meets}, then: {scale: {hook: "
        "{length: {by: distance, steps: [[0, 0.5]], clamp: true}}}}}]")
    s = Style.load(write(tmp_path, ok))
    assert s.rules[0]["then"]["scale"]["hook"]["length"]["clamp"] is True


def test_at_mid_is_rejected_under_rel_near(tmp_path):
    # `graph.nearest` anchors at an end: `_end_point` maps anything that is not
    # "head" to the tail, so `at: mid` under `rel: near` would silently be the
    # tail. It is a schema-valid value for every other relation.
    text = GOOD.replace(
        "rules: []",
        "rules: [{when: {rel: near, from: hook, at: mid}, then: {suppress: hook}}]")
    with pytest.raises(StyleError) as e:
        Style.load(write(tmp_path, text))
    assert "mid" in str(e.value) and "near" in str(e.value)

    ok = GOOD.replace(
        "rules: []",
        "rules: [{when: {rel: meets, at: mid}, then: {suppress: hook}}]")
    Style.load(write(tmp_path, ok))


def test_malformed_yaml_reports_the_file(tmp_path):
    p = write(tmp_path, "name: probe\nwidth_profile: [oops\n")
    with pytest.raises(StyleError) as e:
        Style.load(p)
    assert str(p) in str(e.value)


def test_unknown_style_name_lists_the_available_ones():
    with pytest.raises(StyleError) as e:
        Style.load("no-such-style-anywhere")
    assert "no-such-style-anywhere" in str(e.value)
    assert "serif-song" in str(e.value)


def test_builtin_style_loads_by_name():
    s = Style.load("serif-song")
    assert s.name == "serif-song" and s.genre == "serif"


def test_genre_aliases_resolve():
    from glyphsmith.pen.style import resolve_genre
    assert resolve_genre("mincho") == "serif"
    assert resolve_genre("gothic") == "sans"
    assert resolve_genre("hei") == "sans"
    assert resolve_genre("serif") == "serif"
    with pytest.raises(StyleError):
        resolve_genre("comic")


def test_all_three_styles_load():
    from glyphsmith.pen.style import available
    assert available() == ["sans-hei", "sans-round", "serif-song"]
    for name in available():
        s = Style.load(name)
        assert s.name == name
        assert set(s.width_profile) == {"horizontal", "vertical", "left-falling",
                                        "right-falling", "rising"}
        assert set(s.endings) == set(ENDING_WORDS)


def test_hei_and_round_differ_in_exactly_two_lines():
    # The whole point of the redesign: 宋/黑/圆 used to be three code tables
    # (kagecd.js / kagedf.js / a third copy in HowardZorn). Here hei -> round is
    # a two-line diff, and nothing else.
    # NOTE FOR REVIEWERS: the near-duplication of these two YAML files is
    # deliberate and is precisely what this test asserts. Do not "DRY" them with
    # YAML anchors — that would destroy the evidence. (Controller ruling,
    # 2026-09-19.)
    base = Style.builtin_dir()
    a = (base / "sans-hei.yaml").read_text(encoding="utf-8").splitlines()
    b = (base / "sans-round.yaml").read_text(encoding="utf-8").splitlines()
    assert len(a) == len(b), "the two files must stay line-for-line comparable"
    diff = [x.split(":")[0] for x, y in zip(a, b) if x != y]
    assert diff == ["name", "caps", "joins"], diff


def test_hei_is_uniform_width_and_ignores_the_wedge():
    s = Style.load("sans-hei")
    assert {tuple(map(tuple, v)) for v in s.width_profile.values()} == {((0.0, 10.0), (1.0, 10.0))}
    assert s.decorations == {}, "hei-ti has no うろこ"
    assert s.endings["hook"]["join"] == "miter"


def test_round_differs_from_hei_only_in_caps_and_joins():
    hei, rnd = Style.load("sans-hei"), Style.load("sans-round")
    assert hei.width_profile == rnd.width_profile
    assert hei.endings == rnd.endings
    assert rnd.caps["default"] == "round" and rnd.joins["default"] == "round"


from glyphsmith.pen.nib import StrokePlan
from glyphsmith.pen.style import Decoration, profile_at


def test_profile_at_interpolates_and_clamps():
    prof = [(0.0, 4.0), (0.5, 10.0), (1.0, 2.0)]
    assert profile_at(prof, 0.0) == pytest.approx(4.0)
    assert profile_at(prof, 0.25) == pytest.approx(7.0)
    assert profile_at(prof, 0.5) == pytest.approx(10.0)
    assert profile_at(prof, 0.75) == pytest.approx(6.0)
    assert profile_at(prof, 1.0) == pytest.approx(2.0)
    assert profile_at(prof, -1.0) == pytest.approx(4.0)
    assert profile_at(prof, 9.0) == pytest.approx(2.0)


def node(**kw):
    from glyphsmith.pen.graph import Node
    base = dict(id=0, a1_100=1, a1_opt=0, a3_opt=0, type="line", orientation="horizontal",
                head="flat", tail="flat", length=160.0, bbox=(20.0, 50.0, 180.0, 50.0),
                centerline=((20.0, 50.0), (180.0, 50.0)),
                pure_geometry=False)
    base.update(kw)
    return Node(**base)


def test_plan_uses_the_band_profile():
    s = Style.load("serif-song")
    p = s.plan_for(node(orientation="horizontal"))
    assert p.widths == [pytest.approx(4.0), pytest.approx(4.5)]
    v = s.plan_for(node(orientation="vertical"))
    assert v.widths == [pytest.approx(12.0), pytest.approx(11.0)]


def test_tip_clamps_the_end_width():
    s = Style.load("serif-song")
    p = s.plan_for(node(orientation="vertical", tail="tip"))   # min_width = 0.15
    # min_width is a multiple of *that end's* width (spec §4.2.2: the end's width
    # becomes min(profile end, min_width x profile end)), and the vertical band
    # ends at 11.0, not at the 12.0 it starts from — so the clamp is 11 * 0.15.
    # The pre-implementation brief had 12.0 * 0.15 here, which contradicts its own
    # band-profile test two tests above.
    assert p.widths[-1] == pytest.approx(11.0 * 0.15)
    assert p.widths[0] == pytest.approx(12.0), "only the tip end is affected"


def test_pure_geometry_ignores_endings_and_decorations():
    s = Style.load("serif-song")
    plain = s.plan_for(node(tail="hook", pure_geometry=True, a1_opt=1))
    assert plain.decorations == []
    assert plain.widths == [pytest.approx(4.0), pytest.approx(4.5)]
    assert plain.cap_tail == "butt"


def test_join_ends_force_butt_caps():
    s = Style.load("serif-song")
    p = s.plan_for(node(head="join-h", tail="join-v"))
    assert p.cap_head == "butt" and p.cap_tail == "butt"
    assert p.decorations == [], "a junction end never carries a decoration"


def test_wedge_is_added_only_where_the_tail_is_flat():
    s = Style.load("serif-song")
    yes = s.plan_for(node(tail="flat"))
    assert [(d.kind, d.at) for d in yes.decorations] == [("wedge", "tail")]
    no = s.plan_for(node(tail="tip"))
    assert no.decorations == []


def test_wedge_is_band_filtered():
    s = Style.load("serif-song")
    assert s.plan_for(node(orientation="vertical")).decorations == []


def test_unmapped_tail_code_plans_with_no_ending_geometry():
    # `graph.build` deliberately keeps a GSF tail code that misses TAIL_NAMES as
    # the raw int, and 8 is the corpus's most common such code (33,200 strokes in
    # a 339,530-stroke sample; TAIL_NAMES holds only 0/2/4/7/13/23/24/32/313/413).
    # An unnameable end must plan, not crash, and must not silently pretend the
    # style has something for it.
    s = Style.load("serif-song")
    p = s.plan_for(node(tail=8))
    assert p.widths[-1] == pytest.approx(4.5), \
        "no width modulation: tip.min_width belongs to a named ending"
    assert p.decorations == [], \
        "no decoration: the wedge is only for an end the data left `flat`"
    assert p.cap_tail == s.cap_for("horizontal"), "caps stay at the band default"
    assert p.warnings == ["unmapped ending code 8 at tail"]


def test_unmapped_head_code_plans_with_no_ending_geometry():
    s = Style.load("serif-song")
    p = s.plan_for(node(head=99))
    assert p.widths[0] == pytest.approx(4.0), \
        "no width modulation: tip.min_width belongs to a named ending"
    assert [d.at for d in p.decorations] == ["tail"], \
        "the nameable tail keeps its wedge; the unnameable head adds none"
    assert p.cap_head == s.cap_for("horizontal"), "caps stay at the band default"
    assert p.warnings == ["unmapped ending code 99 at head"]


def test_nameable_ending_codes_produce_no_warning():
    s = Style.load("serif-song")
    assert s.plan_for(node(head="join-h", tail="tip")).warnings == []


def test_a_corpus_code_missing_from_the_name_table_is_reported_end_to_end():
    from glyphsmith.pen.graph import build
    from glyphsmith.legacy_kurgm.rstroke import RStroke
    s = Style.load("serif-song")
    # a3 = 8: the code graph.build cannot name, so it hands back the raw int.
    g = build([RStroke(1, 0, 8, 14, 92, 186, 92, 0, 0, 0, 0)])
    assert g.nodes[0].tail == 8, "the data layer must not coerce the code"
    p = s.apply(g)[0]
    assert p.warnings == ["unmapped ending code 8 at tail"]


def test_endings_source_style_ignores_the_data_words():
    text = _GOOD_WITH_STYLE_SOURCE = GOOD.replace("endings_source: data",
                                                  "endings_source: style")
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "s.yaml"
        p.write_text(text, encoding="utf-8")
        s = Style.load(p)
    hooked = s.plan_for(node(tail="hook"))
    assert hooked.decorations == [], "decorations still come from `decorations`"
    assert s.plan_for(node(tail="tip")).widths[-1] == pytest.approx(4.5), \
        "the tip clamp must not apply when the data endings are ignored"


def test_corner_ending_overrides_the_bend_join():
    s = Style.load("serif-song")                 # joins: {default: miter, bend: round}
    bent = node(type="bend", centerline=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)))
    assert s.plan_for(bent).joins == ["round"]
    bent_corner = node(type="bend", head="corner-ul",
                       centerline=((0.0, 0.0), (100.0, 0.0), (100.0, 100.0)))
    assert s.plan_for(bent_corner).joins == ["miter"]


def test_apply_returns_one_plan_per_node():
    from glyphsmith.pen.graph import build
    from glyphsmith.legacy_kurgm.rstroke import RStroke
    s = Style.load("serif-song")
    g = build([RStroke(1, 0, 0, 14, 92, 186, 92, 0, 0, 0, 0),
               RStroke(1, 0, 4, 100, 17, 100, 185, 0, 0, 0, 0)])
    plans = s.apply(g)
    assert set(plans) == {0, 1}
    assert all(isinstance(p, StrokePlan) for p in plans.values())
    assert [d.kind for d in plans[1].decorations] == ["hook"]
