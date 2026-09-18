import contextlib
import io
import json
from pathlib import Path

import pytest

from glyphsmith.cli import main


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


# ── T16：glyphsmith batch（批量渲染子命令）──

def test_batch_writes_svds(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(5)), encoding="utf-8")
    out = tmp_path / "batch-out"
    code, payload = _run(["batch", "--corpus", str(p), "--out", str(out),
                          "--workers", "2"])
    assert code == 0 and payload["status"] == "ok"
    assert payload["data"]["rendered"] == 5 and payload["data"]["errors"] == 0
    assert payload["data"]["outdir"] == str(out)
    assert len(list(out.glob("*.svg"))) == 5


def test_batch_dump_autodetected(tmp_path):
    # dump_newest_only 格式自动识别（首行含 '|' 且非 gsf/ 头），无需 --dump
    p = tmp_path / "d.txt"
    p.write_text(" name | related | data \n"
                 " g    | u3013   | 1:0:0:10:10:100:60:2:2 \n", encoding="utf-8")
    out = tmp_path / "o"
    code, payload = _run(["batch", "--corpus", str(p), "--out", str(out),
                          "--workers", "1"])
    assert code == 0 and payload["data"]["rendered"] == 1
    assert (out / "g.svg").exists()


def test_batch_dump_flag_forces_dump_mode(tmp_path):
    # 首行为空行的 dump（自动识别只看首行 → 误判 GSF → from_gsf 静默空库）；
    # --dump 显式强制 from_dump。数据行本身必须含 '|'（三列格式）。
    body = " name | related | data \n g | u3013 | 1:0:0:10:10:100:60:2:2 \n"
    p = tmp_path / "d.txt"
    p.write_text("\n" + body, encoding="utf-8")
    out = tmp_path / "o"
    code, payload = _run(["batch", "--corpus", str(p), "--out", str(out),
                          "--workers", "1"])          # 无 --dump：误判 → 空库
    assert code == 0 and payload["data"]["rendered"] == 0
    out2 = tmp_path / "o2"
    code, payload = _run(["batch", "--corpus", str(p), "--out", str(out2),
                          "--workers", "1", "--dump"])
    assert code == 0 and payload["data"]["rendered"] == 1


def test_batch_negative_workers_exit2(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    code, payload = _run(["batch", "--corpus", str(p), "--out",
                          str(tmp_path / "o"), "--workers", "0"])
    assert code == 2 and payload["status"] == "error"


def test_batch_unknown_backend_exit2(tmp_path):
    # 模块头契约：未知 backend → exit 2（而非逐字形 errors=N 跑完）
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    code, payload = _run(["batch", "--corpus", str(p), "--out",
                          str(tmp_path / "o"), "--backend", "no-such-backend"])
    assert code == 2 and payload["status"] == "error"
    assert "backend" in payload["data"]["error"]


def test_batch_outdir_unwritable_exit2_json(tmp_path):
    # M2 写盘契约：outdir 路径被文件占用 → exit 2 + JSON 错误而非 traceback
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    code, payload = _run(["batch", "--corpus", str(p), "--out",
                          str(blocker / "sub"), "--workers", "1"])
    assert code == 2 and payload["status"] == "error"


# ── 全分支终审修复（C1 dump 自动分流 / I1 both 并渲 / M6 OSError）──

DUMP = Path("/home/zhangfan/Project/20260909_KAGE/data/dump_newest_only.txt")

needs_dump = pytest.mark.skipif(not DUMP.exists(), reason="needs real dump")


def _dump_head(dst, n=60):
    with DUMP.open(encoding="utf-8") as src, open(dst, "w", encoding="utf-8") as out:
        for _ in range(n):
            line = src.readline()
            if not line:
                break
            out.write(line)


def _first_stroke_name(path):
    """头部第一个数据列以 stroke 行（head 1-8）开头的字形名（u4e2d 等
    常用字不在 dump 前 60 行；从头部自取，抗 dump 版本漂移）。"""
    with open(path, encoding="utf-8") as f:
        for line in f:
            cells = line.split("|")
            if len(cells) >= 3:
                name, data = cells[0].strip(), cells[2].strip()
                if name and name != "name" and data[:1] in "12345678":
                    return name
    raise AssertionError("dump 头部无 stroke 字形（版本漂移？）")


@needs_dump
def test_render_auto_detects_dump_corpus(tmp_path):
    # C1：非 batch 命令直接吃 dump 语料（README 首例形态）。此前一律
    # from_gsf，dump 静默装出空库 → unknown glyph exit 3 误导。
    d = tmp_path / "dump.txt"
    _dump_head(d)
    code, payload = _run(["render", _first_stroke_name(d), "--corpus", str(d)])
    assert code == 0 and payload["status"] == "ok"
    assert payload["data"]["svg"].startswith("<svg")


@needs_dump
def test_list_auto_detects_dump_corpus(tmp_path):
    # C1 同款分流对 list（检索类命令同样受益）
    d = tmp_path / "dump.txt"
    _dump_head(d)
    code, payload = _run(["list", "--corpus", str(d), "--like", "a*"])
    assert code == 0 and payload["data"]["count"] > 0


def test_render_both_backends_svg(mini):
    # I1：--backend both 双后端各渲一次，svg 双键 + backends 列表
    code, payload = _run(["render", "g", "--corpus", str(mini), "--backend", "both"])
    assert code == 0 and payload["status"] == "ok"
    assert payload["data"]["svg_legacy"].startswith("<svg")
    assert payload["data"]["svg_pen"].startswith("<svg")
    assert payload["data"]["backends"] == ["legacy-kurgm", "pen-minimal"]


def test_render_both_backends_png_two_files(mini, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, payload = _run(["render", "g", "--corpus", str(mini),
                          "--backend", "both", "--out", "png"])
    assert code == 0 and payload["status"] == "ok"
    assert (tmp_path / "g.legacy.png").exists()
    assert (tmp_path / "g.pen.png").exists()


def test_render_both_backends_outline_json_two_files(mini, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, payload = _run(["render", "g", "--corpus", str(mini),
                          "--backend", "both", "--out", "outline.json"])
    assert code == 0
    assert (tmp_path / "g.legacy.outline.json").exists()
    assert (tmp_path / "g.pen.outline.json").exists()


def test_corpus_path_is_directory_exit2_json(tmp_path):
    # M6：语料是目录 → IsADirectoryError（OSError 子类、非 FileNotFoundError）
    # 也走 exit 2 + JSON 契约，而非 raw traceback
    code, payload = _run(["render", "g", "--corpus", str(tmp_path)])
    assert code == 2 and payload["status"] == "error"
