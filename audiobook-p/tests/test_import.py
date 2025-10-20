def test_import():
    import importlib
    pkg = importlib.import_module('audiobook_p')
    assert hasattr(pkg, 'cli')
