import os
import tempfile
import shutil
import pytest
from audiobook_p.utils import detect_folder_type

def create_audio_file(path):
    with open(path, 'wb') as f:
        f.write(b'ID3')

def test_detect_folder_type_labels_for_subfolders():
    temp_dir = tempfile.mkdtemp()
    try:
        # Create a direct audio file (should be novel)
        audio_path = os.path.join(temp_dir, 'chapter1.mp3')
        create_audio_file(audio_path)
        assert detect_folder_type(temp_dir) == 'novel'

        # Create subfolders with audio files (should be series)
        sub1 = os.path.join(temp_dir, 'Book 1')
        sub2 = os.path.join(temp_dir, 'Book 2')
        os.makedirs(sub1)
        os.makedirs(sub2)
        create_audio_file(os.path.join(sub1, 'ch1.mp3'))
        create_audio_file(os.path.join(sub2, 'ch1.mp3'))
        # Now the parent should be series
        assert detect_folder_type(temp_dir) == 'series'
        # And the subfolders themselves should be novel
        assert detect_folder_type(sub1) == 'novel'
        assert detect_folder_type(sub2) == 'novel'
    finally:
        shutil.rmtree(temp_dir)
