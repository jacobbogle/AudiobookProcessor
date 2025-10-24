import os
import tempfile
import shutil

from audiobook_p import main


def test_series_folder_cleaning_applies_cleaned_names(tmp_path, monkeypatch):
    # Create nested series structure: ./library/night lords/ the throne of lies/
    root = tmp_path / 'library'
    series_parent = root / 'night lords'
    series_parent.mkdir(parents=True)
    series_folder = series_parent / ' the throne of lies'
    series_folder.mkdir()

    # Create dummy audio files
    for i in range(1, 3):
        p = series_folder / f"{i:02d} - track.mp3"
        p.write_bytes(b'')

    # Build metadata dict expected by mutate_metadata (files keys should be full paths)
    files = {}
    for i in range(1, 3):
        fname = f"{i:02d} - track.mp3"
        full = os.path.join(str(series_folder), fname)
        files[full] = {
            'filename': fname,
            'title': f"Track {i}",
            'length': 60.0
        }

    metadata = {
        'folder': str(series_folder),
        'files': files
    }
    metadata['folder_type'] = 'series'

    # Monkeypatch move_to_destination to avoid filesystem moves
    monkeypatch.setattr(main, 'move_to_destination', lambda path, dest, folder_type: path)
    captured = {}
    monkeypatch.setattr('audiobook_p.main.apply_metadata_to_file', lambda p, m: captured.setdefault(p, m))

    out = main.mutate_metadata(metadata, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=None, narrator_name=None, author_fix=False, in_place=True)

    assert captured, "apply_metadata_to_file was not called"
    sample_meta = next(iter(captured.values()))

    # cleaned parent should be Title Cased "Night Lords"
    assert sample_meta.get('album_sort') is not None
    assert 'Night Lords' in sample_meta.get('album_sort')
    # cleaned folder name should be Title Cased "The Throne Of Lies" (clean_album_name uses .title())
    assert sample_meta.get('album') == main.clean_album_name(' the throne of lies')
    # grouping should default to cleaned_parent_name when series_name not provided
    assert sample_meta.get('grouping') == main.clean_album_name('night lords')
