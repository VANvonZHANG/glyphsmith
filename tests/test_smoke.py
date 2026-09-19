# tests/test_smoke.py
"""The smoke/audit counters (spec §6 layer 3) on a fixed small sample.

The full-corpus numbers themselves are acceptance evidence, not a unit test;
what a test can pin down is the counting logic and its attribution contract:
degeneracy comes from `nib.should_degrade`, per-reason totals aggregate by the
stable message prefix, and a data-quality notice (`unmapped ending code 8 at
tail`, `missing part: x`) is never counted as a degeneracy — `if plan.warnings`
would report ~12% of real strokes as degenerate instead of well under 1%.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Four glyphs, one per counting case: a plain stroke, a zero-length stroke (the
# one real degeneracy), an ending code the name table cannot name (a notice),
# and a pure ref (0 strokes in stroke-only scope, one stroke under --closure).
SAMPLE = """\
                                  name                                  | related | data
------------------------------------------------------------------------+---------+----
 a                                                                      | -       | 1:0:0:20:50:180:50
 zero                                                                   | -       | 1:0:0:5:5:5:5
 code8                                                                  | -       | 1:0:8:20:50:180:50
 ref                                                                    | -       | 99:0:0:0:0:200:200:a:0:0:0
"""


def test_import():
    import glyphsmith, gsf.model
    assert glyphsmith.__version__ == "0.1.0"
    assert hasattr(gsf, "model")


def _run(script, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        capture_output=True, text=True, cwd=ROOT)


def _field(out, key):
    m = re.search(rf"\b{re.escape(key)}=(\d+)", out)
    assert m, f"{key}= is not in the output:\n{out}"
    return int(m.group(1))


def _dump(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def test_pen_audit_attributes_degeneracy_per_reason_on_a_limited_sample(tmp_path):
    r = _run("pen_audit.py", "--corpus", str(_dump(tmp_path)),
             "--style", "serif-song", "--limit", "4")
    assert r.returncode == 0, r.stderr
    assert _field(r.stdout, "glyphs") == 4
    assert _field(r.stdout, "strokes") == 3          # the pure ref contributes none
    assert _field(r.stdout, "degenerate") == 1       # only `zero`
    assert _field(r.stdout, "err") == 0
    assert "zero-length centerline=1" in r.stdout
    # Both of these live in plan.warnings and are NOT degeneracy.
    assert "unmapped ending code=1" in r.stdout
    assert "missing part=1" in r.stdout
    # ...so the warnings-based count the audit must not use is the larger one.
    assert _field(r.stdout, "warning_strokes") == 2 > _field(r.stdout, "degenerate")


def test_pen_audit_reason_counts_add_up_to_the_degenerate_count(tmp_path):
    """Attribution, not a bare total: every degenerate stroke is one reason."""
    r = _run("pen_audit.py", "--corpus", str(_dump(tmp_path)),
             "--style", "sans-hei", "--limit", "4")
    assert r.returncode == 0, r.stderr
    reasons = re.search(r"degeneracy reasons[^:]*:(.*)", r.stdout)
    assert reasons, r.stdout
    per_reason = sum(int(n) for n in re.findall(r"=(\d+)", reasons.group(1)))
    assert per_reason == _field(r.stdout, "degenerate") == 1


def test_pen_audit_workers_agree_with_the_serial_count(tmp_path):
    args = ("--corpus", str(_dump(tmp_path)), "--style", "serif-song", "--limit", "4")
    serial = _run("pen_audit.py", *args)
    parallel = _run("pen_audit.py", *args, "--workers", "2")
    assert serial.returncode == 0, serial.stderr
    assert parallel.returncode == 0, parallel.stderr
    for key in ("glyphs", "strokes", "degenerate", "empty", "err"):
        assert _field(serial.stdout, key) == _field(parallel.stdout, key), key
    assert _field(serial.stdout, "strokes") == 3      # `ref` draws nothing on its own


def test_pen_audit_closure_scope_resolves_refs(tmp_path):
    r = _run("pen_audit.py", "--corpus", str(_dump(tmp_path)), "--style", "serif-song",
             "--limit", "4", "--closure")
    assert r.returncode == 0, r.stderr
    assert _field(r.stdout, "strokes") == 4           # resolved `a` is one stroke
    assert _field(r.stdout, "degenerate") == 1
    assert _field(r.stdout, "err") == 0


def test_pen_audit_rejects_an_unknown_style_before_scanning(tmp_path):
    r = _run("pen_audit.py", "--corpus", str(_dump(tmp_path)), "--style", "nope")
    assert r.returncode != 0
    assert "unknown style" in r.stderr
    assert "Traceback" not in r.stderr


def test_smoke_full_passes_the_style_through_to_the_pen_backend(tmp_path):
    r = _run("smoke_full.py", "--corpus", str(_dump(tmp_path)),
             "--backend", "pen", "--style", "sans-round", "--limit", "4")
    assert r.returncode == 0, r.stderr
    assert "style=sans-round" in r.stdout
    assert _field(r.stdout, "total") == 4
    assert _field(r.stdout, "err") == 0


def test_smoke_full_rejects_an_unknown_style_before_rendering(tmp_path):
    r = _run("smoke_full.py", "--corpus", str(_dump(tmp_path)),
             "--backend", "pen", "--style", "nope", "--limit", "4")
    assert r.returncode != 0
    assert "unknown style" in r.stderr
    assert "Traceback" not in r.stderr
