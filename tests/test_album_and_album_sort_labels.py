import os
import tempfile
import shutil
import pytest
from audiobook_p.mutation import mutate_metadata
from audiobook_p.utils import clean_album_name

def create_audio_file(path):
    with open(path, 'wb') as f:
        f.write(b'ID3')

def test_album_and_album_sort_novel_and_series_labels():
    temp_dir = tempfile.mkdtemp()
    try:
        # --- Novel case ---
        novel_name = "the great adventure"
        novel_dir = os.path.join(temp_dir, novel_name)
        os.makedirs(novel_dir)
        audio_path = os.path.join(novel_dir, 'chapter1.mp3')
        create_audio_file(audio_path)
        meta = {
            'folder': novel_dir,
            'files': {audio_path: {}}
        }
        result = mutate_metadata(meta)
        for f, m in result['files'].items():
            cleaned = clean_album_name(novel_name)
            assert m['album'] == cleaned
            assert m['album_sort'] == cleaned

        # --- Series case ---
        series_name = "epic saga"
        book_name = "the lost book"
        series_dir = os.path.join(temp_dir, series_name)
        book_dir = os.path.join(series_dir, book_name)
        os.makedirs(book_dir)
        audio_path = os.path.join(book_dir, 'chapter1.mp3')
        create_audio_file(audio_path)
        meta = {
            'folder': book_dir,
            'files': {audio_path: {}},
            'folder_type': 'series',
            'series_name': series_name
        }
        result = mutate_metadata(meta)
        for f, m in result['files'].items():
            cleaned_series = clean_album_name(series_name)
            cleaned_book = clean_album_name(book_name)
            assert m['album'] == cleaned_book
            assert m['album_sort'] == f"{cleaned_series} - {cleaned_book}"
    finally:
        shutil.rmtree(temp_dir)
