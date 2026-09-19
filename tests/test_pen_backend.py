import json

import pytest

from gsf.kage2 import parse_kage2

from glyphsmith.compare import compare
from glyphsmith.legacy_kurgm import LegacyKurgmBackend
from glyphsmith.pen.backend import expand_to_graph, plan_to_dict
from glyphsmith.protocol import RenderOptions, get_backend


class R:
    def __init__(self, g):
        self.name, self.glyph, self.parts, self.warnings = g.name, g, {g.name: g}, []


def test_expand_to_graph_separates_strokes_from_transform_ops():
    g = parse_kage2("1:0:0:20:50:180:50$0:99:0:0:0:200:200:rot:0:0", "t")
    graph, plans, items, warnings, counts = expand_to_graph(R(g), "serif-song")
    assert len(graph.nodes) == 1
    assert sum(1 for it in items if isinstance(it, tuple)) == 1
    assert set(plans) == {0}
    assert counts == {"strokes": 1, "degenerate": 0, "empty": 0}


def test_counts_read_degeneracy_from_should_degrade_not_from_warnings():
    # A tail code the name table cannot name (8 is missing from TAIL_NAMES)
    # is a data-quality notice on plan.warnings - not a degeneracy. Counting
    # `if plan.warnings` would call ~12% of real strokes degenerate.
    from glyphsmith.pen.nib import should_degrade

    g = parse_kage2("1:0:8:20:50:180:50", "t")
    _graph, plans, _items, _w, counts = expand_to_graph(R(g), "serif-song")
    assert plans[0].warnings == ["unmapped ending code 8 at tail"]
    assert not should_degrade(plans[0])
    assert counts["degenerate"] == 0

    zero_len = parse_kage2("1:0:0:5:5:5:5", "t")
    _graph, plans, _items, _w, counts = expand_to_graph(R(zero_len), "serif-song")
    assert should_degrade(plans[0])
    assert counts == {"strokes": 1, "degenerate": 1, "empty": 0}


def test_plan_to_dict_is_json_ready():
    g = parse_kage2("1:0:0:20:50:180:50", "t")
    _graph, plans, _items, _w, _counts = expand_to_graph(R(g), "serif-song")
    d = plan_to_dict(plans[0])
    json.dumps(d)
    assert d["widths"] == [4.0, 4.5]
    assert [x["kind"] for x in d["decorations"]] == ["wedge"]


def test_graph_command_emits_the_graph_and_plans(capsys, tmp_path):
    from glyphsmith.cli import main
    corpus = tmp_path / "c.gsf"
    # Not the brief's `gsf/1\nname: probe\n1:0:0:20:50:180:50\n`: --corpus takes a
    # GSF-DSL file (Corpus.from_gsf reads `glyph`/`stroke` blocks; a KAGE row under
    # a `name:` header loads as an EMPTY corpus -> exit 3). This block is
    # byte-identical input: Stroke('1','0','0','20','50','180','50').
    corpus.write_text("gsf/1\nglyph probe\nstroke line head flat tail flat (20,50)->(180,50)\n",
                      encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["graph", "probe", "--corpus", str(corpus), "--plans"])
    assert e.value.code == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["data"]["graph"]["nodes"][0]["orientation"] == "horizontal"
    assert out["data"]["graph"]["edges"] == []
    assert out["data"]["plans"]["0"]["cap_tail"] == "butt"


def test_graph_command_reports_an_unknown_style(tmp_path, capsys):
    from glyphsmith.cli import main
    corpus = tmp_path / "c.gsf"
    # Not the brief's `gsf/1\nname: probe\n1:0:0:20:50:180:50\n`: --corpus takes a
    # GSF-DSL file (Corpus.from_gsf reads `glyph`/`stroke` blocks; a KAGE row under
    # a `name:` header loads as an EMPTY corpus -> exit 3). This block is
    # byte-identical input: Stroke('1','0','0','20','50','180','50').
    corpus.write_text("gsf/1\nglyph probe\nstroke line head flat tail flat (20,50)->(180,50)\n",
                      encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["graph", "probe", "--corpus", str(corpus), "--style", "nope"])
    assert e.value.code == 2
    assert "nope" in json.loads(capsys.readouterr().out)["data"]["error"]


