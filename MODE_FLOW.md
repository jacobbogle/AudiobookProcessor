MODE_FLOW.md

Summary
-------
A concise reference mapping each CLI mode to its core dataflow and the primary functions invoked.

Format for each mode:
- Purpose: short description
- Inputs: what the user provides
- Outputs: produced artifacts
- Key functions called (ordered)
- Short dataflow (steps with function names)

Also included: for major helper functions listed per-mode, a brief Inputs -> Outputs signature for quick reference.


---

## info
- Purpose: Display package and configuration info
- Inputs: none
- Outputs: printed JSON/text about the package and config
- Key functions: `cmd_info`, `get_config` (optional)
- Dataflow:
  - cli -> `cmd_info` -> optionally `get_config` -> print


## extract
- Purpose: Extract metadata from a file or folder (novel/series)
- Inputs: file or folder path
- Outputs: JSON-ish metadata printed to stdout
- Key functions: `cmd_extract`, `analyze_folder_structure`, `extract_metadata_from_folder`, `extract_metadata_from_file`, `track_number_sort_key`

Function I/O (quick):
- `cmd_extract(args)`
  - Inputs: argparse `args` with `source` (path)
  - Outputs: prints JSON to stdout; returns None
- `analyze_folder_structure(source_path)`
  - Inputs: directory path
  - Outputs: list of `{folder_type, folder}` results
- `extract_metadata_from_folder(folder_path, folder_type, sort_by='filename')`
  - Inputs: folder path, folder_type ('novel'|'series'), optional sort flag
  - Outputs: dict: {folder_type, folder, files: {file_path: metadata_dict}}
- `extract_metadata_from_file(file_path)`
  - Inputs: audio file path
  - Outputs: dict of descriptive metadata (title, track_number, picture presence, etc.)
- `track_number_sort_key(file_path, metadata_dict)`
  - Inputs: file path, per-file metadata dict
  - Outputs: sort key tuple (priority, value)
- Dataflow:
  - cli -> `cmd_extract`
  - if file: `extract_metadata_from_file(path)` -> print
  - if folder: determine folder type via `batch_verify`/`series_verify` or `analyze_folder_structure`
  - for each folder to process: `extract_metadata_from_folder(folder, type)`
    - collect files via glob
    - optionally call `extract_metadata_from_file` (for track sorting)
    - `extract_metadata_from_file(file)`:
      - `mutagen.File(file)` -> read tags
      - map tags -> descriptive keys using `combined-metadata-mapping.json`
      - normalize values (MP4Cover / ID3 frames / COMM frames)


## mutate
- Purpose: Produce a temporary mutated folder where metadata is cleaned/formatted
- Inputs: source folder, optional album_sort_prefix, album_suffix, series_name
- Outputs: mutated folder path (on disk)
- Key functions: `cmd_mutate`, `extract_metadata_from_folder`, `mutate_metadata`, `copy_folder`, `parse_metadata_to_python_safe`, `book_title_logic`, `apply_metadata_to_file`, `reformat_tag_for_file_type`, `clean_album_name`, `sanitize_series_name`, `parse_series_index_from_folder_name`

Function I/O (quick):
- `cmd_mutate(args)`
  - Inputs: argparse `args` with source & destination
  - Outputs: prints JSON summary; returns None
- `mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None)`
  - Inputs: metadata dict from `extract_metadata_from_folder` and options
  - Outputs: path to mutated temp folder on disk (string)
- `copy_folder(source_path, max_attempts=5)`
  - Inputs: source folder path
  - Outputs: copied temp folder path or None
- `parse_metadata_to_python_safe(metadata_dict)`
  - Inputs: raw metadata dict from `extract_metadata_from_file`
  - Outputs: normalized dict with mp3/mp4 keys and Python-safe values
- `apply_metadata_to_file(file_path, metadata_dict)`
  - Inputs: target audio file path, metadata dict of descriptive keys -> values
  - Outputs: writes tags to file, returns None (may raise on failure)
- `reformat_tag_for_file_type(desc_key, python_value, file_type)`
  - Inputs: descriptive key, Python-safe value, 'mp3'|'mp4'
  - Outputs: formatted value suitable for mutagen assignment
- Dataflow:
  - cli -> `cmd_mutate` -> `extract_metadata_from_folder`
  - call `mutate_metadata(metadata_dict, ...)`:
    - `copy_folder` to temp
    - iterate files: `parse_metadata_to_python_safe` -> normalize -> transformations (`book_title_logic`, album/grouping changes, series_index inference)
    - set `title_sort` (`sonm`) = uncleaned file stem
    - `apply_metadata_to_file(temp_file, updated_metadata)`:
      - `reformat_tag_for_file_type` -> write MP4 atoms or ID3 frames; preserve APIC for MP3
    - return mutated folder path


