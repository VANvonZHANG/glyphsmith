# tests/test_smoke.py
def test_import():
    import gsrender, gsf.model
    assert gsrender.__version__ == "0.1.0"
    assert hasattr(gsf, "model")
