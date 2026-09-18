# src/glyphsmith/corpus.py
"""Corpus loader: GSF files / streaming scan of dump_newest_only + closure
resolution. v1 keeps no persistent state."""
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
    """A lazy dict from name → KAGE data string; parse results are cached."""

    # Parse cache ceiling: the full-dump smoke (2.22M glyphs) would push the
    # cache to ~3.5GB per process (measured ~1.6KB/glyph); past the limit it is
    # cleared wholesale — transparent to behaviour, the cache only affects
    # performance.
    _CACHE_LIMIT = 200_000

    def __init__(self, data: dict[str, str]):
        self._data = data
        self._cache: dict = {}

    # ── loading ──
    @classmethod
    def from_gsf(cls, path) -> "Corpus":
        # parse_dsl takes the whole text including blank/header/comment/meta
        # lines (calibration point a: parsing the whole file at once is
        # equivalent to parsing it block by block on blank lines); if the whole
        # text contains a syntactically bad block, fall back to block loading,
        # where bad blocks are skipped rather than aborting (the smoke
        # convention).
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
        """GlyphWiki dump_newest_only.txt: three columns `name | related | data`,
        space-padded, so a strip is all it takes (checked against a real dump
        with head -50: the first line is a header, the second a '+/-' separator
        with no '|', and data lines always have 3 columns). Read line by line,
        never loading the whole text."""
        data: dict[str, str] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                cells = line.split("|")
                if len(cells) < 3:               # separator lines (joined by '+') etc.
                    continue
                name = cells[0].strip()
                if not name or name == "name":   # empty name / header row
                    continue
                data[name] = cells[2].strip()
        return cls(data)

    # ── parsing ──
    def glyph_of(self, name: str):
        if name not in self._cache:
            if len(self._cache) >= self._CACHE_LIMIT:
                self._cache.clear()    # coarse ceiling: clear and rebuild; behaviour unchanged
            if name not in self._data:
                raise UnknownGlyphError(name)
            from gsf.kage2 import parse_kage2
            self._cache[name] = parse_kage2(self._data[name], name)
        return self._cache[name]

    def resolve(self, name: str) -> ResolveResult:
        """ref closure resolution: returns the {name → Glyph} part set plus
        loading/fallback warnings.

        DFS with a grey set (the current recursion path): only a back edge
        (target already on the path) is a cycle; finished shared parts (present
        in parts, not on the path) are skipped outright — diamond dependencies
        are not misreported (the brief's reference implementation treated a
        revisit as a cycle and raised spurious CycleErrors on DAGs with shared
        parts; fixed)."""
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
                # @version fallback. base != name: a self-referential
                # historical snapshot self@N gets no fallback (a newest-only
                # corpus has no X@N row, so falling back to itself would be a
                # false cycle — 94 cases in the T16 full-dump smoke; kurgm's
                # exact match finds nothing and skips it)
                target = base
                warnings.append(f"version ref fallback: {ref} -> {base}")
            else:
                warnings.append(f"dangling ref: {ref} (referenced by {name})")
                continue
            if target in on_path:               # back edge → cycle
                raise CycleError(path[path.index(target):])
            if target not in parts:
                self._collect(target, parts, path, on_path, warnings)
        path.pop()
        on_path.remove(name)

    # ── search ──
    def iter_names(self) -> Iterator[str]:
        return iter(self._data)

    def search(self, *, src=None, char=None, like=None) -> Iterator[str]:
        from gsf.names import parse_name, char_of
        for n in self._data:
            if like and not n.startswith(like.rstrip("*")):
                continue
            if src or char:
                p = parse_name(n)      # gsf.names.parse_name returns a dict (not an object)
                if src and p["src"] != src:
                    continue
                if char and char_of(p) != char:
                    continue
            yield n


def _parse_gsf_text(text: str):
    from gsf.dsl import parse_dsl
    return parse_dsl(text)


def _load_blocks(text: str, data: dict[str, str]) -> None:
    """Load block by block on blank lines (the fallback when whole-text parsing
    fails): syntactically bad blocks are skipped, not fatal."""
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
    # strip header/comment/meta lines; a block must contain a glyph line before
    # we try to parse it (header-only blocks are skipped outright).
    body = [l for l in block
            if not (l == "gsf/1" or l.lstrip().startswith(("#", "meta ")))]
    if not any(l.startswith("glyph ") for l in body):
        return
    try:
        glyphs = _parse_gsf_text("\n".join(body))
    except SyntaxError:
        return  # skip the bad block
    from gsf.writer import to_kage2
    for g in glyphs:
        data[g.name] = to_kage2(g)
