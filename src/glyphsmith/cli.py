# src/glyphsmith/cli.py
"""glyphsmith — an agent-friendly CLI. Uniform contract:
{"status","data","warnings","hints"}.

stdout is always one line of JSON; exit codes are 0 ok / 2 usage (argparse's
own plus unknown font/backend plus a missing corpus file) / 3 unknown glyph
(hints carry a `glyphsmith list --like ...` remedy) / 4 cycle (data.error
carries the cycle path).
"""
from __future__ import annotations

import argparse
import json
import random
import sys

import glyphsmith.legacy_kurgm  # noqa: F401  register the legacy-kurgm backend
# (T8 review: without this import, get_backend raises ValueError)

FONT_ALIAS = {"serif": "mincho", "sans": "gothic",
              "mincho": "mincho", "gothic": "gothic"}


def _emit(status: str, data: dict, warnings=None, hints=None) -> None:
    json.dump({"status": status, "data": data,
               "warnings": warnings or [], "hints": hints or []},
              sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def _fail(code: int, message: str, hints=None) -> None:
    _emit("error", {"error": message}, hints=hints)
    raise SystemExit(code)


def _safe_filename(name: str) -> str:
    """Glyph name → safe filename: path separators (/ and \\ plus the os-level
    sep/altsep) become `_`.

    T14 review M2: a GlyphWiki name containing `/` used to be concatenated
    straight into the output path (render --out png raw traceback). Both
    glyphsmith batch (T16) and this spot share the same helper.
    """
    import os
    for sep in {"/", "\\", os.sep, os.altsep}:
        if sep:
            name = name.replace(sep, "_")
    return name


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="glyphsmith",
        description="GSF glyph renderer: a one-line JSON contract on stdout, agent-native")
    p.add_argument("--corpus", default="glyphwiki-newest.gsf",
                   help="corpus: a GSF text file or a GlyphWiki dump_newest_only.txt")
    sub = p.add_subparsers(dest="cmd", required=True)

    def sp(name, help):
        s = sub.add_parser(name, help=help)
        # the subcommand position also accepts --corpus (both the brief's hints
        # and the tests use `glyphsmith <cmd> --corpus ...`);
        # SUPPRESS: when absent here it does not overwrite a value already set
        # at the main position, so both positions work.
        s.add_argument("--corpus", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return s

    r = sp("render", "render one glyph (--out svg|png|outline.json)")
    r.add_argument("name")
    r.add_argument("--backend", default="legacy-kurgm",
                   help="legacy-kurgm|pen-minimal|both (both = render with both backends)")
    r.add_argument("--font", default="mincho",
                   help="serif|mincho or sans|gothic (resolved via FONT_ALIAS)")
    r.add_argument("--out", default="svg", choices=["svg", "png", "outline.json"])
    rs = sp("resolve", "ref dependency closure: closure / dangling / depth")
    rs.add_argument("name")
    ins = sp("inspect", "glyph anatomy: op counts + name meta")
    ins.add_argument("name")
    ls = sp("list", "corpus search (--src/--char/--like prefix)")
    ls.add_argument("--src"); ls.add_argument("--char"); ls.add_argument("--like")
    smp = sp("sample", "reproducible random sample (--seed seeds the rng)")
    smp.add_argument("--n", type=int, default=10); smp.add_argument("--seed", type=int, default=1)
    cmp_ = sp("compare", "two glyphs: raster IoU + per-stroke structural diff")
    cmp_.add_argument("a"); cmp_.add_argument("b")
    cmp_.add_argument("--backend", default="legacy-kurgm")
    cmp_.add_argument("--font", default="mincho")
    b = sp("batch", "batch-render a whole corpus -> outdir/<glyph-name>.svg (multiprocessing)")
    b.add_argument("--out", required=True, help="output directory")
    b.add_argument("--backend", default="legacy-kurgm")
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--dump", action="store_true",
                   help="corpus is a GlyphWiki dump_newest_only.txt"
                        " (otherwise auto-detected: first line contains '|' and is not a gsf/ header)")
    sp("styles", "list built-in pen styles (name / genre / path)")
    return p


