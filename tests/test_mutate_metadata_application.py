import os
import shutil

import pytest

from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, clean_album_name


def _populate_source_with_test_audio(src_dir, repo_root):
    """Copy the small test audio files from the repo test_audio into src_dir."""
    os.makedirs(src_dir, exist_ok=True)
    test_audio_dir = os.path.join(repo_root, 'test_audio')
    for name in ('test1.mp3', 'test2.mp3', 'test_short.m4a'):
        src = os.path.join(test_audio_dir, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(src_dir, name))


def test_mutate_metadata_novel_applies_changes(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    # Prepare a source folder that represents a single-novel folder
    src = tmp_path / "Source Novel"
    _populate_source_with_test_audio(str(src), repo_root)

    # Extract metadata from folder (folder_type 'novel')
    metadata = extract_metadata_from_folder(str(src), 'novel')

    # Capture calls to apply_metadata_to_file
    captured = {}

    def fake_apply(path, md):
        captured[path] = md

    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', fake_apply)

    # Run mutate_metadata with chapter_titles enabled (should update titles)
    out = mutate_metadata(metadata, chapter_titles=True)

    # Ensure apply_metadata_to_file was called for each source file
    assert captured, "apply_metadata_to_file was not called"

    cleaned = clean_album_name(src.name)

    # Check that for each captured metadata the album and album_sort were set correctly
    for path, md in captured.items():
        # album should be cleaned folder name
        assert md.get('album') == cleaned
        # album_sort should equal cleaned folder name for novels
        assert md.get('album_sort') == cleaned
    # title should be in the format '<Cleaned> - Chapter N'
        title = md.get('title')
        assert isinstance(title, str)
    assert title.startswith(f"{cleaned} - Chapter ") or title.startswith("Chapter ")


def test_mutate_metadata_series_applies_changes(tmp_path, monkeypatch):
    repo_root = os.path.dirname(os.path.dirname(__file__))
    # Create a parent folder and a child folder with numeric prefix
    parent = tmp_path / "My Series Parent"
    child = parent / "01 - The Beginning"
    os.makedirs(child, exist_ok=True)
    _populate_source_with_test_audio(str(child), repo_root)

    # Extract metadata for the child folder as a 'series' type
    metadata = extract_metadata_from_folder(str(child), 'series')

    # Capture calls to apply_metadata_to_file
    captured = {}

    def fake_apply(path, md):
        captured[path] = md

    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', fake_apply)

    # Run mutate_metadata for series (no explicit series_name provided)
    out = mutate_metadata(metadata, series_name=None)

    assert captured, "apply_metadata_to_file was not called for series"

    cleaned_parent = clean_album_name(parent.name)
    cleaned_child = clean_album_name(child.name)

    for path, md in captured.items():
        # For series, album should be child's cleaned name
        assert md.get('album') == cleaned_child
        # album_sort should include parent then child (prefix)
        album_sort = md.get('album_sort')
        assert isinstance(album_sort, str)
        assert album_sort.startswith(f"{cleaned_parent} - {cleaned_child}") or cleaned_parent in album_sort
        # grouping (series) should default to cleaned parent name (or be empty if not set)
        grouping = md.get('grouping')
        assert grouping == cleaned_parent or grouping == '' or grouping is None
        # title: when chapter_titles is not requested, title may be derived from filename or metadata
        title = md.get('title')
        assert isinstance(title, str) and title.strip() != ''

    # Now verify that requesting chapter_titles produces chapter-style titles
    captured2 = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured2.setdefault(p, m))
    out2 = mutate_metadata(metadata, series_name=None, chapter_titles=True)
    assert captured2, "apply_metadata_to_file was not called for series with chapter_titles=True"
    for path, md in captured2.items():
        title = md.get('title')
        assert isinstance(title, str)
        assert title.startswith(f"{cleaned_child} - Chapter ") or title.startswith("Chapter ")


def test_mutate_convert_chapter_title_from_folder_name(tmp_path, monkeypatch):
    """When chapter_titles is requested, folder name should be used for chapter prefix."""
    repo_root = os.path.dirname(os.path.dirname(__file__))
    src = tmp_path / "Inkheart"
    os.makedirs(src, exist_ok=True)
    # populate with one test audio file
    from audiobook_p.main import clean_album_name
    def _populate():
        test_audio_dir = os.path.join(repo_root, 'test_audio')
        src_file = os.path.join(test_audio_dir, 'test1.mp3')
        if os.path.exists(src_file):
            shutil.copy(src_file, os.path.join(src, '01 - Chapter One.mp3'))

    _populate()

    metadata = extract_metadata_from_folder(str(src), 'novel')

    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    out = mutate_metadata(metadata, chapter_titles=True)

    assert captured, "apply_metadata_to_file was not called"
    # There should be exactly one file processed
    md = next(iter(captured.values()))
    title = md.get('title')
    assert title == f"{clean_album_name('Inkheart')} - Chapter 1"
