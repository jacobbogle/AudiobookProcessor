# Dataflow Restoration Task List

This file lists the tasks required to restore full legacy-compatible dataflow for all modes and options, ensuring all pytest tests pass and both modes/options function as expected.

---

## Tasks (Ordered by Dataflow)

1. **CLI/argparse**
   - Validate mode and option parsing matches legacy behavior
   - Ensure all CLI flags/options are handled and passed to downstream functions

2. **Metadata Extraction**
   - Ensure `extract_metadata_from_folder` and `extract_metadata_from_file` produce dicts matching legacy output
   - Fix any discrepancies in extracted keys, normalization, or error handling

3. **Mutation**
   - Ensure `mutate_metadata` returns a dict with `folder` and `files` keys
   - Apply all options (album_sort_prefix, author_fix, part_titles, narrator_name) as described in .md docs
   - Match legacy tag logic for all fields (title, album, album_sort, track, genre, media_kind, etc.)

4. **Conversion**
   - Ensure `convert_folder_to_m4b` works for all folder types and options
   - Fix ffmpeg integration and error handling for test environments
   - Ensure chapters and tags are written as described

5. **Post-processing**
   - Ensure `add_audiobook_metadata` merges tags and cover art as described
   - Use `m4b_edit.py` for any additional tag editing if needed

6. **Helper Functions**
   - Restore and export any missing helpers (e.g., `parse_metadata_to_python_safe`) from main.py
   - Ensure all helpers match legacy contracts and signatures

7. **Test Suite**
   - Run all pytest tests, fix failures, and validate outputs
   - Debug edge cases for options and modes until all tests pass

8. **Final Review**
   - Compare outputs to legacy version
   - Document any remaining differences and update code/tests for full compatibility

---

## Notes
- Reference `MODE_FLOW.md`, `FUNCTIONS.md`, `SEARCH_RETURN_FLOW.md`, and `TAGS_CHANGED_DETAILED.md` for expected dataflow and tag logic.
- Prioritize fixing type mismatches, option edge cases, and missing helpers before deep ffmpeg integration issues.
- Use the comparison file (`dataflow_comparison_todo.md`) to track progress and remaining gaps.
