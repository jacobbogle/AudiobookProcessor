import os
import shutil

import pytest

from audiobook_p.main import extract_metadata_from_folder, mutate_metadata


def test_cover_art_preserved_in_mutate(monkeypatch, tmp_path):
    """Simulate a source file that reports cover art and ensure mutate_metadata preserves it."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "CoverBook"
    os.makedirs(src, exist_ok=True)
    # copy a test audio file
    test_audio_dir = os.path.join(repo_root, 'test_audio')
    src_file = os.path.join(test_audio_dir, 'test1.mp3')
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
    out = mutate_metadata(metadata)

    assert captured, "apply_metadata_to_file was not called"
    for p, md in captured.items():
        # cover_art should be preserved/present in the metadata dict passed for writing
        assert 'cover_art' in md and md['cover_art'] == 'Present'

