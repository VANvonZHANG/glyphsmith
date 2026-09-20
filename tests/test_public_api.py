# tests/test_public_api.py
"""Public API cold-import contract (final review C2).

After `import glyphsmith` the default backend legacy-kurgm must already be
registered — previously __init__ registered only pen-minimal, so a cold library
import of `Renderer()` raised ValueError outright (registration happened only
via cli.py's explicit import), making the README's "three lines after pip
install" shape unusable.
"""
import subprocess
import sys


def test_cold_interpreter_default_backend_registered():
    # cold interpreter: only `import glyphsmith` (never through cli.py);
    # get_backend("legacy-kurgm") must work
    code = ("from glyphsmith.protocol import get_backend; import glyphsmith; "
            "assert get_backend('legacy-kurgm').name == 'legacy-kurgm'")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_cold_interpreter_both_backends_registered():
    # The list gains a name whenever a backend ships (T8 added pen-minimal,
    # T14 added pen); an exact list is what makes this test able to catch a
    # backend that __init__ forgets to import.
    code = ("from glyphsmith.protocol import Backend; import glyphsmith; "
            "assert sorted(Backend.available()) == "
            "['legacy-kurgm', 'pen', 'pen-minimal']")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_renderer_default_backend_constructible():
    # same process: the default Renderer() backend constructs successfully (render
    # is not called)
    import glyphsmith
    assert glyphsmith.Renderer()._backend.name == "legacy-kurgm"
