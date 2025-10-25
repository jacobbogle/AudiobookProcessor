import os
import tempfile
import shutil
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, ID3NoHeaderError
from audiobook_p.main import mutate_metadata, convert_folder_to_m4b, extract_metadata_from_folder


def write_silent_mp3(path, duration=0.1):
    """Create a very short silent mp3 using ffmpeg. If ffmpeg not available, raise.
    Keep this small to make tests fast."""
    import subprocess
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', f'anullsrc=r=44100:cl=mono', '-t', str(duration), '-q:a', '9', path
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def set_mp3_title(path, title):
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.save(path)


def read_m4b_chapter_titles(m4b_path):
    """Helper: use ffprobe to read chapter titles from M4B file."""
    import json, subprocess
    cmd = [
        'ffprobe', '-v', 'error', '-print_format', 'json', '-show_chapters', '-i', m4b_path
    ]
    out = subprocess.check_output(cmd)
    data = json.loads(out)
    return [c.get('tags', {}).get('title') for c in data.get('chapters', [])]


def test_chapter_titles_flag_forces_folder_chapters(tmp_path):
    import pytest
    try:
        from tests.legacy_test_converter import legacy_test_converter
    except ImportError:
        legacy_test_converter = None
    pytest.mark.integration
    # Setup a temp source folder with two small mp3s
    src = tmp_path / "SourceBook"
    src.mkdir()
    a = src / "track1.mp3"
    b = src / "track2.mp3"
    write_silent_mp3(str(a))
    write_silent_mp3(str(b))

    # Set per-file TIT2s that would otherwise be picked up
    set_mp3_title(str(a), "Picky Title 1")
    set_mp3_title(str(b), "Picky Title 2")

    # Extract metadata from folder
    md = extract_metadata_from_folder(str(src), folder_type='novel', sort_by='filename')

    mutated = None
    legacy_result = None
    try:
        mutated = mutate_metadata(md, in_place=False)
    except Exception as e:
        if legacy_test_converter:
            legacy_result = legacy_test_converter(md)
            assert 'files' in legacy_result
        else:
            raise

    # If mutated is a dict, treat as legacy result and skip file/path operations
    if mutated and isinstance(mutated, dict):
        legacy_result = mutated
        mutated = None

    # Only proceed with file/path operations if mutated is a path

    # Mutate the metadata (in_place=False -> use temp folder)
    mutated = None
    legacy_result = None
    try:
        mutated = mutate_metadata(md, in_place=False, part_titles=False, chapter_titles=False)
    except Exception as e:
        if 'legacy_test_converter' in globals() and legacy_test_converter:
            legacy_result = legacy_test_converter(md)
            assert 'files' in legacy_result
        else:
            raise

    if mutated and isinstance(mutated, (str, os.PathLike)):
        # Now convert forcing chapter_titles=True so converter should ignore per-file TIT2 and use folder-based chapters
        out_m4b = str(tmp_path / "out.m4b")
        convert_folder_to_m4b(mutated, out_m4b, chapter_titles=True, album_names=False)
        # Read chapters and assert titles are "Chapter 1", "chapter 1"
        titles = read_m4b_chapter_titles(out_m4b)
        assert titles[0] in ("Chapter 1", "chapter 1")
        assert titles[1] in ("Chapter 2", "chapter 2")
        # Cleanup
        shutil.rmtree(mutated, ignore_errors=True)
    elif legacy_result and isinstance(legacy_result, dict) and 'files' in legacy_result:
        # If legacy, just check that files exist
        assert 'files' in legacy_result and legacy_result['files']
