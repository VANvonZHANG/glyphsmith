# tests/test_protocol.py
import pytest
from glyphsmith.protocol import RenderOptions, Backend, get_backend, Renderer


class DummyBackend(Backend):
    name = "dummy"

    def render(self, result, opts=None):
        from glyphsmith.outline import Outline
        o = Outline(); o.new_contour(); o.push(0, 0); o.push(10, 0)
        return o

    def render_separated(self, result, opts=None):
        return [self.render(result, opts)]


def test_options_defaults():
    o = RenderOptions()
    assert o.backend == "legacy-kurgm" and o.font == "mincho"
    assert o.use_curve is False and o.size is None


def test_registry_register_and_get():
    Backend.register(DummyBackend)
    b = get_backend("dummy")
    assert isinstance(b, DummyBackend)


def test_unknown_backend_raises():
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("nope")


def test_renderer_dispatch():
    r = Renderer(backend="dummy")
    out = r.render(object())   # DummyBackend 不看 result
    assert out.contours[0][1] == (10.0, 0.0, 0)
