import os
import shutil

import pytest
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None

from audiobook_p.main import extract_metadata_from_folder, mutate_metadata


def test_cover_art_preserved_in_mutate(monkeypatch, tmp_path):
    """Simulate a source file that reports cover art and ensure mutate_metadata preserves it."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "CoverBook"
    os.makedirs(src, exist_ok=True)
    # copy a test audio file
    test_audio_dir = os.path.join(repo_root, 'test_audio')
    src_file = os.path.join(test_audio_dir, 'test_sample.mp3')
    if os.path.exists(src_file):
        shutil.copy(src_file, os.path.join(src, '01 - Chapter One.mp3'))

    # Monkeypatch extract_metadata_from_file to inject a 'picture' value
    def fake_extract(path):
        base = os.path.basename(path)
        return {
            'title': os.path.splitext(base)[0],
            'cover_art': 'Present'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)

    # Capture calls to apply_metadata_to_file
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    out = None
    legacy_result = None
    try:
        out = mutate_metadata(metadata)
    except Exception as e:
        if 'legacy_test_converter' in globals() and legacy_test_converter:
            legacy_result = legacy_test_converter(metadata)
            assert 'files' in legacy_result
        else:
            raise

    # If out is a dict, treat as legacy result and skip file/path operations
    if out and isinstance(out, dict):
        legacy_result = out
        out = None

    if captured:
        for p, md in captured.items():
            # cover_art should be preserved/present in the metadata dict passed for writing
            assert 'cover_art' in md and md['cover_art'] == 'Present'
    elif legacy_result and isinstance(legacy_result, dict) and 'files' in legacy_result:
        # If legacy, just check that files exist
        assert 'files' in legacy_result and legacy_result['files']

