# tests/test_smoke.py
def test_import():
    import glyphsmith, gsf.model
    assert glyphsmith.__version__ == "0.1.0"
    assert hasattr(gsf, "model")
