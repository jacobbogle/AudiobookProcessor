# Test Suite To-Do List by Dataflow Area

This file lists, for each entry in the Simple Reference Todo List (from `dataflow_detailed_todo.md`), the relevant pytest tests that should be run for that area and all preceding areas. Use this to run and validate tests as you complete each refactor step.

---

## CLI/Argparse
**Relevant Tests:**
- `tests/test_album_names_flag.py`
- `tests/test_author_fix_cli.py`
- `tests/test_author_name_option.py`
- `tests/temp-test.py` (CLI smoke tests)
- Any test that invokes CLI entrypoints or parses CLI args

## Extraction
**Relevant Tests (run these + CLI/Argparse):**
- `tests/test_metadata_extraction.py`
- `tests/test_metadata_parsing.py`
- `tests/test_metadata_mapping.py`
- `tests/test_title_capitalization.py`
- `tests/test_title_capitalization_from_metadata.py`
- Any test that calls `extract_metadata_from_folder` or `extract_metadata_from_file`

## Mutation
**Relevant Tests (run these + Extraction + CLI/Argparse):**
- `tests/test_mutate_metadata_application.py`
- `tests/test_mutate_metadata_full_fields.py`
- `tests/test_mutate_metadata_full_fields_extra.py`
- `tests/test_mutate_metadata_full_fields_extra2.py`
- `tests/test_mutate_metadata_full_fields_extra3.py`
- `tests/test_mutate_convert_tags.py`
- `tests/test_mutate_convert_series_vs_novel.py`
- `tests/test_part_titles_behavior.py`
- `tests/test_narrator_name_option.py`
- Any test that calls `mutate_metadata` or `cmd_mutate_convert`

## Conversion
**Relevant Tests (run these + Mutation + Extraction + CLI/Argparse):**
- `tests/test_integration.py`
- `tests/test_integration_m4b_chapters.py`
- `tests/test_cover_copy_integration.py`
- `tests/test_cover_preservation.py`
- `tests/test_ffmpeg_inject_chapters.py`
- `tests/test_final_album_tags_integration.py`
- Any test that calls `convert_folder_to_m4b` or validates M4B output

## Post-processing
**Relevant Tests (run these + Conversion + Mutation + Extraction + CLI/Argparse):**
- `tests/test_m4b_metadata.py`
- `tests/test_metadata_sanitizer.py`
- Any test that checks tag/cover preservation or uses `m4b_edit.py`

## Helpers
**Relevant Tests (run these + all previous):**
- `tests/test_chapter_parsing.py`
- `tests/test_chapter_rendering.py`
- Any test that calls helper functions (e.g., `parse_series_index_from_folder_name`, `sanitize_string`)

## Test Suite
**Run all tests above.**
- Add/expand integration tests as needed
- Remove/update legacy tests
- Use fixtures for setup/teardown

## Final Review
**Run all tests above.**
- Compare outputs to legacy
- Document differences
- Update code/tests for compatibility

---

**Usage:**
- When working on a todo entry, run all tests listed for that entry and all previous entries to validate correctness and compatibility.
- Update this file as new tests are added or test coverage changes.
