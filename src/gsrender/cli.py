# src/gsrender/cli.py
"""gsr —— agent 友好 CLI。统一契约：{"status","data","warnings","hints"}。

stdout 恒单行 JSON；退出码 0 ok / 2 usage（argparse 自带 + 未知 font/backend
+ 语料文件缺失）/ 3 unknown glyph（hints 附 `gsr list --like ...` 补救动作）/
4 cycle（data.error 携带环路径）。
"""
from __future__ import annotations

import argparse
import json
import random
import sys

import gsrender.legacy_kurgm  # noqa: F401  注册 legacy-kurgm 后端（不 import 则 get_backend 抛 ValueError，T8 审查发现）

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
    """字形名 → 安全文件名：路径分隔符（/、\\ 及 os 层 sep/altsep）换 `_`。

    T14 审查 M2：GlyphWiki 名含 `/` 时曾直接拼进写盘路径（render --out png
    raw traceback）。gsr batch（T16）与本处共用同一助手。
    """
    import os
    for sep in {"/", "\\", os.sep, os.altsep}:
        if sep:
            name = name.replace(sep, "_")
    return name


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gsr", description="GSF 字形渲染器：stdout 单行 JSON 契约，agent 原生")
    p.add_argument("--corpus", default="glyphwiki-newest.gsf",
                   help="语料：GSF 文本文件或 GlyphWiki dump_newest_only.txt")
    sub = p.add_subparsers(dest="cmd", required=True)

    def sp(name, help):
        s = sub.add_parser(name, help=help)
        # 子命令位也收 --corpus（简报 hints/测试均 `gsr <cmd> --corpus ...` 形态）；
        # SUPPRESS：子位缺省时不覆写主位已设值，两个位置都可用。
        s.add_argument("--corpus", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
        return s

    r = sp("render", "渲染单个字形（--out svg|png|outline.json）")
    r.add_argument("name")
    r.add_argument("--backend", default="legacy-kurgm")
    r.add_argument("--font", default="mincho",
                   help="serif|mincho / sans|gothic（FONT_ALIAS 换算）")
    r.add_argument("--out", default="svg", choices=["svg", "png", "outline.json"])
    rs = sp("resolve", "ref 依赖闭包：closure / dangling / depth")
    rs.add_argument("name")
    ins = sp("inspect", "字形解剖：ops 计数 + 名字 meta")
    ins.add_argument("name")
    ls = sp("list", "语料检索（--src/--char/--like 前缀）")
    ls.add_argument("--src"); ls.add_argument("--char"); ls.add_argument("--like")
    smp = sp("sample", "可复现随机抽样（--seed 定 rng）")
    smp.add_argument("--n", type=int, default=10); smp.add_argument("--seed", type=int, default=1)
    cmp_ = sp("compare", "两字形 IoU + 逐笔结构 diff")
    cmp_.add_argument("a"); cmp_.add_argument("b")
    cmp_.add_argument("--backend", default="legacy-kurgm")
    cmp_.add_argument("--font", default="mincho")
    return p


# ── 各命令主体：返回 (data, warnings)，错误经异常冒泡由 main 统一接管 ──
def _make_renderer(args):
    from gsrender import Renderer
    font = FONT_ALIAS.get(args.font)
    if font is None:
        _fail(2, f"unknown font: {args.font!r} (available: {sorted(FONT_ALIAS)})")
    try:
        return Renderer(backend=args.backend, font=font)
    except ValueError as e:           # get_backend：未注册后端名
        _fail(2, str(e))


def _cmd_render(args, corpus):
    from gsrender.compare import rasterize
    r = corpus.resolve(args.name)
    out = _make_renderer(args).render(r)
    if args.out == "svg":             # 内联，不落盘
        data = {"name": args.name, "svg": out.to_svg()}
    elif args.out == "png":
        path = f"{_safe_filename(args.name)}.png"
        try:
            rasterize(out).save(path)
        except OSError as e:           # 写盘契约（T14 审查 M2）：JSON 错误 + exit 2
            _fail(2, f"cannot write {path}: {e}")
        data = {"name": args.name, "path": path}
    else:                             # outline.json：{"contours": [[(x,y,off), ...], ...]}
        path = f"{_safe_filename(args.name)}.outline.json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"contours": out.contours}, f, ensure_ascii=False)
        except OSError as e:
            _fail(2, f"cannot write {path}: {e}")
        data = {"name": args.name, "path": path}
    return data, list(r.warnings)     # render 后端会向 r.warnings 追加展开期警告


def _closure_depth(corpus, name: str) -> int:
    """闭包最深 ref 链层数（节点数计，目标自身 = 1）。DFS + memo。

    与 Corpus._collect 同口径解析引用目标（含 @版本兜底基名）；悬空引用
    （两边都不在语料）不计层。resolve 已证无环，memo 占位仅作保险。
    """
    from gsrender.corpus import UnknownGlyphError
    from gsrender.legacy_kurgm.expansion import ref_names
    memo: dict[str, int] = {}

    def dfs(n: str) -> int:
        if n in memo:
            return memo[n]
        memo[n] = 1
        best = 1
        for ref in ref_names(corpus.glyph_of(n)):
            target = None
            for cand in (ref, ref.partition("@")[0]):
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
    if args.n < 0:                     # T14 审查 M2：负值曾 raw traceback
        _fail(2, f"--n must be a non-negative integer, got {args.n}")
    names = list(corpus.iter_names())
    rng = random.Random(args.seed)     # scripts/sample_dump.py 同款：seed 定 rng
    return {"names": rng.sample(names, min(args.n, len(names))),
            "seed": args.seed}, []


def _cmd_compare(args, corpus):
    from gsrender.compare import compare, compare_separated
    renderer = _make_renderer(args)
    ra, rb = corpus.resolve(args.a), corpus.resolve(args.b)
    result = compare(renderer.render(ra), renderer.render(rb))
    sa = renderer.render_separated(ra)
    sb = renderer.render_separated(rb)
    if len(sa) == len(sb):             # 笔画数不等时逐笔 zip 无意义，留空
        result.per_stroke = compare_separated(sa, sb)
    warns = list(ra.warnings) + [w for w in rb.warnings if w not in ra.warnings]
    if len(sa) != len(sb):             # T14 审查 M1：静默留空改为显式 warning
        warns.append(f"stroke count mismatch: {len(sa)} vs {len(sb)}; "
                     "per_stroke skipped")
    return result.to_dict(), warns


_HANDLERS = {"render": _cmd_render, "resolve": _cmd_resolve,
             "inspect": _cmd_inspect, "list": _cmd_list,
             "sample": _cmd_sample, "compare": _cmd_compare}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    from gsrender.corpus import Corpus, UnknownGlyphError
    from gsrender.legacy_kurgm.expansion import CycleError

    try:
        corpus = Corpus.from_gsf(args.corpus)
    except FileNotFoundError:
        _fail(2, f"corpus file not found: {args.corpus}",
              hints=[{"action": "gsr list --corpus <path.gsf|dump.txt> --like '<prefix>*'",
                      "reason": "用 --corpus 指定语料文件"}])
    try:
        data, warnings = _HANDLERS[args.cmd](args, corpus)
    except UnknownGlyphError as e:
        _fail(3, str(e), hints=[
            {"action": f"gsr list --corpus {args.corpus} --like '{e.name[:4]}*'",
             "reason": "检查拼写或变体"}])
    except CycleError as e:
        _fail(4, "cycle: " + " -> ".join(e.path), hints=[
            {"action": f"gsr resolve --corpus {args.corpus} {e.path[0]}",
             "reason": "环路径见 data.error；语料需修环后重试"}])
    _emit("ok", data, warnings=warnings)
    sys.exit(0)                        # 成功也走 SystemExit（code=0），契约可预测


if __name__ == "__main__":
    main()
