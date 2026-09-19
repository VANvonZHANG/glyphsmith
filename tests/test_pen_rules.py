# tests/test_pen_rules.py
import pathlib
import tempfile

import pytest

from glyphsmith.legacy_kurgm.rstroke import RStroke
from glyphsmith.pen.graph import build
from glyphsmith.pen.style import Style, ladder

KOU = [(1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0),      # top horizontal
       (1, 0, 0, 160, 40, 160, 160, 0, 0, 0, 0),    # right vertical
       (1, 0, 0, 40, 160, 160, 160, 0, 0, 0, 0),    # bottom horizontal
       (1, 0, 0, 40, 40, 40, 160, 0, 0, 0, 0)]      # left vertical

# A vertical at x=60 spanning y 15..181, and a quad whose tail hook sits at
# (104,91): the hook's nearest left neighbour is 44 away.
HOOK_GRAPH = [RStroke(1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0),
              RStroke(2, 0, 4, 18, 122, 63, 107, 104, 91, 0, 0)]


def variant(rule: str) -> Style:
    """serif-song with its own rule block replaced by `rule` (2-space indented)."""
    text = pathlib.Path(Style.builtin_dir() / "serif-song.yaml").read_text(
        encoding="utf-8")
    cut = text[:text.index("rules:")] + "rules:\n" + rule
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "s.yaml"
        p.write_text(cut, encoding="utf-8")
        return Style.load(p)


def test_ladder_is_piecewise_constant():
    steps = [[0, 0.25], [15, 0.35], [30, 0.5], [45, 0.7], [60, 1.0]]
    assert ladder(0, steps) == pytest.approx(0.25)
    assert ladder(14.9, steps) == pytest.approx(0.25)
    assert ladder(15, steps) == pytest.approx(0.35)
    assert ladder(44, steps) == pytest.approx(0.5)
    assert ladder(1000, steps) == pytest.approx(1.0)


def test_suppress_fires_on_a_tail_meets_vertical():
    s = Style.load("serif-song")
    g = build([RStroke(*r) for r in KOU])
    plans = s.apply(g)
    # stroke 0's tail (160,40) meets stroke 1's head → its wedge is suppressed
    assert plans[0].decorations == []
    # the bottom horizontal's tail (160,160) meets the right vertical's tail too
    assert plans[2].decorations == []
    # no rule touches the two verticals
    assert plans[1].decorations == [] and plans[3].decorations == []
    # and the horizontals still get a wedge where nothing meets (a bare 一)
    bare = build([RStroke(1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0)])
    assert [d.kind for d in s.apply(bare)[0].decorations] == ["wedge"]


def test_scale_uses_the_ladder_on_the_nearest_vertical_distance():
    s = Style.load("serif-song")
    # a vertical at x=60 spanning y 15..181, and a stroke whose tail hook sits
    # at (104,91): the nearest left vertical is 44 away → ladder → 0.5
    g = build([RStroke(1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0),
               RStroke(2, 0, 4, 18, 122, 63, 107, 104, 91, 0, 0)])
    plans = s.apply(g)
    hook = [d for d in plans[1].decorations if d.kind == "hook"]
    assert len(hook) == 1
    assert hook[0].length == pytest.approx(2.5 * 0.5)


def test_scale_is_multiplicative_across_rules():
    from glyphsmith.pen.style import Style as S
    import pathlib, tempfile
    text = pathlib.Path(S.builtin_dir() / "serif-song.yaml").read_text(encoding="utf-8")
    twice = text.replace(
        "  - id: hane-shortens-near-vertical",
        """  - id: halve-again
    when: {rel: near, from: hook, to: vertical, side: left}
    then:
      scale:
        hook:
          length: 0.5
  - id: hane-shortens-near-vertical""")
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "s.yaml"
        p.write_text(twice, encoding="utf-8")
        s2 = S.load(p)
    g = build([RStroke(1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0),
               RStroke(2, 0, 4, 18, 122, 63, 107, 104, 91, 0, 0)])
    plans = s2.apply(g)
    hook = [d for d in plans[1].decorations if d.kind == "hook"][0]
    assert hook.length == pytest.approx(2.5 * 0.5 * 0.5)


def test_near_honours_the_from_filter():
    # The subject is a rising stroke whose tail is a hook. `from: horizontal`
    # used to be read only to pick the anchor end, so the rule fired anyway.
    s = variant("  - id: near-from-horizontal\n"
                "    when: {rel: near, from: horizontal, to: vertical, side: left}\n"
                "    then: {scale: {hook: {length: 0.5}}}\n")
    g = build(HOOK_GRAPH)
    assert g.node(1).orientation == "rising"
    assert [d.length for d in s.apply(g)[1].decorations] == [2.5], \
        "the subject is not a horizontal, so the rule must not fire"


