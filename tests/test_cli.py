import contextlib
import io
import json

import pytest

from gsrender.cli import main


@pytest.fixture
def mini(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    return p


def _run(argv):
    out = io.StringIO()
    with pytest.raises(SystemExit) as ei:
        with contextlib.redirect_stdout(out):
            main(argv)
    return ei.value.code, json.loads(out.getvalue() or "{}")


def test_render_svg(mini):
    code, payload = _run(["render", "g", "--corpus", str(mini)])
    assert code == 0 and payload["status"] == "ok"
    assert payload["data"]["svg"].startswith("<svg")


def test_render_font_alias_serif(mini):
    assert _run(["render", "g", "--corpus", str(mini), "--font", "serif"])[0] == 0


def test_unknown_glyph_exit3_with_hints(mini):
    code, payload = _run(["render", "nope", "--corpus", str(mini)])
    assert code == 3 and payload["status"] == "error"
    assert any("list" in h.get("action", "") for h in payload["hints"])


def test_cycle_exit4(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph a\nref b box(0,0,100,100)\n\nglyph b\nref a box(0,0,100,100)\n",
                 encoding="utf-8")
    code, payload = _run(["render", "a", "--corpus", str(p)])
    assert code == 4 and "cycle" in payload["data"]["error"]


def test_resolve_reports_closure(mini):
    code, payload = _run(["resolve", "g", "--corpus", str(mini)])
    assert code == 0
    assert payload["data"]["closure"] == ["g"]
    assert payload["data"]["dangling"] == []


def test_inspect(mini):
    code, payload = _run(["inspect", "g", "--corpus", str(mini)])
    assert payload["data"]["ops"]["stroke"] == 1


def test_list_like(mini):
    code, payload = _run(["list", "--corpus", str(mini), "--like", "g*"])
    assert payload["data"]["names"] == ["g"]


def test_compare_two_names(mini):
    code, payload = _run(["compare", "g", "g", "--corpus", str(mini)])
    assert code == 0 and payload["data"]["iou"] == 1.0


def test_sample_reproducible(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(20)), encoding="utf-8")
    _, r1 = _run(["sample", "--corpus", str(p), "--n", "5", "--seed", "1"])
    _, r2 = _run(["sample", "--corpus", str(p), "--n", "5", "--seed", "1"])
    assert r1["data"]["names"] == r2["data"]["names"]
