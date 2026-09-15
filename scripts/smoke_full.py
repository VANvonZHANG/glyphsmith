#!/usr/bin/env python
# scripts/smoke_full.py —— M4 验收：全量 dump 零崩溃 + 非空率（不写 222 万文件）
"""全量冒烟：渲染 dump 全部字形，只计数 ok/empty/err，不写盘。

两口径（数字都进报告）：
- stroke-only（默认）：parts 只含字形自身，ref 行不走闭包——纯 ref 字形
  必然 empty，度量「渲染器对任意数据不崩溃」；
- --closure：corpus.resolve(name) 全闭包——度量「每个字形最终轮廓非空」。

--limit N   只冒烟前 N 个名字（确定性子集，便于快速验证）；
--workers N ≥2 多进程版（每 worker 自建 Corpus，分窗提交内存有界）；
            计数逻辑与串行版共用同一 _render_chunk，数字必须一致
            （已用 20000 例 stroke-only / 5000 例 closure 对照）。

用法：
    python scripts/smoke_full.py --limit 20000
    python scripts/smoke_full.py --limit 20000 --workers 8
    python scripts/smoke_full.py --limit 5000 --closure --workers 8
    python scripts/smoke_full.py                     # 全量 222 万（约 2 分钟）
    python scripts/smoke_full.py --closure --workers 16   # 全闭包全量
"""
from __future__ import annotations

import argparse
import sys
import time
from itertools import islice
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DUMP = Path("/home/zhangfan/Project/20260909_KAGE/data/dump_newest_only.txt")
PROGRESS_EVERY = 200_000        # stderr 进度粒度
CHUNK = 500                     # 每 worker 任务的名字数
WINDOW_FACTOR = 4               # 在途窗口 = workers × WINDOW_FACTOR 个 chunk

_STATE: dict = {}               # worker initializer 填充（串行版在主进程填充）


def _init_worker(dump, backend_name, closure):
    from importlib import import_module

    from gsrender.batch import _BACKEND_MODULES
    from gsrender.corpus import Corpus
    from gsrender.protocol import get_backend

    mod = _BACKEND_MODULES.get(backend_name)
    if mod is not None:                 # 未知名留给 get_backend 报 ValueError
        import_module(mod)
    _STATE["corpus"] = Corpus.from_dump(dump)
    _STATE["backend"] = get_backend(backend_name)
    _STATE["closure"] = closure


def _render_chunk(names):
    """计数一个名字块 → (ok, empty, err, 样例错误)。串行/多进程共用。"""
    from gsf.kage2 import parse_kage2
    from gsrender.corpus import ResolveResult

    corpus, backend = _STATE["corpus"], _STATE["backend"]
    ok = empty = err = 0
    errors: list[str] = []
    for name in names:
        try:
            if _STATE["closure"]:
                out = backend.render(corpus.resolve(name))
            else:                       # stroke-only 口径：parts 只有自身
                g = parse_kage2(corpus._data[name], name)
                out = backend.render(ResolveResult(name, g, {name: g}, []))
            if out.contours:
                ok += 1
            else:
                empty += 1
        except Exception as e:          # 冒烟口径：记录不中断
            err += 1
            if len(errors) < 3:
                errors.append(f"{name}: {type(e).__name__}: {e}")
    return ok, empty, err, errors


def main() -> None:
    ap = argparse.ArgumentParser(
        description="GSF 渲染器全量冒烟（零崩溃 + 非空率，不写盘）")
    ap.add_argument("--corpus", default=str(DUMP),
                    help="dump_newest_only.txt 路径")
    ap.add_argument("--backend", default="legacy-kurgm")
    ap.add_argument("--closure", action="store_true",
                    help="全闭包口径（默认 stroke-only）")
    ap.add_argument("--limit", type=int, default=None,
                    help="只冒烟前 N 个名字（默认全量）")
    ap.add_argument("--workers", type=int, default=1,
                    help="≥2 启用多进程版")
    a = ap.parse_args()
    if a.workers < 1:
        sys.exit("--workers must be >= 1")
    if a.limit is not None and a.limit < 0:
        sys.exit("--limit must be >= 0")

    scope = "closure" if a.closure else "stroke-only"
    print(f"smoke scope={scope} backend={a.backend} workers={a.workers} "
          f"limit={a.limit if a.limit is not None else 'all'}",
          file=sys.stderr)

    # 名字清单：主进程自建 corpus（worker 另建各自的，init 各 1 次）。
    # 配置错误（未知后端/文件缺失）在此干净退出，不留 raw traceback。
    try:
        _init_worker(a.corpus, a.backend, a.closure)
    except (ValueError, FileNotFoundError) as e:
        sys.exit(f"error: {e}")
    names = list(_STATE["corpus"].iter_names())
    if a.limit is not None:
        names = names[:a.limit]
    total = len(names)
    chunks = [names[i:i + CHUNK] for i in range(0, total, CHUNK)]

    ok = empty = err = done = 0
    samples: list[str] = []
    t0 = time.time()

    def tally(res):
        nonlocal ok, empty, err, done, samples
        c_ok, c_empty, c_err, c_errors = res
        ok += c_ok
        empty += c_empty
        err += c_err
        for e in c_errors:
            if len(samples) < 3:
                samples.append(e)
        done += CHUNK
        if done % PROGRESS_EVERY < CHUNK:
            print(f"{min(done, total)} done, err={err}, {time.time() - t0:.0f}s",
                  file=sys.stderr)

    if a.workers == 1:
        for chunk in chunks:
            tally(_render_chunk(chunk))
    else:
        from concurrent.futures import ProcessPoolExecutor
        it = iter(chunks)
        with ProcessPoolExecutor(max_workers=a.workers,
                                 initializer=_init_worker,
                                 initargs=(a.corpus, a.backend, a.closure)) as ex:
            while True:                  # 分窗提交：在途任务有界
                window = list(islice(it, a.workers * WINDOW_FACTOR))
                if not window:
                    break
                for res in ex.map(_render_chunk, window):
                    tally(res)

    dt = time.time() - t0
    for s in samples:
        print(f"error sample: {s}", file=sys.stderr)
    rate = total / dt if dt else float("inf")
    print(f"scope={scope} backend={a.backend} workers={a.workers} "
          f"total={total} ok={ok} empty={empty} err={err} "
          f"elapsed={dt:.1f}s rate={rate:.0f}/s")


if __name__ == "__main__":
    main()
