# tests/test_pen_style_diff.py
"""Layer 4 of the acceptance ladder (spec §6): a style parameter moves the
render, in the direction the parameter implies.

Direction, not magnitude. "Thicker verticals cover more ink" is a claim about
the code; "verticals at 20 land within 5% of legacy" would be a calibration
whose answer belongs to the style file's author, and gating on it would push
the pen style toward fitting legacy rather than toward being a typeface — so
every assertion here is a sign (ink rises, IoU < 1, "the ink that goes away is
exactly the wedges"), never a tuned number. The one magnitude worth knowing,
pen vs legacy, is *recorded* by `scripts/pen_style_diff.py`, not gated here.

Every perturbation is written to a temp file and read back with `Style.load`
before it is rendered. A perturbation that does not parse, or that silently
fails to apply, has to fail the test: a copy that still carries the original
parameters renders the original style, and the differential then reads as "the
parameter does nothing" — the note-17 failure mode, where a dropped datum is
indistinguishable from "nothing wrong".
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

from gsf.kage2 import parse_kage2

from glyphsmith.compare import compare, rasterize
from glyphsmith.corpus import ResolveResult
from glyphsmith.outline import Outline
from glyphsmith.pen import nib
from glyphsmith.pen.backend import expand_to_graph
from glyphsmith.pen.style import Style
from glyphsmith.protocol import RenderOptions, get_backend

ROOT = Path(__file__).resolve().parent.parent

# Three glyphs, one per behaviour the differential has to see: 十 puts a wedge
# on a horizontal tail that *crosses* a vertical (the wedge stays), 寸 carries a
# hook and a tail code the name table cannot name (`unmapped ending code 8`),
# and the square is where the shipped rule fires — both horizontals' tails land
# on a vertical, so their wedges are suppressed.
SAMPLE = [
    "1:0:0:14:92:186:92$1:0:0:100:17:100:185",
    "1:0:0:22:67:180:67$1:0:4:134:17:134:181$2:7:8:53:88:77:105:84:129",
    "1:0:0:40:40:160:40$1:0:0:160:40:160:160$1:0:0:40:160:160:160$1:0:0:40:40:40:160",
]

WEDGE_RULE = "no-wedge-where-tail-meets-vertical"
VERTICAL_PROFILE = "vertical:      [[0.0, 12.0], [1.0, 11.0]]"


def _resolve(rows, name="t"):
    """Stroke-only scope: the glyph alone, no ref closure (the smoke's default)."""
    glyph = parse_kage2(rows, name)
    return ResolveResult(name, glyph, {name: glyph}, [])


def render(rows, style):
    """The pen backend's render, with `style` a builtin name or a YAML path."""
    opts = RenderOptions(backend="pen", style=str(style))
    return get_backend("pen").render(_resolve(rows), opts)


def plans(rows, style):
    """The per-stroke plans a style produces — the renderer's own input."""
    return expand_to_graph(_resolve(rows), str(style))[1]


def mask(outline, size=512):
    return np.asarray(rasterize(outline, size), dtype=bool)


def ink(outline, size=512):
    """Ink area: the filled pixels of the rasterised outline."""
    return int(mask(outline, size).sum())


def _serif_song() -> str:
    return (Style.builtin_dir() / "serif-song.yaml").read_text(encoding="utf-8")


def _copy(tmp_path, filename, old, new):
    """`serif-song.yaml` with one literal edit, as a file next to it.

    `old` must be in the file: a needle that no longer matches means the shipped
    value changed and the test's premise is gone, which is a failure to report
    (and re-derive the direction from), not a perturbation to skip.
    """
    src = _serif_song()
    assert old in src, f"serif-song.yaml no longer contains {old!r}"
    path = tmp_path / filename
    path.write_text(src.replace(old, new, 1), encoding="utf-8")
    return path


def _without_rules(tmp_path):
    """`serif-song.yaml` with its whole top-level `rules:` block replaced by `[]`.

    The brief's one-line `src.replace("rules:\\n", ...)` leaves the block's
    items behind the new value and produces a file that does not parse (checked:
    "expected <block end>, but found '<block sequence start>'"), so the block is
    cut by its line structure instead — and the caller loads the result back, so
    a cut that goes wrong fails loudly instead of rendering the original style.
    """
    lines = _serif_song().splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("rules:")), None)
    assert start is not None, "serif-song.yaml has no top-level rules: key"
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end][:1].isspace()):
        end += 1                          # the whole block: blank, comment, indented
    path = tmp_path / "serif-song-norules.yaml"
    path.write_text("\n".join(lines[:start] + ["rules: []"] + lines[end:]) + "\n",
                    encoding="utf-8")
    return path


def _wedges_only(plan_map):
    """An outline of one plan set's wedge decorations, and nothing else.

    `nib.stroke` stacks body + decorations, so isolating the wedges means
    handing `decoration_contours` a plan whose other ornaments are dropped.
    """
    out = Outline()
    for plan in plan_map.values():
        wedges = replace(plan, warnings=[],
                         decorations=[d for d in plan.decorations if d.kind == "wedge"])
        for contour in nib.decoration_contours(wedges):
            out.contours.append([(x, y, 0) for x, y in contour])
    return out


