# tests/test_batch.py
"""T16: multiprocessing batch rendering.

Smoke convention: any per-glyph exception is recorded without aborting.
"""
import pytest

from glyphsmith.batch import batch_render


@pytest.fixture
def eight(tmp_path):
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\n" + "".join(
        f"glyph g{i}\nstroke line head flat tail flat (10,10)->(100,60)\n\n"
        for i in range(8)), encoding="utf-8")
    return p


def test_batch_renders_each(tmp_path, eight):
    # the brief's original Step 1 test: 8 glyphs → 8 SVGs + stats
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
    # the miniature of the smoke cross-check: workers=1 and workers=3 give the
    # same counts (rendering is a pure function)
    s1 = batch_render(eight, tmp_path / "w1", workers=1)
    s3 = batch_render(eight, tmp_path / "w3", workers=3)
    assert s1 == s3 == {"rendered": 8, "errors": 0, "empty": 0}


def test_batch_slash_name_sanitized(tmp_path):
    # filename sanitising shares the same helper as cli._safe_filename (T14 review M2)
    from glyphsmith.cli import _safe_filename
    assert _safe_filename("a/b") == "a_b"
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph a/b\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    outdir = tmp_path / "out"
    stats = batch_render(p, outdir, workers=2)
    assert stats["rendered"] == 1
    assert (outdir / "a_b.svg").exists()
    assert not (outdir / "a").exists()      # unsanitised it would create a subdirectory, not a file


def test_batch_ref_only_glyph_counts_empty(tmp_path):
    # a pure-ref glyph (smoke scope: parts are only itself → missing part warning
    # + empty contour): counted in rendered, counted in empty, file still written
    # (a valid SVG with an empty path)
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph r\nref ghost box(0,0,100,100)\n", encoding="utf-8")
    stats = batch_render(p, tmp_path / "out", workers=1)
    assert stats == {"rendered": 1, "errors": 0, "empty": 1}
    assert (tmp_path / "out" / "r.svg").read_text(encoding="utf-8").startswith("<svg")


def test_batch_unknown_backend_errors_not_crash(tmp_path, eight):
    # smoke convention: an unknown backend name makes each glyph err, and the
    # batch returns normally without aborting
    stats = batch_render(eight, tmp_path / "out", backend="no-such-backend", workers=2)
    assert stats == {"rendered": 0, "errors": 8, "empty": 0}
    assert not list((tmp_path / "out").glob("*.svg"))


def test_batch_write_failure_counts_error(tmp_path, monkeypatch):
    # a single-file write OSError → counted in errors without aborting (unlike
    # the per-glyph command's exit 2: batch follows the batch convention; a failed
    # mkdir still raises OSError, which the CLI layer turns into exit 2)
    p = tmp_path / "c.gsf"
    p.write_text("gsf/1\nglyph g\nstroke line head flat tail flat (10,10)->(100,60)\n",
                 encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir()
    (outdir / "g.svg").mkdir()             # target name taken by a directory → IsADirectoryError
    stats = batch_render(p, outdir, workers=1)
    assert stats == {"rendered": 0, "errors": 1, "empty": 0}


def test_batch_dump_mode_and_pen_minimal(tmp_path):
    # dump loading + both backends work (the protocol registry's rule:
    # pen-minimal exposes the same render interface)
    p = tmp_path / "d.txt"
    p.write_text(" name | related | data \n" + "-------------------------------\n"
                 " g1  | u3013   | 1:0:0:10:10:100:60:2:2 \n", encoding="utf-8")
    stats = batch_render(p, tmp_path / "out", backend="pen-minimal", workers=2, dump=True)
    assert stats == {"rendered": 1, "errors": 0, "empty": 0}
    assert "<path" in (tmp_path / "out" / "g1.svg").read_text(encoding="utf-8")


def test_batch_mkdir_failure_raises_oserror(tmp_path, eight):
    # outdir path taken by a file → the mkdir OSError bubbles up (the CLI layer
    # turns it into exit 2 + JSON)
    blocker = tmp_path / "blocker"
    blocker.write_text("occupied", encoding="utf-8")
    with pytest.raises(OSError):
        batch_render(eight, blocker / "sub", workers=1)
