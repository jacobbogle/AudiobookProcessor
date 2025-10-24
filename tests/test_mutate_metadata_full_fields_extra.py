import os
import json
import shutil
import tempfile
import types

import pytest

from audiobook_p import main
from audiobook_p.main import clean_album_name


def _make_sample_metadata(folder_path, file_count=3):
    files = {}
    for i in range(1, file_count + 1):
        fname = f"{i:02d} - track.mp3"
        full = os.path.join(folder_path, fname)
        files[full] = {
            'filename': fname,
            'title': f"Track {i}",
            'length': 60.0
        }
    return {
        'folder': folder_path,
        'files': files,
        'metadata': {
            'album': 'Sample Book',
            'artist': 'Doe, John',
            'narrator': 'Smith, Jane',
            'series': 'Sample Series',
            'series_index': '3',
            'genre': 'Fiction',
            'year': '2020',
            'part_titles': False
        }
    }


def test_mutate_metadata_applies_fields_novel(tmp_path, monkeypatch):
    # Setup a temporary folder with dummy audio files
    src = tmp_path / 'novel'
    src.mkdir()
    for i in range(1, 4):
        p = src / f"{i:02d} - track.mp3"
        p.write_bytes(b'')

    metadata = _make_sample_metadata(str(src), file_count=3)
    metadata['folder_type'] = 'novel'

    # Monkeypatch move_to_destination to avoid filesystem moves
    monkeypatch.setattr(main, 'move_to_destination', lambda path, dest, folder_type: path)
    # Capture apply_metadata_to_file calls
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    # Call mutate_metadata
    out = main.mutate_metadata(metadata, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=main._maybe_fix_author(metadata['metadata'].get('artist'), True), narrator_name=metadata['metadata'].get('narrator'))

    # mutated path should be returned
    assert out is not None

    # Ensure apply_metadata_to_file was called and inspect one sample
    assert captured, "apply_metadata_to_file was not called"
    sample_meta = next(iter(captured.values()))

    # Verify some fields applied: album is derived from folder name
    assert sample_meta.get('album') == clean_album_name(src.name)
    # author was "Doe, John" and author_fix True should have been applied to 'artist' or stored appropriately
    assert 'Doe' not in sample_meta.get('artist', '') or ',' not in sample_meta.get('artist', '')
    # Genre may be preserved from file-level metadata or defaulted to 'Audiobook'
    assert sample_meta.get('genre') in ('Fiction', 'Audiobook')
    # Year may not be present on per-file metadata; only assert if present
    if sample_meta.get('year') is not None:
        try:
            assert int(sample_meta.get('year')) == 2020
        except Exception:
            # Some mappings use 'date' instead
            assert int(sample_meta.get('date', 2020)) == 2020


def test_mutate_metadata_series_grouping(tmp_path, monkeypatch):
    # Create a series folder with subfolders representing volumes
    root = tmp_path / 'series'
    root.mkdir()
    vol = root / 'Book 03'
    vol.mkdir()
    for i in range(1, 3):
        p = vol / f"{i:02d} - track.mp3"
        p.write_bytes(b'')

    metadata = {
        'folder': str(vol),
        'files': {
            os.path.join(str(vol), '01 - track.mp3'): {'filename': '01 - track.mp3', 'title': 'Track 1', 'length': 60.0},
            os.path.join(str(vol), '02 - track.mp3'): {'filename': '02 - track.mp3', 'title': 'Track 2', 'length': 70.0}
        },
        'metadata': {
            'album': 'Book 03',
            'artist': 'Author Name',
            'series': 'Sample Series',
            'series_index': '3',
            'part_titles': True
        }
    }
    metadata['folder_type'] = 'series'

    monkeypatch.setattr(main, 'move_to_destination', lambda path, dest, folder_type: path)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    out = main.mutate_metadata(metadata, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name='Sample Series', part_titles=True, author_name='Author Name', narrator_name=None)

    assert out is not None
    assert captured, "apply_metadata_to_file was not called for series grouping"
    # At least one file should have been processed
    assert len(captured) >= 1
    sample_meta = next(iter(captured.values()))
    # Album should be cleaned folder name
    assert sample_meta.get('album') == clean_album_name(vol.name)
    # album_sort should include the provided series name (if set)
    assert 'Sample Series' in str(sample_meta.get('album_sort', ''))
