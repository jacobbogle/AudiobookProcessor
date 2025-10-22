# AudiobookProcessor — Data Flow Analysis (Simplified)

This document summarizes the high-level data flow, modes, and important implementation details for the AudiobookProcessor project (`audiobook_p/main.py`). It's intended to help maintainers, contributors, and users quickly understand how data moves through the system and where to look when troubleshooting.

## Modes / Commands

The CLI exposes several operational modes (subcommands). Each mode reads inputs, applies transformations, and produces outputs. Core modes:

- `extract` — Read metadata from a single audio file or a folder of audio files.
  - Input: single audio file path or folder path containing audio files (`.mp3`, `.m4a`, `.m4b`)
  - Output: JSON printed to stdout describing extracted metadata or a folder-level summary
  - Key functions: `extract_metadata_from_file()`, `extract_metadata_from_folder()`

- `mutate` — Normalize and rewrite metadata for files, then move the mutated folder to a destination.
  - Input: folder path with audio files, destination path, optional `--album-sort-prefix`, `--album-suffix`, `--sort-by`
  - Output: Mutated temporary folder (copied and updated), moved to destination; JSON summary printed
  - Key functions: `extract_metadata_from_folder()`, `mutate_metadata()`, `apply_metadata_to_file()`, `move_to_destination()`

- `convert` — Concatenate audio files into an M4B (MP4 audio) container with chapters.
  - Input: folder path with audio files, output file path or directory, optional `--sort-by`
  - Output: Single `.m4b` file with chapter metadata; JSON summary printed
  - Key functions: `convert_folder_to_m4b()`, `add_audiobook_metadata()`

- `mutate-convert` — Run `mutate` (to a temporary folder), then `convert` the mutated files to M4B, and move result to destination.
  - Input: similar to `mutate` + output destination for M4B, optional `--sort-by`
  - Output: Final `.m4b` file at destination; temporary files cleaned up
  - Key functions: orchestrates `mutate_metadata()` and `convert_folder_to_m4b()`

- `config` — Manage configuration file (get/set/reset)
  - Input: configuration keys/values
  - Output: Read/write configuration persisted to a JSON file (path shown in `info`)

- `info` — Print package & configuration info
  - Input: none
  - Output: brief info printed to stdout


## High-level Data Flow

1. CLI parsing (`cli()`)
   - Subcommand chosen -> calls corresponding `cmd_*` function with `args`.

2. Validation & discovery
   - For folder inputs, the code finds audio files using glob (`*.m4a`, `*.mp3`).
   - If available, validation helpers from `audiobook_p.validation` are used (dependency checks, folder validation, estimates).

3. Metadata extraction
   - `extract_metadata_from_file(file_path)` loads a file with Mutagen (`MutagenFile`) and maps tags according to `combined-metadata-mapping.json`.
   - The mapping contains `mutagen_keys` and `data_types` for many descriptive fields (core, audiobook-specific, sort fields, extended metadata).
   - `extract_metadata_from_folder(folder_path, folder_type, sort_by)` optionally pre-extracts metadata for all files (used when `--sort-by track`).

4. Sorting
   - Default: natural filename sorting using `natural_sort_key()` which splits numeric components and treats them numerically.
   - Optional: `--sort-by track` will attempt to extract track numbers from metadata and sort by them using `track_number_sort_key()` with a filename fallback.

5. Mutation
   - `mutate_metadata()` copies folder to a temp location, applies cleaned titles (`book_title_logic`) and other rules (album/album_sort, media_kind, genre), then writes tags back using `apply_metadata_to_file()`.
   - Track numbers are reassigned incrementally based on chosen sort order (filename or track) and written to metadata.

6. Conversion to M4B
   - `convert_folder_to_m4b()` builds an ffmpeg-compatible file list and a FFMETADATA1 chapter file.
   - Chapter titles are taken from source metadata `title` when available, otherwise from the filename (cleaned with `book_title_logic`).
   - ffmpeg concatenates and outputs the `.m4b`. After creation, `add_audiobook_metadata()` copies text tags and cover art into the M4B.

