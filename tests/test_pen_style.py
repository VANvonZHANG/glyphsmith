# tests/test_pen_style.py
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
])
def test_validation_is_loud(tmp_path, mutate, needle):
    with pytest.raises(StyleError) as e:
        Style.load(write(tmp_path, mutate(GOOD)))
    assert needle in str(e.value), f"message must name the offending key: {e.value}"


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
