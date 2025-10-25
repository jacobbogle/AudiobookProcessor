# Dataflow Simplification & Effectiveness Plan

This file proposes changes to make the AudiobookProcessor project more effective and simpler, while ensuring all desired outputs and test coverage are maintained.

---

## General Principles
- Minimize redundant data transformations and file copies
- Use clear, single-responsibility functions for each stage (extract, mutate, convert, post-process)
- Standardize return types (always dicts with keys: folder, files, metadata) for all core functions
- Centralize option handling (album_sort_prefix, author_fix, part_titles, narrator_name) in one place
- Use helper modules (e.g., m4b_edit.py) for post-processing, not in main dataflow
- Ensure CLI and API entrypoints are thin wrappers over core logic
- Prefer pure functions for metadata extraction and mutation; side-effects only in conversion/post-processing

---

## Proposed Code Changes
1. **Standardize Function Outputs**
   - Ensure all core functions (`extract_metadata_from_folder`, `mutate_metadata`, `convert_folder_to_m4b`) return dicts with predictable keys
   - Remove legacy path-only returns; always return dicts for easier chaining and testing

2. **Centralize Option Handling**
   - Move all option logic (album_sort_prefix, author_fix, part_titles, narrator_name) into a single function or config object
   - Pass options as a dict or dataclass to all core functions

3. **Simplify CLI/argparse Layer**
   - Use a single CLI entrypoint that dispatches to mode functions
   - Validate and normalize CLI args before passing to core logic

4. **Refactor Mutation Logic**
   - Make `mutate_metadata` a pure function: takes metadata dict, options dict, returns mutated dict
   - Move file copying and renaming to a separate utility function

5. **Improve Conversion & Post-processing**
   - Ensure `convert_folder_to_m4b` only handles conversion, not metadata mutation
   - Use `m4b_edit.py` for any tag/cover edits after conversion
   - Add error handling and diagnostics for ffmpeg failures

6. **Helper Functions**
   - Restore and export all helpers (e.g., `parse_metadata_to_python_safe`) in a dedicated helpers module
   - Document contracts and edge cases for each helper

7. **Test Suite Improvements**
   - Update tests to expect dict outputs from all core functions
   - Remove tests that depend on legacy path-only returns
   - Add tests for option edge cases and error handling
   - Use fixtures for common test data and file setup
   - Add integration tests for full dataflow (extract → mutate → convert → post-process)

---

## Specific Test Changes Needed
- Update tests to expect dicts with `folder`, `files`, and `metadata` keys from all core functions
- Refactor tests that expect only a path to use the dict and access the folder via `result['folder']`
- Add/expand tests for:
  - Option combinations (album_sort_prefix + author_fix, etc.)
  - ffmpeg error handling and diagnostics
  - Tag and cover art preservation after conversion
- Remove or update tests that depend on legacy side-effects or return types
- Use pytest fixtures for file/folder setup and teardown

---

## Desired Output & Simplicity
- All modes and options produce predictable, testable outputs
- Dataflow is linear and easy to trace: extract → mutate → convert → post-process
- Tests validate both intermediate and final outputs
- Codebase is modular, maintainable, and easy to extend

---

## Next Steps
1. Refactor core functions for standardized outputs
2. Centralize and simplify option handling
3. Update CLI and test suite for new dataflow
4. Validate with full pytest run and fix any remaining edge cases