7. Output & cleanup
   - Temporary files (file lists, metadata files, mutated temp folders) are cleaned up.
   - Final results printed as JSON summaries to stdout.


## Data Shapes / Contracts

- CLI args: argparse Namespace (fields vary per command). Notable new arg: `--sort-by` in `convert` and `mutate-convert` (values: `filename` or `track`).

- Metadata (extracted): dict of descriptive keys -> values (strings, tuples for track/disc, 'Present' for images). Example snippet:
  {
    "title": "Chapter 1",
    "album": "My Book",
    "track": "1",
    "track_number": (1, 12) # for MP4 in some cases
  }

- extract_metadata_from_folder() -> returns:
  {
    "folder_type": "novel" | "series",
    "folder": "/abs/path/to/folder",
    "files": { "/path/file1.mp3": { ...metadata... }, ... }
  }

- apply_metadata_to_file(file_path, metadata_dict)
  - Accepts descriptive keys. It maps to ID3/MP4 tags based on `combined-metadata-mapping.json`.


## Important Functions & Where to Look

- `cli()` — argument parsing and command dispatch
- `cmd_extract`, `cmd_mutate`, `cmd_convert`, `cmd_mutate_convert` — high-level operation orchestration
- `extract_metadata_from_file()` — tag reading & mapping logic
- `extract_metadata_from_folder()` — folder-level metadata extraction + optional pre-extraction for track sorting
- `natural_sort_key()` — filename natural sort
- `track_number_sort_key()` — track-based sort (with filename fallback)
- `mutate_metadata()` & `apply_metadata_to_file()` — core of metadata normalization and writing
- `convert_folder_to_m4b()` & `add_audiobook_metadata()` — concatenation, chapter generation and final metadata copy


## Edge Cases & Notes

- Missing or malformed metadata: the code falls back to filename-based titles and natural sorting. `extract` will report errors per-file in its JSON output.
- Track sorting: if `--sort-by track` is used and track metadata is absent or malformed for some files, those files fall back to filename-based natural sorting.
- MP3 vs MP4 differences: track numbers can be stored differently (strings like "1/12" in ID3 vs tuple `(1,12)` in MP4). The `track_number_sort_key()` function handles both.
- File durations: if Mutagen fails to read duration, the converter estimates 10 minutes per chapter (configurable via `processing.ffmpeg_quality` in config, though duration estimate itself is not configurable yet).
- Cover art: `add_audiobook_metadata()` attempts to find and copy cover art from the first source file that contains it. MP4 `covr` or ID3 `APIC` frames are supported.


## Quick Verification & Useful Commands

Run basic help to see new `--sort-by` option:

```bash
python audiobook_p/main.py convert --help
python audiobook_p/main.py mutate-convert --help
```

Extract metadata from a folder and print JSON:

```bash
python audiobook_p/main.py extract /path/to/folder
```

Test convert using filename sort (default) and track sort:

```bash
python audiobook_p/main.py convert /path/to/folder /tmp/output.m4b
python audiobook_p/main.py convert /path/to/folder /tmp/output-track.m4b --sort-by track
```

Test mutate-convert with track sorting:

```bash
python audiobook_p/main.py mutate-convert /path/to/folder /tmp/output.m4b --sort-by track
```

Notes:
- The repo auto-installs `mutagen` if missing (script attempts to pip install when run).
- `ffmpeg` must be installed and available on PATH for conversion.


## Assumptions & Next Steps

Assumptions made while summarizing:
- `combined-metadata-mapping.json` is present and maps descriptive keys to mutagen keys.
- Mutagen is available or can be installed by the script.

Suggested next steps:
- Add unit tests for `track_number_sort_key()` and `natural_sort_key()` using representative filename and metadata samples.
- Add a small integration test that runs `convert` on a tiny set of sample files and verifies chapter order.
- Document configuration options and default config location in README.

---
Generated on: 2025-10-21