def test_pen_backend_registers_on_a_cold_library_import():
    # A subprocess: this module already imports the pen package at module scope,
    # so an in-process assertion could never fail. Cold `import glyphsmith` is
    # what a library user does, and it must register every shipped backend.
    import subprocess
    import sys
    code = ("import glyphsmith; from glyphsmith.protocol import Backend; "
            "assert 'pen' in Backend.available(), Backend.available(); "
            "print('ok')")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"


def test_pen_renders_a_horizontal():
    g = parse_kage2("1:0:0:20:50:180:50", "t")
    o = get_backend("pen").render(R(g), RenderOptions(backend="pen", style="serif-song"))
    assert len(o.contours) == 2, "body + wedge"
    assert all(len(c) >= 3 for c in o.contours)


def test_pen_differs_from_legacy_but_agrees_roughly():
    g = parse_kage2("1:0:0:20:50:180:50$1:0:4:100:17:100:185", "t")
    pen = get_backend("pen").render(R(g), RenderOptions(backend="pen", style="serif-song"))
    leg = LegacyKurgmBackend().render(R(g))
    iou = compare(pen, leg).iou
    assert 0.5 < iou < 1.0, f"same skeleton, different engine: IoU {iou}"


def test_render_separated_gives_one_outline_per_stroke():
    g = parse_kage2("1:0:0:20:50:180:50$1:0:4:100:17:100:185", "t")
    outs = get_backend("pen").render_separated(R(g), RenderOptions(backend="pen"))
    assert len(outs) == 2
    assert all(o.contours for o in outs)


def test_transform_ops_are_applied_to_what_was_drawn_before_them():
    # t97 reflects the accumulated outline vertically: the body of stroke 0 is
    # drawn first, then flipped inside the 200x200 rect
    g = parse_kage2("1:0:0:20:30:180:30$0:97:0:0:0:200:200", "t")
    o = get_backend("pen").render(R(g), RenderOptions(backend="pen"))
    ys = [y for c in o.contours for _x, y, _ in c]
    assert min(ys) > 100.0, "after reflectY about y=100 the stroke moves down"


def test_warnings_are_written_back_on_both_paths():
    g = parse_kage2("-:0:0:0:0:0:0$1:0:0:20:50:180:50", "rawg")
    a, b = R(g), R(g)
    get_backend("pen").render(a, RenderOptions(backend="pen"))
    get_backend("pen").render_separated(b, RenderOptions(backend="pen"))
    assert any("raw op skipped" in w for w in a.warnings)
    assert a.warnings == b.warnings


def test_degraded_strokes_are_reported_through_result_warnings():
    # A hairpin: the two segments nearly reverse (the control polygon turns 177
    # degrees at (200,0)), so the curvature radius at the flattened apex (2.04)
    # is far below the local half-width (5.75) of serif-song's vertical band.
    # NOT the brief's `2:0:0:0:0:200:0:10:0`: all three of its control points sit
    # on y=0, so the quad is collinear, the chord height is 0 and centerline's
    # flattening drops the apex outright - the centerline becomes the straight
    # two-point line [(0,0),(10,0)], curvature_radius returns [] (it needs an
    # interior vertex) and no curvature warning can ever fire. This is the same
    # seven numbers with the last pair transposed, (x3,y3)=(0,10); the chord is
    # then vertical and the degradation really fires
    # (`degraded: curvature radius 2.04 < half-width 5.75 at vertex 5`).
    g = parse_kage2("2:0:0:0:0:200:0:0:10", "hairpin")
    r = R(g)
    get_backend("pen").render(r, RenderOptions(backend="pen", style="serif-song"))
    assert any("curvature" in w for w in r.warnings)


def test_style_option_selects_the_style():
    g = parse_kage2("1:0:0:20:50:180:50", "t")
    song = get_backend("pen").render(R(g), RenderOptions(backend="pen", style="serif-song"))
    hei = get_backend("pen").render(R(g), RenderOptions(backend="pen", style="sans-hei"))
    assert len(song.contours) == 2 and len(hei.contours) == 1


def test_an_empty_style_is_rejected_not_defaulted():
    # T14 review minor (b): `_style_of`'s `or` turned style="" into serif-song,
    # so a caller's empty value read as "nothing wrong" (the no-silent-fallbacks
    # rule). Only a *missing* style falls back now.
    from glyphsmith.pen.style import StyleError
    g = parse_kage2("1:0:0:20:50:180:50", "t")
    with pytest.raises(StyleError):
        get_backend("pen").render(R(g), RenderOptions(backend="pen", style=""))
