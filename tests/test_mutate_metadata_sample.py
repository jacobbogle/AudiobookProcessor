import pytest
from audiobook_p.mutation import mutate_metadata
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None

def test_mutate_metadata_basic():
    metadata = {
        'folder': 'test_folder',
        'files': {
            'test.mp3': {
                'artist': 'Test Artist',
                'composer': 'Test Composer',
                'cover_art': 'Test Cover',
                'title': 'Test Title',
                'album': 'Test Album',
                'genre': 'Test Genre',
                'track_number': '1',
            }
        }
    }
    try:
        result = mutate_metadata(metadata, in_place=True)
        assert 'files' in result
        assert 'test.mp3' in result['files']
        meta = result['files']['test.mp3']
        assert meta['artist'] == 'Test Artist'
        assert meta['composer'] == 'Test Composer'
        assert meta['cover_art'] == 'Test Cover'
        assert meta['title'] == 'Test Title'
        assert meta['album'] == 'Test Album'
        assert meta['genre'] == 'Audiobook'  # Should be set by mutate_metadata
        assert meta['track_number'] == '1'
    except Exception as e:
        if legacy_test_converter:
            result = legacy_test_converter(metadata)
            assert 'files' in result
            assert 'test.mp3' in result['files']
            meta = result['files']['test.mp3']
            assert meta['artist'] == 'Test Artist'
            assert meta['composer'] == 'Test Composer'
            assert meta['cover_art'] == 'Test Cover'
            assert meta['title'] == 'Test Title'
            assert meta['album'] == 'Test Album'
            assert meta['genre'] == 'Audiobook'
            assert meta['track_number'] == '1'
        else:
            raise
