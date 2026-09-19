# tests/test_pen_rules.py
import pytest

from glyphsmith.legacy_kurgm.rstroke import RStroke
from glyphsmith.pen.graph import build
from glyphsmith.pen.style import Style, ladder

KOU = [(1, 0, 0, 40, 40, 160, 40, 0, 0, 0, 0),      # top horizontal
       (1, 0, 0, 160, 40, 160, 160, 0, 0, 0, 0),    # right vertical
       (1, 0, 0, 40, 160, 160, 160, 0, 0, 0, 0),    # bottom horizontal
       (1, 0, 0, 40, 40, 40, 160, 0, 0, 0, 0)]      # left vertical


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


def test_a_rule_that_matches_nothing_is_not_an_error():
    s = Style.load("sans-hei")           # no rules at all
    g = build([RStroke(*r) for r in KOU])
    s.apply(g)                            # must not raise
    bare = build([RStroke(1, 0, 4, 60, 15, 60, 181, 0, 0, 0, 0)])
    Style.load("serif-song").apply(bare)  # hook with nothing to its left
