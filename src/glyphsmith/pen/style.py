# src/glyphsmith/pen/style.py
"""Declarative styles: YAML in, validated parameters out (spec §4.2).

Every failure is loud (spec §4.2.5). Unknown keys, unknown words, a missing
orientation band and an incomplete `endings` table are all errors: the note-17
lesson is that a silently dropped datum reads as "nothing wrong", and a style
file is exactly where a typo would hide.
"""
from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass
from dataclasses import replace as _dc_replace
from functools import lru_cache
from pathlib import Path

import yaml

from glyphsmith.pen.centerline import BANDS, vertex_ts
from glyphsmith.pen.nib import StrokePlan

HEAD_WORDS = ("flat", "join-h", "tip", "corner-ul", "corner-ur", "join-v")
TAIL_WORDS = ("flat", "join-h", "hook", "tip", "heel-ll", "heel-lr", "cap-t",
              "join-v", "heel-ll-old", "heel-ll-new")
ENDING_WORDS = tuple(sorted(set(HEAD_WORDS) | set(TAIL_WORDS)))       # 12
# The head words that rewrite the bend join (spec §4.2.2): the corner of a bent
# stroke takes its join from the *ending* that names that corner, not from
# joins.bend (which is only the default for an unnamed corner).
BEND_WORDS = ("corner-ul", "corner-ur")
CAP_WORDS = ("butt", "square", "round")
JOIN_WORDS = ("miter", "bevel", "round")
DECORATION_WORDS = ("wedge", "hook", "heel")
DECORATION_AT = ("head", "tail")
DECORATION_SHAPES = ("triangle",)
GENRES = ("serif", "sans", "round")
GENRE_ALIASES = {"mincho": "serif", "song": "serif", "ming": "serif",
                 "gothic": "sans", "hei": "sans", "heiti": "sans",
                 "maru": "round", "rounded": "round"}
REL_WORDS = ("meets", "crosses", "tee", "parallel", "near")
SIDES = ("left", "right", "above", "below")
ENDING_SOURCES = ("data", "style")
THEN_WORDS = ("suppress", "replace", "scale")

_TOP_KEYS = {"name", "genre", "endings_source", "width_profile", "endings",
             "decorations", "caps", "joins", "rules"}
_ENDING_KEYS = {"length", "width", "size", "shape", "min_width", "join",
                "miter_limit"}
# `then.scale` multiplies a number that is already on a Decoration, so its
# params are exactly the numeric Decoration fields — a strict subset of
# _ENDING_KEYS. `shape`/`join` are not numbers and `min_width`/`miter_limit`
# belong to an ending's planning, not to an ornament: accepting them here used
# to defer the failure to a TypeError inside `apply`.
_SCALE_KEYS = {"length", "size", "width"}
_DECOR_KEYS = {"on", "at", "shape", "size", "length", "width"}
_RULE_KEYS = {"id", "when", "then"}
_WHEN_KEYS = {"rel", "from", "to", "at", "side"}
_SCALE_RV = ("distance",)


class StyleError(Exception):
    """A style file that cannot be used; the message names the file and the key."""


_BOOL_TAG = "tag:yaml.org,2002:bool"


class _StyleLoader(yaml.SafeLoader):
    """Style YAML is read with the YAML 1.2 core boolean spelling.

    PyYAML implements YAML 1.1, where the bare key `on` resolves to `True`:
    `wedge: {on: horizontal, ...}` would then fail as "unknown key True" — a
    message that names nothing the author actually wrote. Restricting booleans
    to true/false keeps every style key the string it looks like.
    """


