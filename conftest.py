# conftest.py
def pytest_configure(config):
    config.addinivalue_line("markers", "golden: kurgm golden matrix tests")
    config.addinivalue_line("markers", "cross: cross-engine tests (needs node)")
