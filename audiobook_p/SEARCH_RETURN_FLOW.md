# Search / Return Data Flow Analysis

This document describes the data flow for processing `series` and `novel` folders in the AudiobookProcessor repository. It focuses on the path taken when folders are "searched" / discovered and then processed (mutated and converted), highlighting key functions, data shapes, decision points, and side-effects.

The goal is to make it easy for developers to understand where metadata comes from, how it's transformed, and where potential bugs (e.g., trkn overwrites or cover-art loss) can be introduced.

---

## High-level overview

There are two primary folder types handled by the tool:

- `novel` — a single folder that directly contains audio files (e.g., a single audiobook).
- `series` — a parent folder that contains multiple child folders each representing a volume/book in a series.

The main processing pipeline has these high-level stages:

1. Discovery & classification (what kind of folder is this?)
   - `analyze_folder_structure`, `series_verify`, `batch_verify` (if available) are used to detect `novel` vs `series` folders.
2. Metadata extraction from source files
   - `extract_metadata_from_folder` -> uses `mutagen.File` via `extract_metadata_from_file` to collect descriptive metadata per file.
3. Mutation
   - `mutate_metadata` transforms metadata per-file (title formatting, album/album_sort/grouping, series_index inference, etc.) and copies files into a temporary mutated folder.
4. Conversion
   - `convert_folder_to_m4b` concatenates files with `ffmpeg`, writes chapters metadata, produces an interim M4B, and calls `add_audiobook_metadata` to add/merge final tags and cover art.
5. Finalization
   - `move_to_destination` moves the produced M4B (or mutated folder) to final location.

---

## Key functions and their roles (call graph)

- cli -> cmd_mutate / cmd_convert / cmd_mutate_convert
  - cmd_mutate
    - extract_metadata_from_folder
      - extract_metadata_from_file
        - mutagen.File(file_path)
      - Returns per-file dictionary of descriptive keys
    - mutate_metadata
      - copy files to temp
      - Apply `book_title_logic` to titles
      - infer/assign `album`, `album_sort`, `grouping`, `series_index`
      - call `apply_metadata_to_file` for each temp file
        - uses `reformat_tag_for_file_type` to format values for MP4/ID3
        - writes MP4 tags / ID3 frames via `mutagen` objects
  - cmd_convert
    - convert_folder_to_m4b
      - gather files
      - sort files (filename / track) using `track_number_sort_key`
      - synthesize ffmetadata chapters file
      - call ffmpeg to produce M4B
      - add chapters via mutagen (MP4Chapters)
      - call add_audiobook_metadata to copy/merge metadata and cover art
  - cmd_mutate_convert orchestrates mutate -> convert -> move flow

- add_audiobook_metadata(m4b_path, source_files, original_source_files=None, series_name=None)
  - Loads MP4 object and mapping JSON
  - Attempts to preserve or prefer original cover art from `original_source_files`
  - Copies text metadata from `first_audio` with reformatting
  - Pre-seeds `trkn` using `_determine_track_value_for_sources(source_files, MutagenFile)`
  - Applies grouping (`\xa9grp`) and mirrors to freeform `----:com.apple.iTunes:SERIES`
  - Ensures `sonm` (title_sort) uses uncleaned filename stem
  - Infers and sets `tvsn` from folder names
  - Uses `track_written` guard so helper-derived `trkn` is preserved

---

## Data shapes

- Per-file metadata (returned from `extract_metadata_from_file`):
  - Dict keyed by descriptive fields (e.g., `title`, `track_number`, `picture`, `grouping`, `series_index`)
  - Values are Python types (str, int, bytes, 'Present' marker for images)

- Mapping: `combined-metadata-mapping.json`
  - Each descriptive field maps to mutagen keys and data_types for `mp4` and `id3` targets.

- MP4 tags (mutagen MP4Tags):
  - Key -> value pairs where values are usually lists, e.g.:
    - `'\xa9nam'`: ['Book Title']
    - `'trkn'`: [(1, 10)]
    - `'covr'`: [MP4Cover(bytes, format)]
    - `'----:com.apple.iTunes:SERIES'`: [b'Series Name']

- MP3/ID3 frames (mutagen ID3):
  - Keys like 'TRCK', 'APIC:*', 'TIT1' with frame objects exposing `.text` or `.data`.

---

## Decision points, fallbacks and precedence rules

