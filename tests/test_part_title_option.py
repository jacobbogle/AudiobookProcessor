import os

from audiobook_p import main as mainmod


def test_part_title_groups_and_filenames(tmp_path, monkeypatch):
    """Verify --part-titles groups files into parts of 10, sets titles, and renames files."""
    # Create source folder with 21 dummy files
    src_dir = tmp_path / "Source Book 01"
    src_dir.mkdir()

    src_files = []
    for i in range(1, 22):
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

    # Run mutate_metadata with part_title=True
    mutated = mainmod.mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=True)

    # Ensure mutated path exists
    assert os.path.isdir(mutated)

    # Build expected cleaned folder name (main.clean_album_name behavior)
    cleaned = mainmod.clean_album_name(os.path.basename(str(src_dir)))

    # Helper to build expected filename pattern
    def expected_basename(part_num, index, ext='.m4a'):
        return f"{cleaned}: Part {part_num} - {str(index).zfill(3)}{ext}"

    # Check for files and metadata for indices 1,10,11,20,21
    checks = [1, 10, 11, 20, 21]
    temp_listing = os.listdir(mutated)
    for idx in checks:
        part = 1 + ((idx - 1) // 10)
        expect_name = expected_basename(part, idx)
        assert expect_name in temp_listing, f"Expected renamed file {expect_name} in mutated folder, found: {temp_listing}"

    # Find captured metadata call for that file. Note: apply_metadata_to_file
    # is called before the file is renamed, so match by the original
    # basename (e.g., '01 - Chapter 1.m4a').
    original_basename = f"{idx:02d} - Chapter {idx}.m4a"
    matched = [m for m in captured if os.path.basename(m[0]) == original_basename]
    assert matched, f"No metadata write captured for original {original_basename}; captured={captured}"
    # metadata title should equal '<Cleaned>: Part N'
    _, md = matched[0]
    assert md.get('title') == f"{cleaned}: Part {part}", f"Unexpected title for {original_basename}: {md.get('title')}"
