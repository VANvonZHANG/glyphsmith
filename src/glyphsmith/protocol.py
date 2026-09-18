# src/glyphsmith/protocol.py
"""Backend protocol: registration and dispatch for the two backends (legacy-kurgm / pen*)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from glyphsmith.corpus import ResolveResult
    from glyphsmith.outline import Outline


@dataclass(frozen=True)
class RenderOptions:
    backend: str = "legacy-kurgm"
    font: str = "mincho"          # CLI aliases serif→mincho, sans→gothic are resolved in cli
    use_curve: bool = False
    size: int | None = None


class Backend(ABC):
    name: ClassVar[str]
    _registry: dict[str, type["Backend"]] = {}

    @classmethod
    def register(cls, sub: type["Backend"]) -> None:
        cls._registry[sub.name] = sub

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._registry)

    @abstractmethod
    def render(self, result: "ResolveResult",
               opts: "RenderOptions | None" = None) -> "Outline": ...

    @abstractmethod
    def render_separated(self, result: "ResolveResult",
                         opts: "RenderOptions | None" = None) -> "list[Outline]": ...


def get_backend(name: str) -> Backend:
    try:
        return Backend._registry[name]()
    except KeyError:
        raise ValueError(f"unknown backend: {name!r} (available: {Backend.available()})")


class Renderer:
    """The spec §5.2 public API: a corpus.resolve() result goes in, an Outline comes out."""

    def __init__(self, backend: str = "legacy-kurgm", font: str = "mincho",
                 **opts) -> None:
        self._backend = get_backend(backend)
        self._opts = RenderOptions(backend=backend, font=font, **opts)

    def render(self, result: "ResolveResult") -> "Outline":
        return self._backend.render(result, self._opts)

    def render_separated(self, result: "ResolveResult") -> "list[Outline]":
        return self._backend.render_separated(result, self._opts)
