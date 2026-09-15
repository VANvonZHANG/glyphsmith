# tests/test_batch.py
"""T16：multiprocessing 批量渲染。冒烟口径：单字形任何异常记录不中断。"""
import pytest

from gsrender.batch import batch_render


@pytest.fixture
def eight(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(8)), encoding="utf-8")
    return p


def test_batch_renders_each(tmp_path, eight):
    # 简报 Step 1 原测试：8 字形 → 8 SVG + stats
    outdir = tmp_path / "out"
    stats = batch_render(eight, outdir, workers=2)
    assert stats["rendered"] == 8 and stats["errors"] == 0
    assert len(list(outdir.glob("*.svg"))) == 8


def test_batch_svg_content(tmp_path, eight):
    outdir = tmp_path / "out"
    batch_render(eight, outdir, workers=2)
    svg = (outdir / "g0.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg") and "<path" in svg


def test_batch_serial_matches_parallel(tmp_path, eight):
    # 冒烟交叉判据的缩微版：workers=1 与 workers=3 计数一致（渲染是纯函数）
    s1 = batch_render(eight, tmp_path / "w1", workers=1)
    s3 = batch_render(eight, tmp_path / "w3", workers=3)
    assert s1 == s3 == {"rendered": 8, "errors": 0, "empty": 0}


def test_batch_slash_name_sanitized(tmp_path):
    # 文件名清洗与 cli._safe_filename（T14 审查 M2）同一助手
    from gsrender.cli import _safe_filename
    assert _safe_filename("a/b") == "a_b"
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph a/b\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    outdir = tmp_path / "out"
    stats = batch_render(p, outdir, workers=2)
    assert stats["rendered"] == 1
    assert (outdir / "a_b.svg").exists()
    assert not (outdir / "a").exists()      # 未清洗时会生成子目录而非文件


def test_batch_ref_only_glyph_counts_empty(tmp_path):
    # 纯 ref 字形（冒烟口径 parts 只有自身 → missing part 警告 + 空轮廓）：
    # rendered 计入、empty 计入、文件仍写出（空 path 的合法 SVG）
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph r\nref ghost box(0,0,100,100)\n", encoding="utf-8")
    stats = batch_render(p, tmp_path / "out", workers=1)
    assert stats == {"rendered": 1, "errors": 0, "empty": 1}
    assert (tmp_path / "out" / "r.svg").read_text(encoding="utf-8").startswith("<svg")


def test_batch_unknown_backend_errors_not_crash(tmp_path, eight):
    # 冒烟口径：未知后端名逐字形成 err，批次正常返回不中断
    stats = batch_render(eight, tmp_path / "out", backend="no-such-backend", workers=2)
    assert stats == {"rendered": 0, "errors": 8, "empty": 0}
    assert not list((tmp_path / "out").glob("*.svg"))


def test_batch_write_failure_counts_error(tmp_path, monkeypatch):
    # 单文件写盘 OSError → errors 计数不中断（区别于单字形命令的 exit 2：
    # batch 是批量口径；mkdir 失败仍抛 OSError 交 CLI 层转 exit 2）
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir()
    (outdir / "g.svg").mkdir()             # 目标名被目录占用 → IsADirectoryError
    stats = batch_render(p, outdir, workers=1)
    assert stats == {"rendered": 0, "errors": 1, "empty": 0}


def test_batch_dump_mode_and_pen_minimal(tmp_path):
    # dump 装载 + 双后端通用（协议注册表口径：pen-minimal 同一 render 接口）
    p = tmp_path / "d.txt"
    p.write_text(" name | related | data \n" + "-------------------------------\n"
                 " g1  | u3013   | 1:0:0:10:10:100:60:2:2 \n", encoding="utf-8")
    stats = batch_render(p, tmp_path / "out", backend="pen-minimal", workers=2, dump=True)
    assert stats == {"rendered": 1, "errors": 0, "empty": 0}
    assert "<path" in (tmp_path / "out" / "g1.svg").read_text(encoding="utf-8")


def test_batch_mkdir_failure_raises_oserror(tmp_path, eight):
    # outdir 路径被文件占用 → mkdir OSError 冒泡（CLI 层转 exit 2 + JSON）
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied", encoding="utf-8")
    with pytest.raises(OSError):
        batch_render(eight, blocker / "sub", workers=1)
