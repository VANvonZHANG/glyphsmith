# tests/test_public_api.py
"""公开 API 冷导入契约（终审 C2）。

`import glyphsmith` 后默认后端 legacy-kurgm 必须已注册——此前 __init__ 只注册
pen-minimal，库态冷导入 `Renderer()` 直接抛 ValueError（只有经 cli.py 的
显式 import 才注册），README「pip install 后三行起步」形态不可用。
"""
import subprocess
import sys


def test_cold_interpreter_default_backend_registered():
    # 冷解释器：仅 import glyphsmith（不经 cli.py），get_backend("legacy-kurgm")
    # 必须可用
    code = ("from glyphsmith.protocol import get_backend; import glyphsmith; "
            "assert get_backend('legacy-kurgm').name == 'legacy-kurgm'")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_cold_interpreter_both_backends_registered():
    code = ("from glyphsmith.protocol import Backend; import glyphsmith; "
            "assert sorted(Backend.available()) == "
            "['legacy-kurgm', 'pen-minimal']")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_renderer_default_backend_constructible():
    # 同进程：Renderer() 默认 backend 构造成功（不调 render）
    import glyphsmith
    assert glyphsmith.Renderer()._backend.name == "legacy-kurgm"
