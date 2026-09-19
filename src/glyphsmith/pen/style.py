# src/glyphsmith/pen/style.py
"""Declarative styles: YAML in, validated parameters out (spec §4.2).

Every failure is loud (spec §4.2.5). Unknown keys, unknown words, a missing
orientation band and an incomplete `endings` table are all errors: the note-17
lesson is that a silently dropped datum reads as "nothing wrong", and a style
file is exactly where a typo would hide.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import yaml

from glyphsmith.pen.centerline import BANDS

HEAD_WORDS = ("flat", "join-h", "tip", "corner-ul", "corner-ur", "join-v")
TAIL_WORDS = ("flat", "join-h", "hook", "tip", "heel-ll", "heel-lr", "cap-t",
              "join-v", "heel-ll-old", "heel-ll-new")
ENDING_WORDS = tuple(sorted(set(HEAD_WORDS) | set(TAIL_WORDS)))       # 12
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


class Style:
    """A validated style file. Loading never guesses: every field is checked."""

    def __init__(self, path: Path, raw: dict) -> None:
        self.path = path
        self.name = str(raw.get("name", path.stem))
        self.genre = resolve_genre(raw.get("genre", "serif"))
        self.endings_source = self._check_ending_source(raw.get("endings_source", "data"))
        self.width_profile = self._check_profile(raw.get("width_profile"))
        self.endings = self._check_endings(raw.get("endings"))
        self.decorations = self._check_decorations(raw.get("decorations") or {})
        self.caps = self._check_caps_joins(raw.get("caps") or {"default": "butt"},
                                           CAP_WORDS, "caps")
        self.joins = self._check_caps_joins(raw.get("joins") or {"default": "miter"},
                                            JOIN_WORDS, "joins")
        self.rules = self._check_rules(raw.get("rules") or [])

    # ── loading ────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, source) -> "Style":
        path = cls._resolve(source)
        try:
            raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_StyleLoader)
        except yaml.YAMLError as e:
            raise StyleError(f"{path}: cannot parse YAML: {e}") from None
        if raw is None:
            raise StyleError(f"{path}: empty style file")
        _check_keys(raw, _TOP_KEYS, str(path))
        return cls(path, raw)

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
        _check_keys(raw, _DECORATION_WORDS_SET, "decorations")
        out = {}
        for word, spec in raw.items():
            _check_keys(spec or {}, _DECOR_KEYS, f"decorations.{word}")
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
        out = []
        for i, rule in enumerate(raw):
            where = f"rules[{i}]"
            _check_keys(rule, _RULE_KEYS, where)
            when = rule.get("when") or {}
            then = rule.get("then") or {}
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
                    _check_keys(params, _ENDING_KEYS, f"{where}.then.scale.{word}")
                    for pname, pv in params.items():
                        if isinstance(pv, dict):
                            _check_keys(pv, {"by", "steps", "clamp"},
                                        f"{where}.then.scale.{word}.{pname}")
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


_DECORATION_WORDS_SET = set(DECORATION_WORDS)
