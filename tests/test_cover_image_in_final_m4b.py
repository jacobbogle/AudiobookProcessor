import os
import shutil
import pytest
from mutagen.mp4 import MP4
from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, convert_folder_to_m4b

def test_cover_image_present_in_final_m4b(tmp_path):
    """End-to-end: ensure that a cover image is embedded in the final M4B file."""
    src = tmp_path / "CoverBook"
    os.makedirs(src, exist_ok=True)
    # Use the provided MP3 file
    provided_mp3 = r"C:\Users\Bogle\Documents\Dev\AudiobookProcessor.worktrees\burn-it\test_audio\valid\Eldest (100).mp3"
    if not os.path.exists(provided_mp3):
        pytest.skip("Provided MP3 file does not exist")
    shutil.copy(provided_mp3, os.path.join(src, '01 - Chapter One.mp3'))
    # Look for a cover image in the same directory as the MP3
    cover_jpg = os.path.join(os.path.dirname(provided_mp3), 'cover.jpg')
    if os.path.exists(cover_jpg):
        shutil.copy(cover_jpg, os.path.join(src, 'cover.jpg'))
    # Extract metadata and run mutation
    metadata = extract_metadata_from_folder(str(src), 'novel')
    mutated = mutate_metadata(metadata, in_place=False)
    # Accept both dict (legacy) and path return types
    if isinstance(mutated, dict):
        folder_path = mutated.get('folder')
        assert folder_path and os.path.isdir(folder_path), "Legacy mutate_metadata did not return a valid folder"
    else:
        folder_path = mutated
    out_m4b = str(tmp_path / 'out_with_cover.m4b')
    convert_folder_to_m4b(folder_path, out_m4b, chapter_titles=False, original_source_path=str(src))
    assert os.path.exists(out_m4b), "Output M4B file was not created"
    tags = MP4(out_m4b).tags
    assert tags is not None, "No tags found in output M4B"
    covr = tags.get('covr')
    assert covr and len(covr) > 0, "No cover image found in final M4B file (from cover.jpg or embedded in MP3)"
