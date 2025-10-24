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


def test_mutate_metadata_applies_many_fields_novel(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "FullNovel"
    _populate(str(src), repo_root)

    # Provide a rich metadata payload per file
    def fake_extract(path):
        return {
            'title': 'The Beginning',
            'artist': 'Narrator Name',
            'album': 'Full Novel',
            'genre': 'Fiction',
            'composer': 'Author Name',
            'date': '2020',
            'comment': 'A sample book',
            'cover_art': 'Present',
            'series_index': '',
            'track_number': '1/10'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    out = mutate_metadata(metadata, chapter_titles=True)

    assert captured
    md = next(iter(captured.values()))
    # Check key fields (album derived from folder name)
    cleaned_folder = clean_album_name(src.name)
    assert md.get('title').startswith(cleaned_folder) or 'Chapter' in md.get('title')
    assert md.get('artist') == 'Narrator Name'
    assert md.get('album') == cleaned_folder
    assert md.get('genre') == 'Fiction'
    assert md.get('composer') == 'Author Name'
    assert md.get('date') == '2020'
    assert md.get('comment') == 'A sample book' or md.get('comment') == 'A sample book'
    assert md.get('media_kind') == 2


def test_mutate_metadata_applies_many_fields_series(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    parent = tmp_path / 'SeriesParent'
    child = parent / '02 - The Middle'
    _populate(str(child), repo_root)

    def fake_extract(path):
        return {
            'title': 'The Middle',
            'artist': 'Narrator Two',
            'album': '02 - The Middle',
            'genre': 'Nonfiction',
            'composer': 'Author Two',
            'date': '2018',
            'comment': 'Series volume',
            'cover_art': 'Present',
            'series_index': '2',
            'track_number': '1/8'
        }

    monkeypatch.setattr('audiobook_p.main.extract_metadata_from_file', fake_extract)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    metadata = extract_metadata_from_folder(str(child), 'series')
    out = mutate_metadata(metadata, series_name=None, chapter_titles=False)

    assert captured
    md = next(iter(captured.values()))
    # For series, grouping should be parent (cleaned) and series_index applied
    assert md.get('grouping') == clean_album_name(parent.name) or md.get('grouping') == ''
    # Title may be filename-based when chapter_titles False
    assert isinstance(md.get('title'), str)
    assert md.get('artist') == 'Narrator Two'
    assert md.get('album') == clean_album_name(child.name)
    assert md.get('genre') == 'Nonfiction'
    assert md.get('composer') == 'Author Two'
    assert md.get('date') == '2018'
    assert md.get('comment') == 'Series volume'
    # series_index should be set to int or string representing 2
    assert str(md.get('series_index')) in ('2', '2.0', '2')
    # track should be present
    assert md.get('track') == '1'
    assert md.get('media_kind') == 2
