import os
import shutil
import tempfile
from pathlib import Path
import json
import subprocess
from mutagen.mp4 import MP4

from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, convert_folder_to_m4b, clean_album_name


def write_short_mp3(path, duration=0.1):
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', str(duration), '-q:a', '9', path
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def read_m4b_tags(m4b_path):
    """Return a dict of MP4 tags using mutagen.mp4.MP4 for reliable atom access."""
    mp4 = MP4(m4b_path)
    tags = {}
    if mp4.tags:
        for k, v in mp4.tags.items():
            tags[k] = v
    return tags


import pytest


@pytest.mark.integration
def test_novel_end_to_end_album_and_sort(tmp_path):
    # create novel folder
    src = tmp_path / 'My Novel'
    src.mkdir()
    a = src / '01 - track.mp3'
    b = src / '02 - track.mp3'
    write_short_mp3(str(a))
    write_short_mp3(str(b))

    metadata = extract_metadata_from_folder(str(src), 'novel')
    mutated = mutate_metadata(metadata, in_place=False)
    out_m4b = str(tmp_path / 'novel_out.m4b')
    convert_folder_to_m4b(mutated, out_m4b, chapter_titles=False, album_names=True, original_source_path=str(src))

    tags = read_m4b_tags(out_m4b)
    cleaned = clean_album_name(src.name)
    # ffprobe returns tags in keys that may vary by container; check common keys
    # MP4 stores album in '\xa9alb' and album_sort in 'soal'
    alb = tags.get('\u00a9alb') or tags.get('©alb') or tags.get('album')
    album_sort = tags.get('soal') or tags.get('SOAL') or tags.get('album_sort')

    assert alb is not None
    assert cleaned.lower() in str(alb).lower()
    # For novel, album_sort should equal cleaned folder name (or contain it prominently)
    assert cleaned.lower() in str(album_sort).lower()

    shutil.rmtree(mutated, ignore_errors=True)


@pytest.mark.integration
def test_series_end_to_end_album_and_sort(tmp_path):
    parent = tmp_path / 'Series Parent'
    child = parent / '01 - Child Book'
    child.mkdir(parents=True, exist_ok=True)
    a = child / '01 - track.mp3'
    write_short_mp3(str(a))

    metadata = extract_metadata_from_folder(str(child), 'series')
    mutated = mutate_metadata(metadata, in_place=False, series_name=None)
    out_m4b = str(tmp_path / 'series_out.m4b')
    convert_folder_to_m4b(mutated, out_m4b, chapter_titles=False, album_names=True, original_source_path=str(child))

    tags = read_m4b_tags(out_m4b)
    cleaned_child = clean_album_name(child.name)
    cleaned_parent = clean_album_name(parent.name)

    alb = tags.get('\u00a9alb') or tags.get('©alb') or tags.get('album')
    album_sort = tags.get('soal') or tags.get('SOAL') or tags.get('album_sort')

    assert alb is not None
    assert cleaned_child.lower() in str(alb).lower()
    # For series, album_sort should include parent then child
    assert cleaned_parent.lower() in str(album_sort).lower()
    assert cleaned_child.lower() in str(album_sort).lower()

    shutil.rmtree(mutated, ignore_errors=True)
