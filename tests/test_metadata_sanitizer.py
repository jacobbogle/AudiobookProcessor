
# We can't import the inner helper directly because it's nested; instead, test via behavior

def test_sanitize_stringified_list_like():
    from audiobook_p.main import sanitize_metadata_value as s
    assert s("['1/1']") == '1/1'
    assert s('["1/1"]') == '1/1'

def test_sanitize_bytes_and_list():
    from audiobook_p.main import sanitize_metadata_value as s
    b = b'hello'
    assert s(b) == b
    assert s([b]) == b

def test_sanitize_mutagen_like_object():
    class MockPic:
        def __init__(self, data):
            self.data = data
    from audiobook_p.main import sanitize_metadata_value as s
    m = MockPic(b'abc')
    assert s(m) == b'abc'


def test_sanitize_list_multi():
    from audiobook_p.main import sanitize_metadata_value as s
    assert s("['a','b']") == ['a','b']
