#!/usr/bin/env python3
"""Regenerate tests/fixtures/pen-golden.tsv — spec §6 layer 5, the self-golden.

⚠ These values come from glyphsmith's own pen backend. The fixture is a **drift
guard**: it can tell you the output changed, never that it is right. Regenerate
after a *deliberate* output change and review the diff — every changed line is a
change to what users see. Nothing here is external evidence (the internal anchor
is `tests/test_pen_equivalence.py`, against `pen-minimal`).

Deterministic by construction (no timestamps, no host paths in the file), so
re-running on unchanged code reproduces the fixture byte for byte:

    python scripts/pen_golden_regen.py && git diff --stat tests/fixtures/

The sample list below must stay identical to `tests/test_pen_golden.py`; a
desync cannot pass silently, because the test renders *its* list and compares
against what this script wrote.
"""
from __future__ import annotations

from pathlib import Path

from gsf.kage2 import parse_kage2

from glyphsmith.corpus import ResolveResult
from glyphsmith.legacy_kurgm.fingerprint import fingerprint
from glyphsmith.protocol import RenderOptions, get_backend

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "pen-golden.tsv"
STYLES = ["serif-song", "sans-hei", "sans-round"]

# One glyph per behaviour worth pinning, in stroke-only scope (the glyph alone,
# as `smoke_full.py`'s default scope): 十 puts a wedge on a horizontal tail that
# crosses a vertical, 寸 carries a hook tail and an ending code the name table
# cannot name (`unmapped ending code 8`), and the bare bend exercises the
# interior-vertex joins.
SAMPLES = [
    "1:0:0:14:92:186:92$1:0:0:100:17:100:185",
    "1:0:0:22:67:180:67$1:0:4:134:17:134:181$2:7:8:53:88:77:105:84:129",
    "3:0:0:20:20:180:20:100:120",
]

HEADER = [
    "# pen backend self-golden (spec §6 layer 5).",
    "# ⚠ Drift guard only: these values come from glyphsmith's own code, so they",
    "# can show that the output changed, never that it is right.",
    "# Regenerate: python scripts/pen_golden_regen.py",
]


def fingerprint_of(style: str, rows: str) -> str:
    glyph = parse_kage2(rows, f"{style}-golden")
    result = ResolveResult(glyph.name, glyph, {glyph.name: glyph}, [])
    outline = get_backend("pen").render(
        result, RenderOptions(backend="pen", style=style))
    return fingerprint(outline)


def build() -> str:
    lines = list(HEADER)
    for style in STYLES:
        for i, rows in enumerate(SAMPLES):
            lines.append(f"{style}:{i}\t{fingerprint_of(style, rows)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    text = build()
    FIXTURE.write_text(text, encoding="utf-8")
    print(text, end="")
    print(f"# wrote {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
