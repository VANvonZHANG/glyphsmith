import json

import pytest

from gsf.kage2 import parse_kage2

from glyphsmith.pen.backend import expand_to_graph, plan_to_dict


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