# ── command bodies: return (data, warnings); errors bubble up and main handles them ──
def _make_renderer(args):
    from glyphsmith import Renderer
    font = FONT_ALIAS.get(args.font)
    if font is None:
        _fail(2, f"unknown font: {args.font!r} (available: {sorted(FONT_ALIAS)})")
    try:
        return Renderer(backend=args.backend, font=font)
    except ValueError as e:           # get_backend: unregistered backend name
        _fail(2, str(e))


# the fixed render order for `--backend both`; svg_legacy/svg_pen keys follow it
BOTH_BACKENDS = ["legacy-kurgm", "pen-minimal"]


def _render_both(args, r):
    """`--backend both` (final review I1): render once per backend and produce a
    comparison — composed at the CLI layer, leaving Renderer/protocol untouched.
    For svg both keys are inlined; png/outline.json write two files,
    {name}.legacy.*/{name}.pen.* (the write contract matches the single-backend
    case: exit 2 + JSON)."""
    from glyphsmith import Renderer
    from glyphsmith.compare import rasterize
    font = FONT_ALIAS.get(args.font)
    if font is None:
        _fail(2, f"unknown font: {args.font!r} (available: {sorted(FONT_ALIAS)})")
    outs = {key: Renderer(backend=b, font=font).render(r)
            for b, key in zip(BOTH_BACKENDS, ("legacy", "pen"))}
    # each backend writes the same expansion warnings back into r.warnings
    # → de-duplicate, preserving order
    seen: set[str] = set()
    warns = [w for w in r.warnings if not (w in seen or seen.add(w))]

    def _write(out, key: str, ext: str) -> str:
        path = f"{_safe_filename(args.name)}.{key}.{ext}"
        try:
            if ext == "png":
                rasterize(out).save(path)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({"contours": out.contours}, f, ensure_ascii=False)
        except OSError as e:       # same write contract (T14 review M2)
            _fail(2, f"cannot write {path}: {e}")
        return path

    data = {"name": args.name, "backends": list(BOTH_BACKENDS)}
    if args.out == "svg":
        data["svg_legacy"] = outs["legacy"].to_svg()
        data["svg_pen"] = outs["pen"].to_svg()
    elif args.out == "png":
        data["paths"] = [_write(outs["legacy"], "legacy", "png"),
                         _write(outs["pen"], "pen", "png")]
    else:
        data["paths"] = [_write(outs["legacy"], "legacy", "outline.json"),
                         _write(outs["pen"], "pen", "outline.json")]
    return data, warns


def _cmd_render(args, corpus):
    from glyphsmith.compare import rasterize
    r = corpus.resolve(args.name)
    if args.backend == "both":         # final review I1: render with both and compare
        return _render_both(args, r)
    out = _make_renderer(args).render(r)
    if args.out == "svg":             # inline, nothing written to disk
        data = {"name": args.name, "svg": out.to_svg()}
    elif args.out == "png":
        path = f"{_safe_filename(args.name)}.png"
        try:
            rasterize(out).save(path)
        except OSError as e:           # write contract (T14 review M2): JSON error + exit 2
            _fail(2, f"cannot write {path}: {e}")
        data = {"name": args.name, "path": path}
    else:                             # outline.json: {"contours": [[(x,y,off), ...], ...]}
        path = f"{_safe_filename(args.name)}.outline.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"contours": out.contours}, f, ensure_ascii=False)
        except OSError as e:
            _fail(2, f"cannot write {path}: {e}")
        data = {"name": args.name, "path": path}
    return data, list(r.warnings)     # the render backend appends expansion warnings here


