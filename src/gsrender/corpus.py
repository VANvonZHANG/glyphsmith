# src/gsrender/corpus.py
"""语料装载器：GSF 文件 / dump_newest_only 流式扫描 + 闭包解析。v1 零持久化。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator


class UnknownGlyphError(Exception):
    def __init__(self, name: str):
        super().__init__(f"unknown glyph: {name!r}")
        self.name = name


class ResolveResult:
    def __init__(self, name: str, glyph, parts: dict, warnings: list):
        self.name, self.glyph, self.parts, self.warnings = name, glyph, parts, warnings


class Corpus:
    """名字 → KAGE 数据串的惰性字典；parse 结果缓存。"""

    # parse 缓存上限：全量冒烟（222 万字形）会把缓存推到 ~3.5GB/进程
    # （实测 ~1.6KB/字形）；超限整体清空——行为透明，缓存只影响性能。
    _CACHE_LIMIT = 200_000

    def __init__(self, data: dict[str, str]):
        self._data = data
        self._cache: dict = {}

    # ── 装载 ──
    @classmethod
    def from_gsf(cls, path) -> "Corpus":
        # parse_dsl 直接吃含空行/头行/注释/meta 行的全文（校准点 a：整文件一次
        # 解析，等价于按空行分块逐块解析）；全文有语法坏块时回退分块装载，
        # 坏块跳过不中断（冒烟口径）。
        text = Path(path).read_text(encoding="utf-8")
        data: dict[str, str] = {}
        try:
            glyphs = _parse_gsf_text(text)
        except SyntaxError:
            _load_blocks(text, data)
            return cls(data)
        from gsf.writer import to_kage2
        for g in glyphs:
            data[g.name] = to_kage2(g)
        return cls(data)

    @classmethod
    def from_dump(cls, path) -> "Corpus":
        """GlyphWiki dump_newest_only.txt：`name | related | data` 三列，空格
        padding，strip 即得（真实 dump head -50 抽样核对：首行表头、次行
        '+/-' 分隔线无 '|'、数据行恒 3 列）。逐行流式读，不整载文本。"""
        data: dict[str, str] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                cells = line.split("|")
                if len(cells) < 3:               # 分隔线（'+' 连接）等
                    continue
                name = cells[0].strip()
                if not name or name == "name":   # 空名 / 表头行
                    continue
                data[name] = cells[2].strip()
        return cls(data)

    # ── 解析 ──
    def glyph_of(self, name: str):
        if name not in self._cache:
            if len(self._cache) >= self._CACHE_LIMIT:
                self._cache.clear()    # 粗粒度封顶：整清后重建，行为不变
            if name not in self._data:
                raise UnknownGlyphError(name)
            from gsf.kage2 import parse_kage2
            self._cache[name] = parse_kage2(self._data[name], name)
        return self._cache[name]

    def resolve(self, name: str) -> ResolveResult:
        """ref 闭包解析：返回 {名字 → Glyph} 部件集与装载/兜底警告。

        DFS 带灰集（当前递归路径）：回边（target 已在路径上）才是环；已完成的
        共享部件（在 parts、不在路径上）直接跳过——菱形依赖不误报（简报参考
        实现把"重访"当环，对共用部件的 DAG 会假阳性 CycleError，已修正）。"""
        if name not in self._data:
            raise UnknownGlyphError(name)
        warnings: list[str] = []
        parts: dict = {}
        self._collect(name, parts, [], set(), warnings)
        return ResolveResult(name, parts[name], parts, warnings)

    def _collect(self, name: str, parts: dict, path: list[str],
                 on_path: set[str], warnings: list[str]) -> None:
        from .legacy_kurgm.expansion import CycleError, ref_names

        parts[name] = self.glyph_of(name)
        path.append(name)
        on_path.add(name)
        for ref in ref_names(parts[name]):
            base = ref.partition("@")[0]
            if ref in self._data:
                target = ref
            elif base in self._data and base != name:
                # @版本兜底。base != name：self@N 历史快照自引用不兜底
                # （newest-only 语料没有 X@N 行，回退到自身是假环——
                # T16 全量冒烟 94 例；kurgm 精确匹配查不到即跳过）
                target = base
                warnings.append(f"version ref fallback: {ref} -> {base}")
            else:
                warnings.append(f"dangling ref: {ref} (referenced by {name})")
                continue
            if target in on_path:               # 回边 → 环
                raise CycleError(path[path.index(target):])
            if target not in parts:
                self._collect(target, parts, path, on_path, warnings)
        path.pop()
        on_path.remove(name)

    # ── 检索 ──
    def iter_names(self) -> Iterator[str]:
        return iter(self._data)

    def search(self, *, src=None, char=None, like=None) -> Iterator[str]:
        from gsf.names import parse_name, char_of
        for n in self._data:
            if like and not n.startswith(like.rstrip("*")):
                continue
            if src or char:
                p = parse_name(n)      # gsf.names.parse_name 返回 dict（非对象）
                if src and p["src"] != src:
                    continue
                if char and char_of(p) != char:
                    continue
            yield n


def _parse_gsf_text(text: str):
    from gsf.dsl import parse_dsl
    return parse_dsl(text)


def _load_blocks(text: str, data: dict[str, str]) -> None:
    """按空行分块装载（全文解析失败时的回退）：语法坏块跳过，不中断。"""
    block: list[str] = []
    for line in text.splitlines():
        if line.strip() == "":
            _flush(block, data)
            block = []
        else:
            block.append(line)
    _flush(block, data)


def _flush(block: list[str], data: dict[str, str]) -> None:
    if not block:
        return
    # 剥头行/注释/meta 行；块内须含 glyph 行才尝试解析（纯头部块直接跳过）。
    body = [l for l in block
            if not (l == "gsf/1" or l.lstrip().startswith(("#", "meta ")))]
    if not any(l.startswith("glyph ") for l in body):
        return
    try:
        glyphs = _parse_gsf_text("\n".join(body))
    except SyntaxError:
        return  # 坏块跳过
    from gsf.writer import to_kage2
    for g in glyphs:
        data[g.name] = to_kage2(g)