def test_near_honours_an_ending_word_in_to():
    # `to` may name a GSF ending word (see `_check_rules`). `graph.nearest` can
    # only filter bands, so passing the word through made the rule silently dead.
    s = variant("  - id: near-to-heel\n"
                "    when: {rel: near, from: hook, to: heel-ll, side: left}\n"
                "    then: {scale: {hook: {length: 0.5}}}\n")
    hook = RStroke(2, 0, 4, 18, 122, 63, 107, 104, 91, 0, 0)
    heel = RStroke(1, 0, 13, 60, 15, 60, 181, 0, 0, 0, 0)
    g = build([heel, hook])
    assert g.node(0).tail == "heel-ll"
    assert s.apply(g)[1].decorations[0].length == pytest.approx(2.5 * 0.5)

    # The nearest hit is the condition: when it misses `to`, the rule does not
    # fire even though a farther node would satisfy it.
    g = build([RStroke(1, 0, 0, 60, 15, 60, 181, 0, 0, 0, 0),
               RStroke(3, 0, 13, 10, 15, 10, 181, 0, 0, 0, 0), hook])
    assert [n.tail for n in g.nodes] == ["flat", "heel-ll", "hook"]
    assert s.apply(g)[2].decorations[0].length == pytest.approx(2.5), \
        "the nearest left node is flat, not heel-ll"


def test_near_band_to_selects_the_nearest_node_of_that_band():
    # A band `to` (here the shipped 钩长 rule's `to: vertical`) must SELECT the
    # nearest node of that band via `want=`. Asking for the unfiltered nearest
    # and rejecting it when it is not the band goes dead whenever a non-vertical
    # lies closer, whereas legacy scans verticals only (mincho.py:297-301).
    # The subject's hook tail is at (104,91); the horizontal is 24 away, the
    # vertical 64, so the rule must scale by 64 (ladder bin 60 → 0.7).
    s = Style.load("serif-song")
    vertical = RStroke(1, 0, 0, 40, 15, 40, 181, 0, 0, 0, 0)     # x=40 → 64
    hook = RStroke(2, 0, 4, 18, 122, 63, 107, 104, 91, 0, 0)     # tail (104,91)
    nearer_h = RStroke(1, 0, 0, 10, 91, 80, 91, 0, 0, 0, 0)      # y=91 → 24
    g = build([vertical, hook, nearer_h])
    assert [n.orientation for n in g.nodes] == ["vertical", "rising",
                                                "horizontal"]
    assert g.node(1).tail == "hook"
    # the premise: the nearest node of *any* band is the horizontal, so a
    # post-checked band filter would kill the rule instead of scaling it
    any_hit = g.nearest(1, at="tail", side="left")
    band_hit = g.nearest(1, at="tail", want="vertical", side="left")
    assert any_hit[0].id == 2 and any_hit[1] == pytest.approx(24)
    assert band_hit[0].id == 0 and band_hit[1] == pytest.approx(64)
    hook_deco = [d for d in s.apply(g)[1].decorations if d.kind == "hook"]
    assert len(hook_deco) == 1
    assert hook_deco[0].length == pytest.approx(2.5 * 0.7), \
        "the rule must fire on the vertical's distance, not the nearer horizontal's"


def test_the_shipped_step_table_is_the_legacy_staircase():
    # legacy: adj = 7 - floor(mn / 15) (mincho.py:303) and the hook's length
    # factor is 1 - adj / 10 (mincho_cd.py:457). The table must encode that law
    # in every bin, not a lookalike that agrees only at the pinned 44 -> 0.5.
    s = Style.load("serif-song")
    steps = s.rules[-1]["then"]["scale"]["hook"]["length"]["steps"]
    assert steps == [[0, 0.3], [15, 0.4], [30, 0.5], [45, 0.6],
                     [60, 0.7], [75, 0.8], [90, 0.9], [105, 1.0]]
    for mn in (0, 14, 15, 29, 30, 44, 45, 59, 60, 74, 75, 89, 90, 104, 105, 119):
        legacy = 1 - (7 - mn // 15) / 10
        assert ladder(mn, steps) == pytest.approx(legacy), f"mn={mn}"
    # Above the last bin legacy's adj would go negative; the ladder's last entry
    # is the cap (`ladder` always clamps).
    assert ladder(1000, steps) == pytest.approx(1.0)


def test_a_rule_that_matches_nothing_is_not_an_error():
    s = Style.load("sans-hei")           # no rules at all
    g = build([RStroke(*r) for r in KOU])
    s.apply(g)                            # must not raise
    bare = build([RStroke(1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0)])
    Style.load("serif-song").apply(bare)  # hook with nothing to its left
