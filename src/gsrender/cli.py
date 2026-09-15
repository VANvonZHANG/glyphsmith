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
    r.add_argument("--backend", default="legacy-kurgm",
                   help="legacy-kurgm|pen-minimal|both（both=双后端并渲对比）")
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
    b = sp("batch", "整库批量渲染 → outdir/<字形名>.svg（multiprocessing）")
    b.add_argument("--out", required=True, help="输出目录")
    b.add_argument("--backend", default="legacy-kurgm")
    b.add_argument("--workers", type=int, default=4)
    b.add_argument("--dump", action="store_true",
                   help="语料为 GlyphWiki dump_newest_only.txt"
                        "（缺省自动识别：首行含 '|' 且非 gsf/ 头）")
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


BOTH_BACKENDS = ["legacy-kurgm", "pen-minimal"]   # both 固定渲序，svg_legacy/svg_pen 键序同此


def _render_both(args, r):
    """`--backend both`（终审 I1）：两后端各渲一次并出对比——CLI 层组合，
    Renderer/协议层不动。svg 内联双键；png/outline.json 落
    {name}.legacy.*/{name}.pen.* 两个文件（写盘契约与单后端一致：exit 2 + JSON）。"""
    from gsrender import Renderer
    from gsrender.compare import rasterize
    font = FONT_ALIAS.get(args.font)
    if font is None:
        _fail(2, f"unknown font: {args.font!r} (available: {sorted(FONT_ALIAS)})")
    outs = {key: Renderer(backend=b, font=font).render(r)
            for b, key in zip(BOTH_BACKENDS, ("legacy", "pen"))}
    # 两后端各自向 r.warnings 回写同源展开警告 → 去重保序合并
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
        except OSError as e:       # 写盘契约（T14 审查 M2）同款
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
    from gsrender.compare import rasterize
    r = corpus.resolve(args.name)
    if args.backend == "both":         # 终审 I1：双后端并渲出对比
        return _render_both(args, r)
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
                # self@N 历史快照自引用不兜底（与 Corpus._collect 同规则，
                # 否则自引用 X@N 的字形 depth 虚 +1）
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


def _looks_like_dump(path: str) -> bool:
    """dump_newest_only 格式自动识别：首行含 '|' 且非 GSF 头（gsf/1）。

    无 --dump 时兜底——agent 直接把 dump 路径丢给 --corpus 时，from_gsf
    会静默装出空库（无 glyph 行）而非报错。
    """
    with open(path, encoding="utf-8") as f:
        first = f.readline()
    return "|" in first and not first.startswith("gsf/")


def _cmd_batch(args, _corpus=None):
    # 语料由 batch_render 自装载（dump 自动识别）：main 的 from_gsf 预载对
    # batch 既浪费（317MB dump 再读一遍）又常不适用（dump 格式）。
    from gsrender.batch import batch_render
    from gsrender.protocol import get_backend
    if args.workers < 1:                # T14 审查 M2 同款：参数层校验
        _fail(2, f"--workers must be >= 1, got {args.workers}")
    try:                                # 未知 backend → exit 2（模块头契约）
        get_backend(args.backend)
    except ValueError as e:
        _fail(2, str(e))
    try:
        stats = batch_render(args.corpus, args.out, backend=args.backend,
                             workers=args.workers,
                             dump=args.dump or _looks_like_dump(args.corpus))
    except FileNotFoundError:          # 语料缺失：上抛 main 层（hints 指向语料文件）
        raise
    except OSError as e:                # M2 写盘契约：exit 2 + JSON
        _fail(2, f"cannot write to {args.out}: {e}")
    return {**stats, "outdir": args.out}, []


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    from gsrender.corpus import Corpus, UnknownGlyphError
    from gsrender.legacy_kurgm.expansion import CycleError

    try:
        if args.cmd == "batch":        # batch 自带语料装载（见 _cmd_batch）
            data, warnings = _cmd_batch(args)
        else:
            # 终审 C1：非 batch 命令同样自动分流 dump 语料（batch 侧 T16 已做，
            # 此前 dump 路径被 from_gsf 静默装成空库 → 首例 exit 3 误导）
            corpus = (Corpus.from_dump(args.corpus)
                      if _looks_like_dump(args.corpus)
                      else Corpus.from_gsf(args.corpus))
            data, warnings = _HANDLERS[args.cmd](args, corpus)
    except OSError as e:         # 终审 M6：目录/无权限等 OSError 家族（FileNotFoundError
                                # 仅其一）统一 exit 2 + JSON，不再 raw traceback
        _fail(2, f"cannot open corpus {args.corpus}: {e}",
              hints=[{"action": "gsr list --corpus <path.gsf|dump.txt> --like '<prefix>*'",
                      "reason": "用 --corpus 指定语料文件"}])
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