## convert
- Purpose: Concatenate audio into single `.m4b` with chapters and final metadata
- Inputs: folder path of audio files (mutated or original), output path, optional original_source_path, chapter_titles, series_name
- Outputs: `.m4b` file at given output path
- Key functions: `cmd_convert`, `convert_folder_to_m4b`, `add_chapters_to_m4b`, `add_audiobook_metadata`, `_determine_track_value_for_sources`, `reformat_tag_for_file_type`, `mutagen.File`, `parse_series_index_from_folder_name`

Function I/O (quick):
- `cmd_convert(args, original_source_path=None)`
  - Inputs: argparse `args` with `source`, `output`, optional flags
  - Outputs: writes `.m4b` file; prints JSON result; returns None
- `convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename', original_source_path=None, chapter_titles=False, series_name=None)`
  - Inputs: folder path of audio files, output path for M4B, options
  - Outputs: path to created `.m4b` file (string)
- `add_chapters_to_m4b(m4b_path, chapters_info)`
  - Inputs: path to M4B, chapters_info list [{'start', 'title'}]
  - Outputs: writes chapters to M4B, returns True/False
- `add_audiobook_metadata(m4b_path, source_files, original_source_files=None, series_name=None, mp4_class=None, mutagen_file_func=None)`
  - Inputs: path to M4B, ordered list of source file paths, optional originals and injections
  - Outputs: writes tags (covr, trkn, sonm, tvsn, etc.) to M4B; returns None
- `_determine_track_value_for_sources(source_files, MutagenFile)`
  - Inputs: ordered list of source file paths, mutagen File function or injection
  - Outputs: tuple `(track_val, track_written)` where `track_val` is MP4-style `trkn` and `track_written` indicates origin
- Dataflow:
  - cli -> `cmd_convert` -> collect & sort audio files
  - build ffmpeg file list + ffmetadata (chapters) by reading durations with `mutagen.File`
  - run ffmpeg to create combined `.m4b`
  - `add_chapters_to_m4b(m4b, chapters_info)`
  - determine `original_audio_files` if available (for cover art)
  - `add_audiobook_metadata(m4b_path, source_files, original_source_files, series_name)`:
    - load `MP4` object
    - `pre-seed trkn` with `_determine_track_value_for_sources(source_files, MutagenFile)`
    - copy cover art from originals (prefer `covr` / `APIC` raw data)
    - copy text metadata from first (mutated) source using mapping and `reformat_tag_for_file_type`
    - set `sonm` (title_sort) to first file stem
    - infer and set `tvsn` from folder name (via `parse_series_index_from_folder_name`)
    - guard `trkn` writes using `track_written` to preserve originals
    - final safety-net ensure `trkn` present (1/total) if not source-derived


## mutate-convert
- Purpose: Run mutate then convert in one operation; useful when taking an unclean folder -> final M4B
- Inputs: source folder, destination, mutation options, series-name
- Outputs: `.m4b` in destination
- Key functions: `cmd_mutate_convert`, `mutate_metadata`, `convert_folder_to_m4b` (via `cmd_convert`), `move_to_destination`, `add_audiobook_metadata`

Function I/O (quick):
- `cmd_mutate_convert(args)`
  - Inputs: argparse args with `source`, `destination`, mutation options
  - Outputs: prints JSON result; final M4B saved to destination
- `move_to_destination(source_path, destination_path, folder_type)`
  - Inputs: path to source folder or file, destination dir, folder_type
  - Outputs: moves folder/file to destination, returns final path
- Dataflow:
  - cli -> `cmd_mutate_convert`
  - `mutate_metadata` (copy & write cleaned files to temp)
  - `convert_folder_to_m4b` on mutated folder (pass original_source_path so `add_audiobook_metadata` can prefer originals for cover)
  - `move_to_destination` to final output


## config
- Purpose: inspect and set configuration options
- Inputs: `--show`, `--set`, `--reset`, etc.
- Outputs: printed config or updated config files
- Key functions: `cmd_config`, `get_config`, `create_default_config_file`
- Dataflow: `cli -> cmd_config -> config.*` (no audio IO)


---

Notes
-----
- `combined-metadata-mapping.json` is the central mapping used by `extract_metadata_from_file`, `parse_metadata_to_python_safe`, and `reformat_tag_for_file_type`.
- Use injection knobs on `add_audiobook_metadata` (parameters `mp4_class`, `mutagen_file_func`) in tests to inject fakes that persist state.
- `track_written` and `_determine_track_value_for_sources` are the canonical places that implement the rule: prefer original per-chapter `trkn` when present and do not overwrite it with index-based defaults.

Document created: MODE_FLOW.md
