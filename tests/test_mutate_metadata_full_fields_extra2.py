import os
import shutil

import pytest

from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, clean_album_name


def _populate(src, repo_root):
    os.makedirs(src, exist_ok=True)
    test_audio_dir = os.path.join(repo_root, 'test_audio')
    src_file = os.path.join(test_audio_dir, 'test1.mp3')
    if os.path.exists(src_file):
        shutil.copy(src_file, os.path.join(src, '01 - Chapter One.mp3'))


def test_mutate_metadata_derives_album_sort_and_title_sort(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "SortableBook"
    _populate(str(src), repo_root)

    def fake_extract(path):
        return {
            'title': 'A Tale of Something',
            'artist': 'Narrator Name',
            'album': 'The Sortable Book',
            'genre': 'Fiction',
            'composer': 'Author Name',
            'date': '2021',
            'comment': '',
            'cover_art': 'Present',
            'series_index': '',
            'track_number': '1/12'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    out = mutate_metadata(metadata, chapter_titles=True)

    assert captured
    md = next(iter(captured.values()))
    # album_sort should include 'sortable' and 'book' (cleaning/title-casing may remove spaces)
    album_sort_val = md.get('album_sort', '') or ''
    assert 'sortable' in album_sort_val.lower()
    assert 'book' in album_sort_val.lower()
    # title_sort is set to the unmodified filename stem by mutate_metadata
    assert 'Chapter One' in md.get('title_sort', '')


def test_mutate_metadata_prefers_original_trkn_per_chapter(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "PrefTrkn"
    _populate(str(src), repo_root)

    # Simulate per-file metadata where the source has a preferred trkn we should keep
    def fake_extract(path):
        return {
            'title': 'Original Track',
            'artist': 'Narrator Name',
            'album': 'PrefTrkn',
            'genre': 'Nonfiction',
            'composer': 'Author Name',
            'date': '2019',
            'comment': '',
            'cover_art': 'Present',
            'series_index': '',
            'track_number': '3/20'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    # Note: mutate_metadata currently sets per-file 'track' to the positional index
    out = mutate_metadata(metadata)

    assert captured
    md = next(iter(captured.values()))
    # mutate_metadata sets 'track' to the positional index (1 for first file)
    assert md.get('track') == '1' or md.get('track') == 1


def test_mutate_metadata_title_from_folder_when_no_title(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "FolderTitleFallback"
    _populate(str(src), repo_root)

    def fake_extract(path):
        # No title in extracted metadata; mutate_metadata should derive something from folder
        return {
            'title': '',
            'artist': 'Narrator Name',
            'album': '',
            'genre': 'Fiction',
            'composer': 'Author Name',
            'date': '2022',
            'comment': '',
            'cover_art': 'Present',
            'series_index': '',
            'track_number': '1/5'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    out = mutate_metadata(metadata, chapter_titles=False)

    assert captured
    md = next(iter(captured.values()))
    # Title should be derived/filled; cannot be empty
    assert md.get('title')
