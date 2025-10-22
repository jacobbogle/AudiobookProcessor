This file lists the main top-level functions in ``audiobook_p/main.py`` with short descriptions and file:line references.


---

Detailed entries (signature, contract, error modes, edge cases)


1) book_title_logic(title)
   - Purpose: Clean and normalize chapter/title strings by removing a single leading numeric track token and capitalizing the first alphabetic character.
   - Inputs: title (str)
   - Outputs: cleaned_title (str)
   - Error modes: Returns input unchanged for None/empty; may raise if non-string with unexpected attributes
   - Edge cases:
	 - "01 01 Book Title" -> removes only the first leading number
	 - Empty or None -> returns as-is
	 - Strings with no alphabetic characters -> returns unchanged after numeric removal
   - Location: `audiobook_p/main.py:42`

2) extract_metadata_from_file(file_path)
   - Signature: extract_metadata_from_file(file_path) -> dict
   - Purpose: Read metadata from a single audio file using `combined-metadata-mapping.json` and normalize values.
   - Inputs: file_path (str)
   - Outputs: dict mapping descriptive keys (e.g., 'title', 'artist', 'track_number') to python values or 'Present' for images
   - Error modes: Raises ValueError if Mutagen cannot load the file; catches tag-specific errors per-field and continues
   - Edge cases:
	 - Files with non-standard/encoded tag keys (eg. "\\xa9nam") are normalized via generate_key_variants
	 - COMM/COMMENT frames are selected heuristically (longest or no-description preferred)
	 - Corrupt/unreadable files -> MutagenFile returns None -> ValueError
   - Location: `audiobook_p/main.py:66`

3) generate_key_variants(tag_literal)
   - Purpose: (nested helper) Produce variants (unicode/bytes forms) of a mapping tag to match audio tag keys
   - Inputs: tag_literal (str)
   - Outputs: list of candidate keys (str/bytes)
   - Notes: Nested inside `extract_metadata_from_file`; include here for discoverability
   - Location: `audiobook_p/main.py:110` (nested)

4) parse_metadata_to_python_safe(metadata_dict)
   - Signature: parse_metadata_to_python_safe(metadata_dict) -> dict
   - Purpose: Translate extract_metadata_from_file output into a predictable dict with 'mp3', 'mp4', 'value' fields
   - Inputs: metadata_dict (dict)
   - Outputs: dict of desc_key -> {'mp3': key, 'mp4': key, 'value': python_value}
   - Error modes: Silently skips fields not defined in mapping; decodes bytes with utf-8/latin-1 fallbacks
   - Edge cases:
	 - Bytes requiring latin-1 decoding
	 - Non-string scalar metadata (ints/floats) converted to str
   - Location: `audiobook_p/main.py:294`

5) reformat_tag_for_file_type(desc_key, python_value, file_type)
   - Signature: reformat_tag_for_file_type(desc_key, python_value, file_type) -> formatted_value
   - Purpose: Convert python-safe values into the correct mutagen format for MP3 (ID3 frames) or MP4 (arrays/tuples)
   - Inputs: desc_key (str), python_value (var), file_type ('mp3'|'mp4')
   - Outputs: properly-typed value ready to set on audio.tags
   - Error modes: Returns the input unchanged if desc_key not found; may raise on integer conversion failures (caught by callers)
   - Edge cases:
	 - track strings like "1/12" -> (1,12)
	 - Python 2/3 unicode handling (uses try/except NameError for unicode/basestring)
   - Location: `audiobook_p/main.py:363`

6) natural_sort_key(filename)
   - Signature: natural_sort_key(filename) -> list
   - Purpose: Provide an ordering key that splits strings into ints and lowercased text parts so "2" < "10".
   - Inputs: filename (str)
   - Outputs: list of alternating text/int used as sort key
   - Edge cases: filenames with no digits -> single-element list; digit-only names -> integer elements
   - Location: `audiobook_p/main.py:452`

