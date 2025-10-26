import os
import tempfile
import shutil
import pytest
from audiobook_p.utils import detect_folder_type

def create_audio_file(path):
    with open(path, 'wb') as f:
        f.write(b'ID3')

def test_detect_folder_type_novel_and_series():
    temp_dir = tempfile.mkdtemp()
    try:
        # Novel: audio files directly in folder
        audio_path = os.path.join(temp_dir, 'chapter1.mp3')
        create_audio_file(audio_path)
        assert detect_folder_type(temp_dir) == 'novel'
        os.remove(audio_path)

        # Series: subfolders with audio files
        series_sub = os.path.join(temp_dir, 'Book 1')
        os.makedirs(series_sub)
        audio_path = os.path.join(series_sub, 'chapter1.mp3')
        create_audio_file(audio_path)
        assert detect_folder_type(temp_dir) == 'series'
        shutil.rmtree(series_sub)

        # Unknown: no audio files
        assert detect_folder_type(temp_dir) == 'unknown'
    finally:
        shutil.rmtree(temp_dir)