def test_widening_the_verticals_raises_the_ink_area(tmp_path):
    """Vertical width 12 -> 20 covers more of the same glyph, and the two
    renders are visibly different (not a re-render of one style)."""
    wide = _copy(tmp_path, "wide-vertical.yaml", VERTICAL_PROFILE,
                 "vertical:      [[0.0, 20.0], [1.0, 20.0]]")
    # the perturbation applied: a copy that did not would compare equal here
    assert Style.load(wide).width_profile["vertical"] != \
        Style.load("serif-song").width_profile["vertical"]
    for rows in SAMPLE:
        base, wider = render(rows, "serif-song"), render(rows, wide)
        assert ink(wider) > ink(base), "thicker verticals must cover more pixels"
        assert compare(base, wider).iou < 0.95


def test_round_caps_add_ink_while_the_iou_stays_high():
    """sans-hei -> sans-round changes caps (butt -> round) and joins (miter ->
    round) only: round caps add a half-disc at every stroke end, round joins cut
    the miter corners. The skeletons are the same, so the IoU must stay high —
    and below 1, because the two styles must not be the same render twice."""
    total_hei = total_round = 0
    for rows in SAMPLE:
        hei, rnd = render(rows, "sans-hei"), render(rows, "sans-round")
        total_hei += ink(hei)
        total_round += ink(rnd)
        assert 0.5 < compare(hei, rnd).iou < 1.0, "only the ends may differ"
    assert total_round > total_hei, "round caps add area at every end"


def test_suppressing_the_wedge_rule_removes_exactly_the_wedges(tmp_path):
    """The shipped rule may only take wedges away: the plans lose wedge
    decorations and gain nothing else, no ink that was there is lost, and every
    pixel that appears is one of the suppressed wedges' own pixels — so the ink
    falls by exactly the wedges."""
    assert WEDGE_RULE in {r["id"] for r in Style.load("serif-song").rules}
    norules = _without_rules(tmp_path)
    assert Style.load(norules).rules == []          # the perturbation is real

    suppressed = 0
    for rows in SAMPLE:
        ruled_plans, unr_plans = plans(rows, "serif-song"), plans(rows, norules)
        for i, plan in unr_plans.items():
            before = Counter((d.kind, d.at) for d in ruled_plans[i].decorations)
            after = Counter((d.kind, d.at) for d in plan.decorations)
            gone, gained = before - after, after - before
            assert not gone, f"stroke {i}: the rule removed {dict(gone)}"
            assert all(kind == "wedge" for kind, _at in gained), \
                f"stroke {i}: the rule added {dict(gained)}"
            suppressed += sum(gained.values())

        ruled, unr = render(rows, "serif-song"), render(rows, norules)
        mr, mu = mask(ruled), mask(unr)
        wedges = mask(_wedges_only(unr_plans))
        assert not (mr & ~mu).any(), "suppressing a wedge must not lose other ink"
        unexplained = (mu & ~mr) & ~wedges       # added pixels that are no wedge
        assert not unexplained.any(), \
            f"{int(unexplained.sum())} pixels appear that are not the suppressed wedges"
        assert int((mu & ~mr).sum()) == int((wedges & ~mr).sum()), \
            "ink falls by exactly the wedges the rule suppressed"
    assert suppressed, "no stroke in SAMPLE loses a wedge: the test is vacuous"


# ── the report script (the recorded, ungated pen-vs-legacy number) ──────────

DUMP_SAMPLE = """\
                                  name                                  | related | data
------------------------------------------------------------------------+---------+----
 t0                                                                     | -       | {t0}
 t1                                                                     | -       | {t1}
 t2                                                                     | -       | {t2}
"""


def _run(script, *args):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), *args],
        capture_output=True, text=True, cwd=ROOT)


def _number(out, key):
    m = re.search(rf"\b{re.escape(key)}=([0-9.]+)", out)
    assert m, f"{key}= is not in the output:\n{out}"
    return float(m.group(1))


def _dump(tmp_path):
    path = tmp_path / "sample.txt"
    path.write_text(DUMP_SAMPLE.format(t0=SAMPLE[0], t1=SAMPLE[1], t2=SAMPLE[2]),
                    encoding="utf-8")
    return path


def test_the_report_script_measures_a_pair_of_styles(tmp_path):
    r = _run("pen_style_diff.py", "--corpus", str(_dump(tmp_path)),
             "--a", "serif-song", "--b", "sans-hei", "--n", "3")
    assert r.returncode == 0, r.stderr
    assert _number(r.stdout, "err") == 0
    assert _number(r.stdout, "n") == 3
    assert _number(r.stdout, "mean_iou") < 1.0, r.stdout
    assert _number(r.stdout, "ink_a") != _number(r.stdout, "ink_b"), r.stdout


def test_the_report_script_takes_the_peer_engine_as_a_backend(tmp_path):
    """`--b legacy-kurgm` is a backend, not a style file. The number is
    recorded, never gated: the two engines are supposed to differ (spec §6)."""
    r = _run("pen_style_diff.py", "--corpus", str(_dump(tmp_path)),
             "--a", "serif-song", "--b", "legacy-kurgm", "--n", "3", "--closure")
    assert r.returncode == 0, r.stderr
    assert _number(r.stdout, "err") == 0
    assert 0.0 <= _number(r.stdout, "mean_iou") <= 1.0, r.stdout
