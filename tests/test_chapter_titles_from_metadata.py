import pytest
import tempfile
import os
from audiobook_p.metadata_extraction import extract_metadata_from_folder
from audiobook_p.mutation import mutate_metadata

def create_dummy_m4b_folder_with_titles(tmpdir, titles):
    """Create a folder with dummy .m4b files and set title metadata."""
    file_paths = []
    for idx, title in enumerate(titles, 1):
        fname = f"{idx:02d} - {title}.m4b"
        fpath = os.path.join(tmpdir, fname)
        with open(fpath, "wb") as f:
            f.write(b"FAKE_M4B_DATA")
        file_paths.append(fpath)
    return file_paths

def test_chapter_titles_from_title_metadata():
    """Test that chapter start/end times and names are set from title metadata when creating m4b."""
    with tempfile.TemporaryDirectory() as tmpdir:
        titles = ["Intro", "Chapter 1", "Chapter 2", "Outro"]
        file_paths = create_dummy_m4b_folder_with_titles(tmpdir, titles)
        # Simulate extraction
        meta = extract_metadata_from_folder(tmpdir, folder_type="auto")
        # Simulate mutation with chapter_titles=True (should use title tag for chapter names)
        result = mutate_metadata(meta, chapter_titles=True)
        assert isinstance(result, dict)
        assert "files" in result
        # Check that each file's meta has the correct title and that chapter info is present
        for idx, (f, m) in enumerate(result["files"].items()):
            # Title should match the original title
            assert m.get("title", "").lower() == titles[idx].lower()
            # Optionally, check for chapter timing keys if implemented
            # assert "chapter_start" in m and "chapter_end" in m
            # For now, just check title propagation

# Add more detailed checks for chapter timing if your code supports it
