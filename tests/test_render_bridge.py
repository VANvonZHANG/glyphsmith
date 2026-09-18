# tests/test_render_bridge.py
"""The downgrade contract of scripts/render_bridge.mjs (left over from the
rename task: previously only verified by hand).

The bridge resolves the engine location in order (KAGE_ENGINE →
<repo>/node_modules/..., the same rule as gsftool scripts/render_check.mjs).
When neither exists it must: write a JSON error to stderr, exit with code 2,
and keep stdout clean (the TSV contract must not be polluted) — the
cross-engine differential callers (tests/test_cross_engine.py) rely on this
exit-code semantics to tell "engine missing" from "rendering difference".

This test only needs the node executable, not kage-engine: the script is copied
into tmp, so the node_modules candidate resolves to tmp/node_modules (which does
not exist), and KAGE_ENGINE is pointed at a non-existent path to block the other
candidate too. test_cross_engine.py's module-level skipif requires the engine to
be present and cannot cover this branch, hence a separate file (following
gsftool tests/test_render_golden.py::test_missing_engine_reports_error_and_exits_2).
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node executable not available")


@needs_node
def test_missing_engine_reports_json_error_and_exits_2(tmp_path):
    # guaranteed by skipif; narrows the type so subprocess.run gets list[str]
    assert NODE is not None
    script = tmp_path / "render_bridge.mjs"
    shutil.copy(REPO / "scripts" / "render_bridge.mjs", script)
    env = {**os.environ, "KAGE_ENGINE": str(tmp_path / "no-such-engine.js")}
    r = subprocess.run([NODE, str(script)], input='{"name":"g","data":"1:0:0:10:10:100:60"}\n',
                       capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 2, r.stderr
    payload = json.loads(r.stderr)          # stderr must be parseable JSON (not a traceback)
    assert payload["error"] == "kage-engine not found"
    assert str(tmp_path / "no-such-engine.js") in payload["tried"]
    assert "KAGE_ENGINE" in payload["hint"]
    assert r.stdout == ""                   # the TSV contract stays clean: no half line


@needs_node
def test_engine_candidate_order_prefers_kage_engine_env(tmp_path):
    # Resolution-order contract: KAGE_ENGINE outranks the node_modules candidate —
    # a fake engine exporting only empty objects proves that "the one the env
    # points at is the one imported" (missing it is the exit 2 branch above).
    assert NODE is not None
    script = tmp_path / "render_bridge.mjs"
    shutil.copy(REPO / "scripts" / "render_bridge.mjs", script)
    fake = tmp_path / "fake-engine.mjs"
    fake.write_text("export const Kage = class {};\nexport const Polygons = class {};\n"
                    "export const KShotai = { kMincho: 0, kGothic: 1 };\n", encoding="utf-8")
    env = {**os.environ, "KAGE_ENGINE": str(fake)}
    r = subprocess.run([NODE, str(script)], input="", capture_output=True,
                       text=True, timeout=60, env=env)
    # the fake engine imports fine (not the exit 2 "not found"), and empty input
    # ends cleanly
    assert r.returncode == 0, r.stderr
    assert "kage-engine not found" not in r.stderr