7) track_number_sort_key(file_path, metadata_dict)
   - Signature: track_number_sort_key(file_path, metadata_dict) -> tuple(priority, value)
   - Purpose: Primary sort by track metadata when present, otherwise fall back to natural filename ordering
   - Inputs: file_path (str), metadata_dict (dict) — expects 'track_number' key in metadata
   - Outputs: tuple used as sort key; priority 0 = use numeric track, 1 = filename fallback
   - Edge cases: MP4 tuple format vs MP3 "1/12" string; malformed track strings fallback to filename ordering
   - Location: `audiobook_p/main.py:464`

8) extract_metadata_from_folder(folder_path, folder_type, sort_by='filename')
   - Signature: extract_metadata_from_folder(folder_path, folder_type, sort_by='filename') -> dict
   - Purpose: Scan a folder for .m4a/.mp3 files, optionally extract per-file metadata, and return an ordered mapping
   - Inputs: folder_path (str), folder_type ('novel'|'series'), sort_by ('filename'|'track')
   - Outputs: { 'folder_type': ..., 'folder': ..., 'files': {file_path: metadata,...} }
   - Error modes: Raises ValueError if folder missing or contains no audio files; per-file errors included in result
   - Edge cases: Mixed extensions, unreadable files (error strings stored in results), empty folder
   - Location: `audiobook_p/main.py:496`

9) copy_folder(source_path, max_attempts=5)
   - Signature: copy_folder(source_path, max_attempts=5) -> str | None
   - Purpose: Copy a source folder to a temp directory with retry and cleanup on failure
   - Inputs: source_path (str), max_attempts (int)
   - Outputs: path to copied folder (str) or None on permanent failure
   - Edge cases: Non-existent source -> returns None; varying shutil.copytree behavior between Python versions handled
   - Location: `audiobook_p/main.py:546`

10) apply_metadata_to_file(file_path, metadata_dict)
	- Signature: apply_metadata_to_file(file_path, metadata_dict) -> None
	- Purpose: Set metadata fields on a single audio file according to mapping and data types
	- Inputs: file_path (str), metadata_dict (desc_key -> value)
	- Outputs: Writes tags to file (audio.save())
	- Error modes: Raises ValueError if Mutagen can't load file; individual tag set errors are ignored (skipped)
	- Edge cases: Preserves pictures (doesn't overwrite); empty strings ignored except picture
	- Location: `audiobook_p/main.py:600`

11) mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename')
	- Signature: mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename') -> str (temp folder path)
	- Purpose: Create a temporary copy of a folder and apply normalized/mutated metadata to each file (renumber tracks)
	- Inputs: metadata_dict (from extract_metadata_from_folder), album_sort_prefix (opt), album_suffix (opt), sort_by
	- Outputs: path to temp folder containing mutated files
	- Error modes: Raises ValueError on invalid metadata_dict or failed copy; logs warnings for per-file failures
	- Edge cases: Missing temp files skipped, series vs novel album_sort logic applied, sort_by='track' uses metadata when available
	- Location: `audiobook_p/main.py:708`

12) convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename')
	- Signature: convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename') -> str (output_path)
	- Purpose: Concatenate audio files (ordered by sort_by) into a single M4B using ffmpeg and create chapter metadata
	- Inputs: folder_path (str), output_path (str), config (optional dict-like), sort_by
	- Outputs: path to generated M4B file
	- Error modes: Raises ValueError for missing folder or files; raises Exception on ffmpeg failure or empty output
	- Edge cases: Missing duration (fallback 10 minutes), file paths with quotes escaped for ffmpeg concat, ffmpeg exit codes handled with retry to capture stderr
	- Location: `audiobook_p/main.py:841`

