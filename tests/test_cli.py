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


# ── T14 审查修复（M2 写盘契约 / M1 笔数不等 warning）──

@pytest.fixture
def slash(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph a/b\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    return p


def test_render_slash_name_sanitized_to_filename(slash, tmp_path, monkeypatch):
    # 名字里的路径分隔符清洗后写盘（T14 审查 M2：a/b 曾直接拼进文件名）
    monkeypatch.chdir(tmp_path)
    code, payload = _run(["render", "a/b", "--corpus", str(slash), "--out", "png"])
    assert code == 0 and payload["status"] == "ok"
    assert payload["data"]["path"] == "a_b.png"
    assert (tmp_path / "a_b.png").exists()


def test_render_write_failure_exit2_json_not_traceback(mini, tmp_path, monkeypatch):
    # 写盘失败 → exit 2 + JSON 错误（此前 raw traceback + exit 1 + stdout 无 JSON）
    monkeypatch.chdir(tmp_path)
    (tmp_path / "g.png").mkdir()          # 目标名被目录占用 → IsADirectoryError(OSError)
    (tmp_path / "g.outline.json").mkdir()
    for out in ("png", "outline.json"):
        code, payload = _run(["render", "g", "--corpus", str(mini), "--out", out])
        assert code == 2 and payload["status"] == "error"
        assert "g" in payload["data"]["error"]


def test_sample_negative_n_exit2(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    code, payload = _run(["sample", "--corpus", str(p), "--n", "-1"])
    assert code == 2 and payload["status"] == "error"


def test_compare_stroke_count_mismatch_warns(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text(
        "gsf/1\nglyph one\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        "glyph two\nstroke line head flat tail flat (10,10)->(100,60)\n"
        "stroke line head flat tail flat (20,20)->(80,80)\n", encoding="utf-8")
    code, payload = _run(["compare", "one", "two", "--corpus", str(p)])
    assert code == 0
    assert payload["data"]["per_stroke"] == []      # 笔数不等 → 逐笔 diff 跳过
    assert "stroke count mismatch: 1 vs 2; per_stroke skipped" in payload["warnings"]
