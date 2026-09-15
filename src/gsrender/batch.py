# src/gsrender/batch.py
"""multiprocessing 批量渲染：整库 → outdir/*.svg + 统计。

对简报骨架的现状适配（公开签名与 stats 口径不变）：
- 分窗提交：ProcessPoolExecutor.map 会一次性提交全部任务（源码
  `fs = [self.submit(fn, *args) for args in zip(*iterables)]`），222 万
  字形即 222 万 pending work items（各携带 data 串），GB 级驻留；按
  _WINDOW 批次提交，内存有界；
- worker 内自注册后端：spawn 启动方式下子进程不继承父进程注册表，
  按 _BACKEND_MODULES 映射在 worker 内 import（fork 下亦无副作用）；
- 文件名清洗与 cli._safe_filename（T14 审查 M2）同一助手；
- worker 用真身 ResolveResult（简报骨架 _R 的四字段等价类）。

冒烟口径：单字形任何异常都返回 err 元组由 errors 计数，不中断批次。
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from importlib import import_module
from itertools import islice
from pathlib import Path

_BACKEND_MODULES = {                 # 后端名 → 注册所在模块（worker 内 import）
    "legacy-kurgm": "gsrender.legacy_kurgm",
    "pen-minimal": "gsrender.pen_minimal",
}
_WINDOW = 4096                       # 单批提交任务数（在途内存上界）
_CHUNKSIZE = 64                      # ex.map 分发粒度（简报值）


def _render_one(job):
    """渲染单字形（worker 进程）。任何异常 → (name, "", True, err)，不冒泡。"""
    name, data, backend_name = job
    from gsf.kage2 import parse_kage2
    from gsrender.corpus import ResolveResult
    from gsrender.protocol import get_backend

    try:
        mod = _BACKEND_MODULES.get(backend_name)
        if mod is not None:
            import_module(mod)       # 未知名留给 get_backend 报 ValueError
        g = parse_kage2(data, name)
        out = get_backend(backend_name).render(
            ResolveResult(name, g, {name: g}, []))   # 冒烟口径：parts 只有自身
        return name, out.to_svg(), not out.contours, ""
    except Exception as e:                       # 冒烟口径：记录不中断
        return name, "", True, f"{type(e).__name__}: {e}"


def batch_render(corpus_path, outdir, *, backend="legacy-kurgm",
                 workers=4, dump=False) -> dict:
    """整库批量渲染 → outdir/<safe-name>.svg，返回 stats dict。

    stats = {"rendered", "errors", "empty"}：rendered 含空轮廓字形（empty
    是其子集）；单字形渲染异常与单文件写盘 OSError 都计入 errors、不中断
    批次（批量口径；outdir mkdir 失败则直接抛 OSError，由 CLI 层转 exit 2，
    与 M2 单字形契约一致）。
    """
    from gsrender.cli import _safe_filename
    from gsrender.corpus import Corpus

    corpus = Corpus.from_dump(corpus_path) if dump else Corpus.from_gsf(corpus_path)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)    # OSError 冒泡 → CLI exit 2
    # 原始 kage2 数据串进 worker（parsing 在 worker 内做，主进程不缓存字形）
    jobs = ((n, corpus._data[n], backend) for n in corpus.iter_names())
    stats = {"rendered": 0, "errors": 0, "empty": 0}

    def absorb(name, svg, empty, err) -> None:
        if not err:
            try:
                (outdir / f"{_safe_filename(name)}.svg").write_text(
                    svg, encoding="utf-8")
            except OSError as e:                 # 单文件写失败：计入不中断
                err = f"OSError: {e}"
        if err:
            stats["errors"] += 1
            return
        stats["rendered"] += 1
        if empty:
            stats["empty"] += 1

    if workers <= 1:
        for t in map(_render_one, jobs):
            absorb(*t)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            while True:                          # 分窗提交：内存有界（见模块 docstring）
                window = list(islice(jobs, _WINDOW))
                if not window:
                    break
                for t in ex.map(_render_one, window, chunksize=_CHUNKSIZE):
                    absorb(*t)
    return stats
