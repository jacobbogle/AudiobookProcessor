# Dataflow Comparison: Current vs Legacy

## Legacy Dataflow (from .md docs)
- Modes: extract, mutate, convert, mutate-convert
- Dataflow:
  1. CLI parses args, determines mode
  2. For extract: `cmd_extract` → `extract_metadata_from_folder`/`extract_metadata_from_file` → print JSON
  3. For mutate: `mutate_metadata` → copies files, normalizes tags, applies per-file metadata
  4. For convert: `convert_folder_to_m4b` → ffmpeg, chapters, add_audiobook_metadata
  5. For mutate-convert: orchestrates extract → mutate → convert → move
- Options: album_sort_prefix, author_fix, part_titles, narrator_name, etc. handled in mutate/convert
- Output: Dicts with metadata, folders, files, and final M4B

## Current Dataflow (project state)
- Modes: extract, mutate, convert, mutate-convert (all present)
- Dataflow:
  1. CLI parses args, determines mode
  2. For extract: `extract_metadata_from_folder`/`extract_metadata_from_file` (unchanged)
  3. For mutate: `mutate_metadata` (returns dict, but some tests expect path)
  4. For convert: `convert_folder_to_m4b` (unchanged, but some ffmpeg errors)
  5. For mutate-convert: orchestration restored, returns dict, uses mutated['folder'] for conversion
- Options: All present, but some edge cases (album_sort, author_fix, part_titles) may not match legacy output
- Output: Dicts with metadata, folders, files, and final M4B (restored)

## Key Differences
- Some tests expect different return types (dict vs path)
- Edge case handling for options (album_sort, author_fix, part_titles) may differ
- ffmpeg integration and error handling may differ
- Some helper functions (e.g., parse_metadata_to_python_safe) missing or not exported

---
# TODO: Dataflow Restoration Tasks (Modes & Options)

1. Ensure all mode entrypoints (`cmd_extract`, `mutate_metadata`, `convert_folder_to_m4b`, `cmd_mutate_convert`) return expected types for tests
2. Restore/implement missing helper functions (e.g., `parse_metadata_to_python_safe`) and export from main.py
3. Audit and fix option handling:
   - album_sort_prefix: ensure correct prefixing in album_sort
   - author_fix: ensure author names are normalized everywhere
   - part_titles: ensure files are grouped/renamed as expected
   - narrator_name: ensure composer tag is set correctly
4. Fix ffmpeg integration and error handling in `convert_folder_to_m4b` for test environments
5. Ensure all tags (title, album, album_sort, track, genre, media_kind, etc.) are set and mutated as described in TAGS_CHANGED_DETAILED.md
6. Re-run and debug all mutate-convert and option-related tests until passing
7. Document any remaining differences and update the code or tests for full compatibility

---
# Task List (in Dataflow Order)
1. CLI/argparse: Validate mode/option parsing
2. Metadata extraction: Ensure `extract_metadata_from_folder`/`extract_metadata_from_file` match legacy output
3. Mutation: Ensure `mutate_metadata` returns dict, applies all options, and matches legacy tag logic
4. Conversion: Ensure `convert_folder_to_m4b` works for all folder types, handles errors, and calls `add_audiobook_metadata`
5. Post-processing: Ensure tags and cover art are preserved/merged as described
6. Helper functions: Restore and export any missing helpers (e.g., `parse_metadata_to_python_safe`)
7. Test suite: Run all pytest tests, fix failures, and validate outputs
8. Final review: Compare outputs to legacy, document any remaining gaps