def _closure_depth(corpus, name: str) -> int:
    """Depth of the deepest ref chain in the closure (counted in nodes; the
    target itself = 1). DFS + memo.

    Resolves reference targets by the same rules as Corpus._collect (including
    the @version fallback to the base name); dangling references (neither side
    in the corpus) do not count towards the depth. resolve has already proved
    there is no cycle, so the memo placeholder is only a safety net.
    """
    from glyphsmith.corpus import UnknownGlyphError
    from glyphsmith.legacy_kurgm.expansion import ref_names
    memo: dict[str, int] = {}

    def dfs(n: str) -> int:
        if n in memo:
            return memo[n]
        memo[n] = 1
        best = 1
        for ref in ref_names(corpus.glyph_of(n)):
            target = None
            for cand in (ref, ref.partition("@")[0]):
                # a self-referential historical snapshot self@N gets no
                # fallback (the same rule as Corpus._collect, otherwise a glyph
                # referencing itself as X@N would have its depth inflated by 1)
                if cand != ref and cand == n:
                    continue
                try:
                    corpus.glyph_of(cand)
                except UnknownGlyphError:
                    continue
                target = cand
                break
            if target is not None:
                best = max(best, 1 + dfs(target))
        memo[n] = best
        return best

    return dfs(name)


def _cmd_resolve(args, corpus):
    r = corpus.resolve(args.name)
    return {"name": args.name,
            "closure": sorted(r.parts),
            "dangling": [w for w in r.warnings if w.startswith("dangling ref:")],
            "depth": _closure_depth(corpus, args.name)}, list(r.warnings)


def _cmd_inspect(args, corpus):
    from gsf.model import RawOp, Ref, Stroke
    from gsf.names import parse_name
    r = corpus.resolve(args.name)
    ops = {"stroke": 0, "ref": 0, "raw": 0}
    for op in r.glyph.ops:
        if isinstance(op, Stroke):
            ops["stroke"] += 1
        elif isinstance(op, Ref):
            ops["ref"] += 1
        elif isinstance(op, RawOp):
            ops["raw"] += 1
    return {"name": args.name, "ops": ops, "meta": parse_name(args.name)}, \
        list(r.warnings)


def _cmd_list(args, corpus):
    names = list(corpus.search(src=args.src, char=args.char, like=args.like))
    return {"names": names, "count": len(names)}, []


def _cmd_sample(args, corpus):
    if args.n < 0:                     # T14 review M2: a negative value used to raw traceback
        _fail(2, f"--n must be a non-negative integer, got {args.n}")
    names = list(corpus.iter_names())
    rng = random.Random(args.seed)     # as in scripts/sample_dump.py: the seed fixes the rng
    return {"names": rng.sample(names, min(args.n, len(names))),
            "seed": args.seed}, []


def _cmd_compare(args, corpus):
    from glyphsmith.compare import compare, compare_separated
    renderer = _make_renderer(args)
    ra, rb = corpus.resolve(args.a), corpus.resolve(args.b)
    result = compare(renderer.render(ra), renderer.render(rb))
    sa = renderer.render_separated(ra)
    sb = renderer.render_separated(rb)
    if len(sa) == len(sb):             # per-stroke zip needs equal counts
        result.per_stroke = compare_separated(sa, sb)
    warns = list(ra.warnings) + [w for w in rb.warnings if w not in ra.warnings]
    if len(sa) != len(sb):             # T14 review M1: silent empty list → explicit warning
        warns.append(f"stroke count mismatch: {len(sa)} vs {len(sb)}; "
                     "per_stroke skipped")
    return result.to_dict(), warns


def _cmd_styles(_args, _corpus=None):
    # unlike the corpus commands this reads only the style files on disk: the
    # three recipes are one pen model, so listing them must work before any
    # corpus exists (hence _NO_CORPUS).
    from glyphsmith.pen.style import Style
    rows = []
    for name in Style.available():
        s = Style.load(name)
        rows.append({"name": s.name, "genre": s.genre, "path": str(s.path),
                     "description": f"{s.genre} style with "
                                    f"{len(s.decorations)} decoration(s) and "
                                    f"{len(s.rules)} rule(s)"})
    return {"styles": rows}, []


_HANDLERS = {"render": _cmd_render, "resolve": _cmd_resolve,
             "inspect": _cmd_inspect, "list": _cmd_list,
             "sample": _cmd_sample, "compare": _cmd_compare,
             "styles": _cmd_styles}


