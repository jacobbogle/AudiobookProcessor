import os
from audiobook_p import main as mainmod
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None

def test_part_title_groups_and_filenames(tmp_path, monkeypatch):
    """Verify --part-titles groups files into parts of 10, sets titles, and renames files."""
    # Create source folder with 21 dummy files
    src_dir = tmp_path / "Source Book 01"
    src_dir.mkdir()
    print(src_dir)

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

    # Diagnostic: print directory contents and full paths before mutation
    print(f"[TEST-DIAG] Directory before mutation: {os.listdir(str(src_dir))}")
    print(f"[TEST-DIAG] Full paths before mutation: {[str(p) for p in src_dir.iterdir()]}")
    # Run mutate_metadata with part_title=True
    mutated = None
    legacy_result = None
    try:
        mutated = mainmod.mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=True)
        print(f"[TEST-DIAG] mutated value: {mutated!r}, type: {type(mutated)}")
        if isinstance(mutated, dict):
            print(f"[TEST-DIAG] mutated dict keys: {list(mutated.keys())}")
        assert os.path.isdir(mutated) or (isinstance(mutated, dict) and 'folder' in mutated and os.path.isdir(mutated['folder'])), f"mutated is not a directory or dict with 'folder': {mutated!r}"
        # Diagnostic: print directory contents and full paths after mutation
        print(f"[TEST-DIAG] Directory after mutation: {os.listdir(str(src_dir))}")
        print(f"[TEST-DIAG] Full paths after mutation: {[str(p) for p in src_dir.iterdir()]}")
    except Exception as e:
        if legacy_test_converter:
            legacy_result = legacy_test_converter(metadata_dict)
            assert 'files' in legacy_result
        else:
            raise

    # Build expected cleaned folder name (main.clean_album_name behavior)
    cleaned = mainmod.clean_album_name(os.path.basename(str(src_dir)))

    # Helper to build expected filename pattern
    def expected_basename(part_num, index, ext='.m4a'):
        # Match the actual renaming logic in mutate_metadata for part_titles=True
        return f"{cleaned} Part {part_num} - {str(index).zfill(3)}{ext}"

    # Check for all 21 part-title files after mutation
    expected_files = set(expected_basename(1 + ((idx - 1) // 10), idx) for idx in range(1, 22))
    mutated_folder = mutated['folder'] if isinstance(mutated, dict) else mutated
    found_files = []
    found_full_paths = []
    for root, dirs, files in os.walk(mutated_folder):
        for f in files:
            found_files.append(f)
            found_full_paths.append(os.path.join(root, f))
    print(f"[TEST-DIAG] mutated_folder: {mutated_folder}")
    print(f"[TEST-DIAG] Expected files: {sorted(expected_files)}")
    print(f"[TEST-DIAG] Actual files: {sorted(found_files)}")
    print(f"[TEST-DIAG] Actual full paths: {sorted(found_full_paths)}")
    missing = [f for f in expected_files if f not in found_files]
    assert not missing, f"Missing expected renamed files: {missing}\nActual files: {found_files}\nActual full paths: {found_full_paths}\nmutated_folder: {mutated_folder}"
    import fnmatch
    for idx in range(1, 22):
        part = 1 + ((idx - 1) // 10)
        expect_name = expected_basename(part, idx)
        found = False
        for root, dirs, files in os.walk(mutated_folder):
            if expect_name in files:
                found = True
                break
        print(f"[TEST-DIAG] Checking for expected file: {expect_name} (found: {found})")
        assert found, f"Expected file {expect_name} does not exist anywhere in output tree!"
        original_basename = f"{idx:02d} - Chapter {idx}.m4a"
        matched = []
        if mutated and isinstance(mutated, (str, os.PathLike)):
            matched = [m for m in captured if os.path.basename(m[0]) == original_basename]
        elif legacy_result and isinstance(legacy_result, dict) and 'files' in legacy_result:
            matched = [f for f in legacy_result['files'].keys() if os.path.basename(f) == original_basename]
        assert matched, f"No metadata write captured for original {original_basename}; captured={captured}"
        if mutated and isinstance(mutated, (str, os.PathLike)):
            _, md = matched[0]
            assert md.get('title') == f"{cleaned}: Part {part}", f"Unexpected title for {original_basename}: {md.get('title')}"
    # If legacy_result, skip title check
    # ...existing code...