13) add_audiobook_metadata(m4b_path, source_files)
	- Signature: add_audiobook_metadata(m4b_path, source_files) -> None
	- Purpose: Copy text metadata and cover art from source files into the created M4B (MP4 tags)
	- Inputs: m4b_path (str), source_files (list[str])
	- Outputs: Writes tags to M4B file
	- Error modes: Skips entirely if MP4 mutagen support missing; prints warnings on per-file failures
	- Edge cases: COMM frame selection heuristics; copies first-found picture (MP4 'covr' preferred, then MP3 'APIC')
	- Location: `audiobook_p/main.py:1006`

14) move_to_destination(source_path, destination_path, folder_type)
	- Signature: move_to_destination(source_path, destination_path, folder_type) -> str
	- Purpose: Move a processed folder into destination, creating a series subfolder when folder_type == 'series'
	- Inputs: source_path (str), destination_path (str), folder_type ('novel'|'series')
	- Outputs: Path to final destination folder
	- Edge cases: Overwrites existing destination by removing it first; creates needed directories
	- Location: `audiobook_p/main.py:1201`

15) cmd_convert(args)
	- Signature: cmd_convert(args) -> None
	- Purpose: CLI handler for converting a folder to M4B; validates inputs, optionally shows progress and calls convert_folder_to_m4b
	- Inputs: args with .source, .output, .sort_by
	- Outputs: Prints JSON result or error strings
	- Edge cases: Accepts output as directory or filename; uses fallback validation when enhancement modules missing
	- Location: `audiobook_p/main.py:1242`

16) cmd_extract(args)
	- Signature: cmd_extract(args) -> None
	- Purpose: CLI handler to extract metadata from a file or folder; delegates to extract_metadata_from_folder for folders
	- Inputs: args.source
	- Outputs: JSON printed to stdout
	- Edge cases: Batch/series detection uses batch_verify/series_verify if available; per-folder errors captured in output
	- Location: `audiobook_p/main.py:1403`

17) cmd_mutate(args)
	- Signature: cmd_mutate(args) -> None
	- Purpose: CLI handler to mutate metadata and move results to a destination
	- Inputs: args.source, args.destination, args.album_sort_prefix, args.album_suffix
	- Outputs: JSON printed describing mutated folders or errors
	- Edge cases: Handles single-folder and batch/series structures via batch_verify/series_verify when available
	- Location: `audiobook_p/main.py:1513`

18) cmd_config(args)
	- Signature: cmd_config(args) -> None
	- Purpose: CLI handler to view/set/reset configuration using audiobook_p.config
	- Inputs: args.show|--reset|--create-default|--set|--get
	- Outputs: Prints results and writes config when --set used
	- Edge cases: Falls back to local import when package import fails; parses JSON values for --set when possible
	- Location: `audiobook_p/main.py:1634`

19) cmd_mutate_convert(args)
	- Signature: cmd_mutate_convert(args) -> None
	- Purpose: Convenience CLI to mutate files into a temp folder and convert them to M4B in one flow
	- Inputs: args.source, args.destination, args.album_sort_prefix, args.album_suffix, args.sort_by
	- Outputs: Prints progress messages and calls cmd_convert with a MockArgs wrapper
	- Nested helper: MockArgs.__init__(self, source, output, sort_by) — simple container used to forward arguments to cmd_convert
	- Edge cases: Does not support multi-folder mutate-convert; uses temp dir and attempts cleanup in finally block
	- Location: `audiobook_p/main.py:1685`

20) cmd_info(args)
	- Signature: cmd_info(args) -> None
	- Purpose: Print package info and config location
	- Inputs: args (unused)
	- Outputs: Short informational print to stdout
	- Location: `audiobook_p/main.py:1771`

21) cli(argv=None)
	- Signature: cli(argv=None) -> None
	- Purpose: Top-level argparse CLI definition and dispatch for subcommands (info, extract, mutate, convert, mutate-convert, config)
	- Inputs: argv (list[str]) optional
	- Outputs: Calls the chosen command handler
	- Location: `audiobook_p/main.py:1790`