_StyleLoader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != _BOOL_TAG]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_StyleLoader.add_implicit_resolver(
    _BOOL_TAG, re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def builtin_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "styles"


def available() -> list[str]:
    return sorted(p.stem for p in builtin_dir().glob("*.yaml"))


def resolve_genre(word: str) -> str:
    w = str(word).lower()
    if w in GENRES:
        return w
    if w in GENRE_ALIASES:
        return GENRE_ALIASES[w]
    raise StyleError(f"unknown genre {word!r} (allowed: {', '.join(GENRES)}; "
                     f"aliases: {', '.join(sorted(GENRE_ALIASES))})")


def _check_mapping(d, where: str) -> None:
    """Shape check on its own, for keys whose contents are checked separately."""
    if not isinstance(d, dict):
        raise StyleError(f"{where}: expected a mapping, got {type(d).__name__}")


def _check_keys(d, allowed, where: str) -> None:
    _check_mapping(d, where)
    for k in d:
        if k not in allowed:
            raise StyleError(f"{where}: unknown key {k!r} "
                             f"(allowed: {', '.join(sorted(allowed))})")


def _positive(v, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise StyleError(f"{where}: expected a number, got {v!r}")
    f = float(v)
    if not math.isfinite(f) or f <= 0.0:
        raise StyleError(f"{where}: expected a finite positive number, got {v!r}")
    return f


def _nonneg(v, where: str) -> float:
    f = _positive(v, where) if v else 0.0
    return f


@dataclass(frozen=True)
class Decoration:
    """One ornament placed in a stroke end's local frame (spec §4.3.5). All
    numeric parameters are multiples of the local full width."""
    kind: str
    at: str                                             # head | tail
    length: float = 0.0
    size: float = 0.0
    width: float = 0.0
    join: str = "bevel"


def profile_at(profile, t: float) -> float:
    """Piecewise-linear width profile, clamped outside [0, 1] (spec §4.2.2)."""
    if t <= profile[0][0]:
        return profile[0][1]
    if t >= profile[-1][0]:
        return profile[-1][1]
    for i in range(len(profile) - 1):
        t0, w0 = profile[i]
        t1, w1 = profile[i + 1]
        if t0 <= t <= t1:
            return w1 if t1 == t0 else w0 + (w1 - w0) * (t - t0) / (t1 - t0)
    return profile[-1][1]


def ladder(value: float, steps) -> float:
    """Piecewise-constant lookup (spec §4.2.4).

    Legacy's adjustHane is literally `7 - floor(mn / 15)` — a 15-unit ladder,
    not an interpolation — so the declarative form is a step table, not a spline.
    Entries are read in order; the last `d <= value` wins.
    """
    factor = steps[0][1]
    for d, f in steps:
        if value < d:
            break
        factor = f
    return factor


# ── reading a style file ───────────────────────────────────────────────────
# `Style.load` runs once per glyph on the render path (the pen backend loads
# the style inside `expand_to_graph`), and one load is 3.4 ms of YAML parse
# against 0.01 ms of stat + read: memoising the parse is what keeps a
# full-corpus run from spending ~500 s per worker on the same recipe. The
# cache hands out a copy, never the mapping itself (see `_read_style_file`).


@lru_cache(maxsize=None)
def _parse_style_file(resolved: str, mtime_ns: int, size: int, text: str) -> dict:
    """Parse and top-level-check one revision of one style file.

    The key is the resolved path, the file's stat and the text actually read.
    The stat alone is not enough to satisfy "an edited file is re-read": this
    filesystem stamps mtime with a ~4 ms granule (two immediate rewrites of the
    same length share an mtime_ns and a size — measured, not assumed), so a
    stat-keyed cache serves the old parse until the clock moves and is exactly
    the silent staleness this project forbids. The text is in hand anyway (the
    read cannot be skipped: see `_read_style_file`) and closes that hole, so a
    run can never keep serving a style the author has since edited.

    `lru_cache` memoises a returned mapping only; an exception is not stored,
    so a YAML syntax error or an empty file re-raises on every load instead of
    being cached as if the failure were the parse.

    Entries are one per (file, revision) pair the process has read, so the
    unbounded cache is a handful of small mappings, not a growing one.
    """
    path = Path(resolved)
    try:
        raw = yaml.load(text, Loader=_StyleLoader)
    except yaml.YAMLError as e:
        raise StyleError(f"{path}: cannot parse YAML: {e}") from None
    if raw is None:
        raise StyleError(f"{path}: empty style file")
    _check_keys(raw, _TOP_KEYS, str(path))
    return raw


def _read_style_file(path: Path) -> dict:
    """Read a style file and return a *private* copy of its parsed mapping.

    The read is deliberately not behind the cache, only the parse: the read is
    where an unreadable file is reported, and a cache hit must not turn "this
    file cannot be read now" into the parse of an earlier, readable revision.
    `tests/test_cli.py::test_styles_command_reports_an_unreadable_style_file`
    makes exactly that call — it loads sans-hei.yaml (twice, in the same
    process), then makes it unreadable and requires the error, which a
    read-through cache answers with exit 0 (`assert 0 == 2`, measured). The
    read is 11 us against the 3450 us parse, 0.3% of what the cache saves, so
    it is paid on every load.

    The copy is what keeps two `Style` objects independent: `Style` stores
    sub-dicts of the parse as they are (a rule's `when`/`then`) and a caller
    may hold and mutate a loaded style, so the mapping the cache holds must
    never be reachable from one. ~50 us per load.
    """
    try:
        st = path.stat()
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise StyleError(f"{path}: cannot read style file: {e}") from None
    return copy.deepcopy(
        _parse_style_file(str(path), st.st_mtime_ns, st.st_size, text))


class Style:
    """A validated style file. Loading never guesses: every field is checked."""

    def __init__(self, path: Path, raw: dict) -> None:
        self.path = path
        self.name = str(raw.get("name", path.stem))
        self.genre = resolve_genre(raw.get("genre", "serif"))
        self.endings_source = self._check_ending_source(raw.get("endings_source", "data"))
        self.width_profile = self._check_profile(raw.get("width_profile"))
        self.endings = self._check_endings(raw.get("endings"))
        self.decorations = self._check_decorations(raw.get("decorations"))
        self.caps = self._check_caps_joins(raw.get("caps") or {"default": "butt"},
                                           CAP_WORDS, "caps")
        self.joins = self._check_caps_joins(raw.get("joins") or {"default": "miter"},
                                            JOIN_WORDS, "joins")
        self.rules = self._check_rules(raw.get("rules"))

    # ── loading ────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, source) -> "Style":
        # The path is resolved so that every spelling of one file (a name, a
        # relative path, a symlink) is one cache entry, and so that the errors
        # name the file's real identity. T8 review: a raw OSError from the read
        # used to reach the CLI's corpus-worded handler ("cannot open corpus
        # <path>"); a style read is a style error naming the file, and
        # `_read_style_file` keeps that true on a cache hit as well.
        path = cls._resolve(source).resolve()
        return cls(path, _read_style_file(path))

    @staticmethod
    def _resolve(source) -> Path:
        p = Path(source)
        if p.is_file():
            return p
        cand = builtin_dir() / f"{source}.yaml"
        if cand.is_file():
            return cand
        raise StyleError(f"unknown style {str(source)!r} "
                         f"(available: {', '.join(available())})")

    @staticmethod
    def builtin_dir() -> Path:
        return builtin_dir()

    @staticmethod
    def available() -> list[str]:
        return available()

    # ── field checks ───────────────────────────────────────────────────────
    @staticmethod
    def _check_ending_source(v) -> str:
        if v not in ENDING_SOURCES:
            raise StyleError(f"endings_source: unknown value {v!r} "
                             f"(allowed: {', '.join(ENDING_SOURCES)})")
        return v

    @staticmethod
    def _check_profile(raw) -> dict:
        _check_keys(raw or {}, set(BANDS), "width_profile")
        out = {}
        for band in BANDS:
            if band not in (raw or {}):
                raise StyleError(f"width_profile: missing band {band!r} "
                                 f"(all of {', '.join(BANDS)} are required)")
            pts = raw[band]
            if not isinstance(pts, list) or len(pts) < 2:
                raise StyleError(f"width_profile.{band}: expected a list of "
                                 f"[t, width] pairs with at least two entries")
            parsed = []
            for pair in pts:
                if not isinstance(pair, list) or len(pair) != 2:
                    raise StyleError(f"width_profile.{band}: bad point {pair!r}")
                t = pair[0]
                if isinstance(t, bool) or not isinstance(t, (int, float)) \
                        or not math.isfinite(float(t)) or not 0.0 <= float(t) <= 1.0:
                    raise StyleError(f"width_profile.{band}: t must be in [0, 1], "
                                     f"got {t!r}")
                parsed.append((float(t), _positive(pair[1], f"width_profile.{band}")))
            parsed.sort()
            out[band] = parsed
        return out

    @staticmethod
    def _check_endings(raw) -> dict:
        # Unknown words are reported BEFORE missing ones: a typo (`hookk`) should
        # read as a typo, not as "missing hook" — the two are the same data bug
        # but only one message tells the author what to fix.
        # `None` (an absent or empty `endings:`) is not a shape error: it falls
        # through to the missing-words check, which names all twelve words.
        if raw is not None:
            _check_mapping(raw, "endings")
        for word, spec in (raw or {}).items():
            if word not in ENDING_WORDS:
                raise StyleError(f"endings: unknown word {word!r} "
                                 f"(allowed: {', '.join(ENDING_WORDS)})")
            _check_keys(spec or {}, _ENDING_KEYS, f"endings.{word}")
            if "join" in (spec or {}) and spec["join"] not in JOIN_WORDS:
                raise StyleError(f"endings.{word}.join: unknown join {spec['join']!r} "
                                 f"(allowed: {', '.join(JOIN_WORDS)})")
            for k in ("length", "width", "size", "min_width", "miter_limit"):
                if k in (spec or {}):
                    _positive(spec[k], f"endings.{word}.{k}")
        missing = [w for w in ENDING_WORDS if w not in (raw or {})]
        if missing:
            raise StyleError(f"endings: missing {', '.join(missing)} "
                             f"(all {len(ENDING_WORDS)} GSF head/tail words must be "
                             f"listed; use {{}} for 'no extra geometry')")
        return {w: dict(raw[w] or {}) for w in raw}

    @staticmethod
    def _check_decorations(raw) -> dict:
        # `None` (an absent or empty `decorations:`) means "no ornaments"; any
        # other non-mapping is a shape error, as under `endings`.
        if raw is None:
            return {}
        _check_keys(raw, _DECORATION_WORDS_SET, "decorations")
        out = {}
        for word, spec in raw.items():
            # The normalised spec is what gets checked: the old `spec or {}`
            # passed the shape check on an empty mapping and then called `.get`
            # on the original falsy value (`wedge: []` → AttributeError).
            spec = {} if spec is None else spec
            _check_keys(spec, _DECOR_KEYS, f"decorations.{word}")
            if spec.get("on") not in BANDS:
                raise StyleError(f"decorations.{word}.on: unknown band "
                                 f"{spec.get('on')!r} (allowed: {', '.join(BANDS)})")
            if spec.get("at") not in DECORATION_AT:
                raise StyleError(f"decorations.{word}.at: unknown end "
                                 f"{spec.get('at')!r} (allowed: {', '.join(DECORATION_AT)})")
            if spec.get("shape") not in DECORATION_SHAPES:
                raise StyleError(f"decorations.{word}.shape: unknown shape "
                                 f"{spec.get('shape')!r} "
                                 f"(allowed: {', '.join(DECORATION_SHAPES)})")
            for k in ("size", "length", "width"):
                if k in spec:
                    _positive(spec[k], f"decorations.{word}.{k}")
            out[word] = dict(spec)
        return out

    @staticmethod
    def _check_caps_joins(raw, words, where) -> dict:
        _check_keys(raw, set(BANDS) | {"default", "bend"}, where)
        if "bend" in raw and where == "caps":
            raise StyleError(f"{where}: 'bend' is only meaningful for joins")
        for k, v in raw.items():
            if v not in words:
                raise StyleError(f"{where}.{k}: unknown value {v!r} "
                                 f"(allowed: {', '.join(words)})")
        return dict(raw)

    @staticmethod
    def _check_rules(raw) -> list:
        # `None` (an absent or empty `rules:`) means "no rules"; a scalar or a
        # mapping is a shape error. Without the check a `rules: 5` died inside
        # `enumerate(5)` as a bare TypeError that named nothing the author wrote.
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise StyleError(f"rules: expected a list, got {type(raw).__name__}")
        out = []
        for i, rule in enumerate(raw):
            where = f"rules[{i}]"
            _check_keys(rule, _RULE_KEYS, where)
            when, then = rule.get("when"), rule.get("then")
            # Both are mappings or absent. A list `then: [suppress]` used to pass
            # the one-word check below (its element iterated as a key) and only
            # fail at `then[kind]` — TypeError: list indices must be integers.
            if when is not None:
                _check_mapping(when, f"{where}.when")
            if then is not None:
                _check_mapping(then, f"{where}.then")
            when, then = when or {}, then or {}
            _check_keys(when, _WHEN_KEYS, f"{where}.when")
            if when.get("rel") not in REL_WORDS:
                raise StyleError(f"{where}.when.rel: unknown relation "
                                 f"{when.get('rel')!r} "
                                 f"(allowed: {', '.join(REL_WORDS)})")
            for side_key in ("from", "to"):
                v = when.get(side_key)
                if v is not None and v not in ENDING_WORDS and v not in BANDS:
                    raise StyleError(f"{where}.when.{side_key}: unknown filter {v!r} "
                                     f"(an orientation band or a GSF ending word)")
            if when.get("at") not in (None, "head", "tail", "mid"):
                raise StyleError(f"{where}.when.at: unknown end {when['at']!r} "
                                 f"(allowed: head, tail, mid)")
            if when.get("rel") == "near" and when.get("at") == "mid":
                # `graph.nearest` anchors at a stroke *end*: `_end_point` maps
                # anything that is not "head" to the tail, so `mid` would read
                # as `tail` while claiming otherwise. Reject rather than alias.
                raise StyleError(f"{where}.when.at: 'mid' cannot be used with "
                                 f"rel 'near' (the nearest query anchors at a "
                                 f"stroke end, and a 'mid' anchor would silently "
                                 f"be the tail)")
            if when.get("side") not in (None,) + SIDES:
                raise StyleError(f"{where}.when.side: unknown side {when['side']!r} "
                                 f"(allowed: {', '.join(SIDES)})")
            kinds = [k for k in then if k in THEN_WORDS]
            if len(kinds) != 1 or len(then) != 1:
                raise StyleError(f"{where}.then: exactly one of "
                                 f"{', '.join(THEN_WORDS)} is required, got {then!r}")
            kind = kinds[0]
            if kind == "suppress":
                Style._check_decoration_word(then[kind], f"{where}.then.suppress")
            elif kind == "replace":
                _check_keys(then[kind], set(DECORATION_WORDS), f"{where}.then.replace")
                for k, v in then[kind].items():
                    Style._check_decoration_word(v, f"{where}.then.replace.{k}")
            else:
                _check_mapping(then[kind], f"{where}.then.scale")
                for word, params in then[kind].items():
                    Style._check_decoration_word(word, f"{where}.then.scale")
                    _check_keys(params, _SCALE_KEYS, f"{where}.then.scale.{word}")
                    for pname, pv in params.items():
                        if isinstance(pv, dict):
                            _check_keys(pv, {"by", "steps", "clamp"},
                                        f"{where}.then.scale.{word}.{pname}")
                            if pv.get("clamp", True) is not True:
                                # `ladder` clamps by construction: the first
                                # entry's factor applies below it and the last
                                # above it, so there is no unclamped mode to
                                # switch off. `clamp: true` stays legal as
                                # documentation; anything else is rejected or
                                # the author would believe it did something.
                                raise StyleError(
                                    f"{where}.then.scale.{word}.{pname}.clamp: "
                                    f"the ladder always clamps (its first entry "
                                    f"applies below and its last above), so "
                                    f"clamp: false is not representable; write "
                                    f"clamp: true or omit the key")
                            if pv.get("by") not in _SCALE_RV:
                                raise StyleError(
                                    f"{where}.then.scale.{word}.{pname}.by: "
                                    f"unknown driver {pv.get('by')!r} "
                                    f"(allowed: {', '.join(_SCALE_RV)})")
                            steps = pv.get("steps")
                            if not isinstance(steps, list) or not steps:
                                raise StyleError(
                                    f"{where}.then.scale.{word}.{pname}.steps: "
                                    f"expected a non-empty [[distance, factor], ...]")
                            for pair in steps:
                                if not isinstance(pair, list) or len(pair) != 2:
                                    raise StyleError(
                                        f"{where}.then.scale.{word}.{pname}.steps: "
                                        f"bad entry {pair!r}")
                                _nonneg(pair[0], f"{where}.then.scale.steps.distance")
                                _positive(pair[1], f"{where}.then.scale.steps.factor")
                        else:
                            _positive(pv, f"{where}.then.scale.{word}.{pname}")
            out.append(dict(rule))
        return out

    @staticmethod
    def _check_decoration_word(word, where) -> None:
        if word not in DECORATION_WORDS:
            raise StyleError(f"{where}: unknown decoration {word!r} "
                             f"(allowed: {', '.join(DECORATION_WORDS)})")

    # ── planning ───────────────────────────────────────────────────────────
    # The validated parameters meet the geometry (spec §4.2.2's end x profile
    # table). Units: every number under `endings`/`decorations` is a multiple of
    # the local *full* width (dimensionless), which is what lets one recipe fit
    # the serif, sans and round styles alike. `miter_limit` is the exception: a
    # ratio to the half-width, as in CSS.
    def cap_for(self, band: str) -> str:
        return self.caps.get(band, self.caps.get("default", "butt"))

    def join_for(self, band: str) -> str:
        return self.joins.get(band, self.joins.get("default", "miter"))

    def _ending(self, node, end: str):
        """The data's ending word for one end, or None when it is ignored.

        The return value is `object`: `graph.build` hands back the raw int for a
        code the data layer's name table does not cover (see `_ending_word`).
        """
        if self.endings_source == "style" or node.pure_geometry:
            return None
        return node.head if end == "head" else node.tail

    def _ending_word(self, node, end: str, warnings: list) -> str | None:
        """The ending word this style can act on, or None when it cannot name it.

        `graph.build` deliberately keeps a GSF code that misses HEAD_NAMES /
        TAIL_NAMES as the raw int (`graph.py`: `TAIL_NAMES.get(code, code)`), and
        that is a corpus path, not a corner case: the tail table covers only
        {0, 2, 4, 7, 13, 23, 24, 32, 313, 413}, while a 339,530-stroke sample of
        the real corpus carries 8 (33,200 strokes), 5 (7,179) and smaller counts
        of 1, 100, 200, 300, 404, 1008, 2008 — about 12% of all strokes. So this
        must never raise, and it must never guess.

        An unnameable end behaves as if the style had nothing configured for it:
        no ending decoration, no width modulation, caps left at the band default.
        Inventing a meaning for the code (8 -> "tip") would be a private alias
        minted by the pen layer out of the data layer's vocabulary; the gap is in
        the data layer's name table and belongs reported there.

        The code is therefore reported, once per end, as `unmapped ending code
        <code> at <end>` — a stable prefix for the corpus audit to aggregate by.
        Swallowing it would read as "nothing wrong" (note 17), which is exactly
        the failure mode this project keeps paying for.
        """
        word = self._ending(node, end)
        if word is None or isinstance(word, str):
            return word
        msg = f"unmapped ending code {word} at {end}"
        if msg not in warnings:
            warnings.append(msg)
        return None

    def _bands_decorations(self, node, end: str, word: str | None) -> list:
        """Ornaments the style adds where the data left the end `flat`
        (spec §4.2.2 'decorations apply where the ending is flat')."""
        if node.pure_geometry or word != "flat":
            return []
        out = []
        for kind, spec in self.decorations.items():
            if spec.get("on") != node.orientation or spec.get("at") != end:
                continue
            out.append(Decoration(kind=kind, at=end,
                                  length=float(spec.get("length", 0.0)),
                                  size=float(spec.get("size", 0.0)),
                                  width=float(spec.get("width", 0.0)),
                                  join=str(spec.get("join", "bevel"))))
        return out

    def _end_width(self, word: str | None, w: float) -> float:
        """Apply the ending's width modulation. `tip.min_width` is a multiple of
        the local full width (spec §4.3.5), so it scales with the band."""
        spec = self.endings.get(word or "", {})
        if "min_width" in spec:                 # `tip`: taper the end
            return w * min(1.0, float(spec["min_width"]))
        return w

    def plan_for(self, node) -> StrokePlan:
        # The ending words are resolved once, here: a code the name table cannot
        # name becomes None (no ending geometry, no width modulation) and one
        # `unmapped ending code <code> at <end>` warning per unnameable end, which
        # the plan carries to the backend's aggregate.
        warnings: list[str] = []
        head_word = self._ending_word(node, "head", warnings)
        tail_word = self._ending_word(node, "tail", warnings)

        prof = self.width_profile[node.orientation]
        ts = vertex_ts(list(node.centerline))
        widths = [profile_at(prof, t) for t in ts]
        widths[0] = self._end_width(head_word, widths[0])
        widths[-1] = self._end_width(tail_word, widths[-1])

        cap_head, cap_tail = self.cap_for(node.orientation), self.cap_for(node.orientation)
        if head_word in ("join-h", "join-v"):
            cap_head = "butt"
        if tail_word in ("join-h", "join-v"):
            cap_tail = "butt"

        bend = self.join_for("bend")
        for bend_word in BEND_WORDS:
            spec = self.endings.get(bend_word, {})
            if bend_word in (head_word, tail_word) and "join" in spec:
                bend = spec["join"]
        joins = [bend] * max(0, len(node.centerline) - 2)

        decos = []
        for end, word in (("head", head_word), ("tail", tail_word)):
            decos += self._bands_decorations(node, end, word)
            spec = self.endings.get(word or "", {})
            if word is not None and (word == "hook" or word.startswith("heel")):
                decos.append(Decoration(kind=word, at=end,
                                        length=float(spec.get("length", 0.0)),
                                        size=float(spec.get("size", 0.0)),
                                        width=float(spec.get("width", 0.0)),
                                        join=str(spec.get("join", "bevel"))))
        return StrokePlan(centerline=[tuple(p) for p in node.centerline],
                          widths=widths, cap_head=cap_head, cap_tail=cap_tail,
                          joins=joins,
                          miter_limit=float(self.endings.get("corner-ul", {})
                                            .get("miter_limit", 3.0)),
                          decorations=decos, warnings=warnings,
                          stroke_id=node.id)

    # ── rules ──────────────────────────────────────────────────────────────
    @staticmethod
    def _subject_end(node, word) -> str:
        """Which end of the subject the rule's `from` filter refers to."""
        if getattr(node, "head", None) == word:
            return "head"
        if getattr(node, "tail", None) == word:
            return "tail"
        return "tail"                       # orientation filter: the tail is the
                                            # end decorations usually hang off

    @staticmethod
    def _matches(node, word) -> bool:
        return node.orientation == word or node.head == word or node.tail == word

    def _candidates(self, graph, node, when) -> list:
        """(subject_end, other_node, distance) tuples satisfying `when`."""
        rel = when["rel"]
        if rel == "near":
            # Both filters are stated conditions, so both must run. `from` names
            # the anchor end *and* filters the subject: always checked here.
            if when.get("from") and not self._matches(node, when["from"]):
                return []
            end = when.get("at") or self._subject_end(node, when.get("from"))
            # The `to` filter splits by kind, because `graph.nearest` compares
            # `want` against `node.orientation` only:
            #   * an orientation band is passed through `want=`, which SELECTS
            #     the nearest node *of that band*. Asking for the unfiltered
            #     nearest and post-rejecting instead would pick the nearest node
            #     of any band and drop the rule whenever another band happened
            #     to be nearer — a silently dead rule, and less faithful than
            #     legacy, which iterates only its own band (mincho.py:297-301).
            #   * an ending word (or no filter) cannot be matched by `want=`, so
            #     the nearest is asked for unfiltered and the hit is POST-
            #     checked with `_matches`, as the edge branch does.
            to = when.get("to")
            want = to if to in BANDS else None
            hit = graph.nearest(node.id, at=end, want=want,
                                side=when.get("side"))
            if hit is None:
                return []
            other, dist, _other_end = hit
            if want is None and to is not None and not self._matches(other, to):
                return []
            return [(end, other, dist)]
        out = []
        for e in graph.edges:
            if e.a_id == node.id:
                end, other = e.a_end, graph.node(e.b_id)
            elif e.b_id == node.id:
                end, other = e.b_end, graph.node(e.a_id)
            else:
                continue
            if e.kind != rel:
                continue
            if when.get("at") and end != when["at"]:
                continue
            if when.get("from") and not self._matches(node, when["from"]):
                continue
            if when.get("to") and not self._matches(other, when["to"]):
                continue
            out.append((end, other, e.distance))
        return out

    def apply_rules(self, graph, plans) -> None:
        """Evaluate every rule against every plan, in file order (spec §4.2.4).

        `suppress` removes the decoration outright; `scale` multiplies, so two
        matching rules compound. Both are deterministic and explainable — that
        is the whole point of keeping the action vocabulary this small.
        """
        for plan in plans.values():
            node = graph.node(plan.stroke_id)
            for rule in self.rules:
                when, then = rule["when"], rule["then"]
                hits = self._candidates(graph, node, when)
                if not hits:
                    continue
                if "suppress" in then:
                    plan.decorations = [d for d in plan.decorations
                                        if d.kind != then["suppress"]]
                elif "replace" in then:
                    old, new = next(iter(then["replace"].items()))
                    plan.decorations = [
                        _dc_replace(d, kind=new) if d.kind == old else d
                        for d in plan.decorations]
                else:
                    for word, params in then["scale"].items():
                        for i, d in enumerate(plan.decorations):
                            if d.kind != word:
                                continue
                            dist = min(h[2] for h in hits)
                            upd = {}
                            for pname, pv in params.items():
                                cur = getattr(d, pname, 0.0)
                                factor = (ladder(dist, pv["steps"])
                                          if isinstance(pv, dict) else float(pv))
                                upd[pname] = cur * factor
                            plan.decorations[i] = _dc_replace(d, **upd)

    def apply(self, graph) -> dict:
        plans = {n.id: self.plan_for(n) for n in graph.nodes}
        self.apply_rules(graph, plans)
        return plans


_DECORATION_WORDS_SET = set(DECORATION_WORDS)
