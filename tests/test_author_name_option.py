import os

from audiobook_p import main as mainmod


def test_author_name_applies_artist_tag(tmp_path, monkeypatch):
    """Verify --author-name sets the per-file 'artist' metadata to the cleaned author name."""
    # Create source folder with 3 dummy files
    src_dir = tmp_path / "Source Book"
    src_dir.mkdir()

    src_files = []
    for i in range(1, 4):
        name = f"{i:02d} - Chapter {i}.m4a"
        p = src_dir / name
        p.write_text("")
        src_files.append(str(p))

    # Build a metadata_dict similar to extract_metadata_from_folder output
    files_map = {str(p): {} for p in src_files}
    metadata_dict = {
        'folder_type': 'novel',
        'folder': str(src_dir),
        'files': files_map
    }

    # Capture apply_metadata_to_file calls instead of actually using mutagen
    captured = []

    def fake_apply_metadata_to_file(file_path, metadata_dict):
        # store a shallow copy for inspection
        captured.append((str(file_path), dict(metadata_dict)))

    monkeypatch.setattr(mainmod, 'apply_metadata_to_file', fake_apply_metadata_to_file)

    # Use an author name with leading/trailing noise that should be cleaned
    author_input = '  01 john doe  '

    # Run mutate_metadata with author_name provided
    mutated = mainmod.mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=author_input)

    # Ensure mutated path exists
    assert os.path.isdir(mutated)

    # The cleaning logic uses book_title_logic which removes leading numeric prefixes and caps the first alpha
    # For '  01 john doe  ' we expect 'John doe' (first alpha capitalized, leading '01 ' removed)
    expected_artist = mainmod.book_title_logic(author_input).strip()

    # At minimum one metadata write should be captured; ensure all captured writes set the expected artist
    assert len(captured) >= 1, f"Expected at least one metadata write, got {len(captured)}"
    for (fp, md) in captured:
        assert md.get('artist') == expected_artist, f"Artist tag for {fp} expected {expected_artist}, got {md.get('artist')}"