1. Determining folder type (novel vs series)
   - If folder directly contains audio files and no subfolders -> `novel`.
   - If contains subfolders -> `series` or batch; fallback heuristics use `series_verify`, `batch_verify`, or `analyze_folder_structure`.

2. Choosing metadata source for final M4B
   - For text metadata: prefer mutated post-mutation files (i.e., `source_files[0]`) so `mutate_metadata` changes are applied.
   - For cover art: prefer `original_source_files` (unmutated originals) to avoid recompression and preserve APIC raw bytes.

3. Track number (`trkn`) precedence
   - Pre-seed from helper `_determine_track_value_for_sources`, which uses (in order):
     1) MP4 `'trkn'` on first source
     2) ID3-like `TRCK` parsing on first source
     3) Index fallback -> (index+1, total)
   - `track_written` is set to True when value came from source metadata; subsequent writes to `'trkn'`/`'disk'` are skipped when `track_written` True.
   - Final safety-net only applies when `track_written` False (copy from first source or default to (1, total)).

4. Series index (`tvsn`) precedence
   - Prefer numeric prefix parsed from original folder name (original_source_files) then from mutated source folder; finally try sibling inference.

5. Grouping/Series freeform
   - `grouping` -> sets `\xa9grp` and mirrors to `----:com.apple.iTunes:SERIES` to maximize compatibility with Apple tooling.

---

## Where bugs commonly appear (risk areas)

- Multiple write-sites for the same atom (e.g., `'trkn'`) — without a single authoritative source and guard flags this leads to overwrites. Resolved by pre-seed + track_written flag.
- Cover-art recompression/loss: writing MP3 APIC frames through mutagen into MP4 without preserving original APIC bytes can cause re-encoded images. Use `original_source_files` and copy `APIC.data` or `covr` directly.
- Freeform atoms (`----:`) require bytes payloads; tests need to encode strings to bytes before writing.
- ID3/MP4 key name mismatches (`"\\xa9nam"` vs actual unicode `©nam`) — mapping keys must be decoded before use.
- Sorting by track number when metadata is inconsistent: `track_number_sort_key` handles tuples and strings, but malformed strings may sort wrong.

---

## Suggested checks & tests

- Regression test ensuring helper-derived `trkn` is never overwritten (added).
- Tests that cover cover-art copy paths: original MP3 APIC -> final MP4 covr; final covr format preserved.
- Tests for freeform SERIES write and read using `MP4FreeForm` and raw bytes.
- Sanity checks around `reformat_tag_for_file_type` for all mapping `data_types` (tuple_of_ints, integer, utf8_text, list_of_mp4cover).

---

## Quick reference: run-path for a `novel` folder

1. `cmd_mutate_convert` -> `mutate_metadata`:
   - `extract_metadata_from_folder(folder, 'novel')`
   - `mutate_metadata` writes mutated files to temp
2. `convert_folder_to_m4b` on mutated folder:
   - create ffmpeg concat list + metadata, run ffmpeg
   - add chapters using mutagen MP4Chapters
   - call `add_audiobook_metadata` with original and mutated source lists
3. `add_audiobook_metadata` applies final tags and cover art, sets `trkn`, `sonm`, `tvsn`, `\xa9grp`, `covr`.
4. `move_to_destination` moves final M4B to destination.

---

## Quick reference: run-path for a `series` folder

1. Top-level CLI uses `batch_verify` / `series_verify` or `analyze_folder_structure` to find child folders.
2. Each child folder is processed as a `novel` (use the novel run-path), but `mutate_metadata` will include series-specific logic:
   - `album_sort` is prefixed with cleaned parent folder name
   - `grouping` is set to series name (sanitized) or cleaned parent
   - `series_index` inference tries multiple heuristics across siblings
3. Combined: final M4B files for each child are written with `grouping` / `tvsn` set to keep series structure.

---

## Notes for maintainers

- Keep `combined-metadata-mapping.json` authoritative; changes to mapping should be mirrored by updates to `reformat_tag_for_file_type` and tests.
- When adding write sites for metadata atoms, prefer idempotent assignment and set guard flags (e.g., `track_written`) to prevent accidental overwrites.
- Use dependency injection (`mp4_class`, `mutagen_file_func`) in `add_audiobook_metadata` to make unit tests robust and fast.

---

Document created: SEARCH_RETURN_FLOW.md