def _looks_like_dump(path: str) -> bool:
    """Auto-detect the dump_newest_only format: the first line contains '|' and
    is not a GSF header (gsf/1).

    The fallback when --dump is absent — if an agent drops a dump path straight
    into --corpus, from_gsf would silently load an empty corpus (no glyph line)
    instead of erroring.
    """
    with open(path, encoding="utf-8") as f:
        first = f.readline()
    return "|" in first and not first.startswith("gsf/")


def _cmd_batch(args, _corpus=None):
    # the corpus is loaded by batch_render itself (dump auto-detection): main's
    # from_gsf preload would both be wasteful for batch (reading the 317MB dump
    # again) and often inapplicable (dump format).
    from glyphsmith.batch import batch_render
    from glyphsmith.protocol import get_backend
    if args.workers < 1:                # as in T14 review M2: argument-level validation
        _fail(2, f"--workers must be >= 1, got {args.workers}")
    try:                                # unknown backend → exit 2 (the module header contract)
        get_backend(args.backend)
    except ValueError as e:
        _fail(2, str(e))
    try:
        stats = batch_render(args.corpus, args.out, backend=args.backend,
                             workers=args.workers,
                             dump=args.dump or _looks_like_dump(args.corpus))
    except FileNotFoundError:          # missing corpus: re-raised to main (hints point at the file)
        raise
    except OSError as e:                # M2 write contract: exit 2 + JSON
        _fail(2, f"cannot write to {args.out}: {e}")
    return {**stats, "outdir": args.out}, []


# registered here, not in the literal above: _cmd_batch is defined below it.
# main() dispatches every _NO_CORPUS command through this table, so batch must
# be in it (it used to be a special case in main).
_HANDLERS["batch"] = _cmd_batch


# Commands that must not have a corpus built before dispatch. batch loads its own
# (dump auto-detection, and reading the 317MB dump twice would be wasteful);
# styles only lists the style files under src/glyphsmith/styles/. The default
# --corpus is glyphwiki-newest.gsf, which need not exist for either.
_NO_CORPUS = {"batch", "styles"}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    from glyphsmith.corpus import Corpus, UnknownGlyphError
    from glyphsmith.legacy_kurgm.expansion import CycleError

    try:
        if args.cmd in _NO_CORPUS:     # these commands do not need a corpus
            data, warnings = _HANDLERS[args.cmd](args)
        else:
            # final review C1: the corpus commands route dump corpora
            # automatically (batch did this in T16; previously a dump path was
            # silently loaded by from_gsf as an empty corpus → a misleading
            # exit 3 on the first glyph)
            corpus = (Corpus.from_dump(args.corpus)
                      if _looks_like_dump(args.corpus)
                      else Corpus.from_gsf(args.corpus))
            data, warnings = _HANDLERS[args.cmd](args, corpus)
    except OSError as e:         # final review M6: the whole OSError family (directory /
                                # permissions; FileNotFoundError is only one) now exits 2
                                # + JSON instead of a raw traceback
        _fail(2, f"cannot open corpus {args.corpus}: {e}",
              hints=[{"action": "glyphsmith list --corpus <path.gsf|dump.txt> --like '<prefix>*'",
                      "reason": "point --corpus at the corpus file"}])
    except UnknownGlyphError as e:
        _fail(3, str(e), hints=[
            {"action": f"glyphsmith list --corpus {args.corpus} --like '{e.name[:4]}*'",
             "reason": "check the spelling or the variant"}])
    except CycleError as e:
        _fail(4, "cycle: " + " -> ".join(e.path), hints=[
            {"action": f"glyphsmith resolve --corpus {args.corpus} {e.path[0]}",
             "reason": "cycle path is in data.error; fix the cycle in the corpus and retry"}])
    _emit("ok", data, warnings=warnings)
    sys.exit(0)                        # success also goes through SystemExit (code=0)


if __name__ == "__main__":
    main()
