"""
CLI entrypoint for AudiobookProcessor.
Handles argument parsing and dispatches to the appropriate dataflow modules.
"""
import argparse
import os
from audiobook_p.mutation import convert_folder_to_m4b, add_chapters_to_m4b, ffmpeg_inject_chapters, add_audiobook_metadata
from audiobook_p.metadata_extraction import extract_metadata_from_folder
from audiobook_p.metadata_normalization import reformat_tag_for_file_type
from audiobook_p.utils import sanitize_string, book_title_logic, clean_folder_name, clean_filename_text, natural_sort_key, track_number_sort_key, parse_series_index_from_folder_name, discover_audiobook_folders


def main():
    parser = argparse.ArgumentParser(
        description="AudiobookProcessor: Modular audiobook metadata extraction, normalization, and conversion.\n\n"
        "Usage: py audiobook-p-cli <mode> <input> <output> [options]\n"
        "Modes: extract, normalize, convert, add-chapters, add-metadata, mutate-convert, mutate\n"
        "\nFor all folder-processing modes, recursive search is now the default. Use --type/folder-type to control series/novel/auto behavior."
    )

    parser.add_argument('mode', choices=['extract', 'convert', 'add-chapters', 'mutate-convert', 'mutate'],
                        nargs='?', default='mutate-convert', help='Operation mode (default: mutate-convert)')
    parser.add_argument('input', nargs='?', help='Input folder or file')
    parser.add_argument('output', nargs='?', help='Output file or folder (required for convert/mutate-convert/scan modes)')

    # Common options
    parser.add_argument('--folder-type', choices=['auto', 'series', 'novel'], default='auto', help='Folder type')
    parser.add_argument('--sort-by', choices=['filename', 'track'], default='filename', help='Sort files by')
    parser.add_argument('--chapter-titles', action='store_true', help='Use file titles for chapters')
    parser.add_argument('--series-name', help='Series name (optional)')
    parser.add_argument('--part-titles', action='store_true', help='Enable part titles')
    parser.add_argument('--author-name', help='Author name (optional)')
    parser.add_argument('--narrator-name', help='Narrator name (optional)')
    parser.add_argument('--author-fix', action='store_true', help='Fix author name format')
    parser.add_argument('--album-sort-prefix', help='Prefix for album_sort (optional)')
    parser.add_argument('--album-suffix', help='Suffix for album_sort (optional)')

    # Recursive search options (now default for folder-processing modes)
    parser.add_argument('--type', dest='folder_type', choices=['auto', 'series', 'novel'], default='auto',
                        help='How to treat the input path: auto=recursive search (default), series=treat as series root with recursive search, novel=treat as single folder')
    parser.add_argument('--max-depth', type=int, default=5, help='Maximum directory depth to search (default: 5)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without actually processing')



    import sys
    # If the first positional argument is not a known mode, insert 'mutate-convert' as the mode
    known_modes = ['extract', 'convert', 'add-chapters', 'mutate-convert', 'mutate']
    argv = sys.argv[1:]
    if argv and argv[0] not in known_modes:
        argv = ['mutate-convert'] + argv
    args = parser.parse_args(argv)

    # Handle output alias
    if hasattr(args, 'output') and args.output and not args.output:
        args.output = args.output

    # Validate required arguments for each mode
    if args.mode in ['extract', 'normalize', 'mutate'] and not args.input:
        print(f"[ERROR] {args.mode} mode requires an input path")
        return
    elif args.mode in ['convert', 'mutate-convert'] and not args.input:
        print(f"[ERROR] {args.mode} mode requires an input path")
        return
    elif args.mode in ['convert', 'mutate-convert'] and not args.output:
        print(f"[ERROR] {args.mode} mode requires an output path")
        return
    elif args.mode in ['add-chapters', 'add-metadata'] and not args.input:
        print(f"[ERROR] {args.mode} mode requires an input/output path")
        return

    if args.mode == 'extract':
        config = {
            'input': args.input,
            'folder_type': args.folder_type,
            'sort_by': args.sort_by
        }
        print("[INFO] Extracting metadata...")
        result = extract_metadata_from_folder(config['input'], config['folder_type'], sort_by=config['sort_by'])
        print(result)
    elif args.mode == 'convert':
        # Recursive search is now default for folder input
        from audiobook_p.utils import discover_audiobook_folders
        discovered_folders = discover_audiobook_folders(args.input, max_depth=args.max_depth)
        if not discovered_folders:
            print("[INFO] No audiobook folders found.")
            return
        for folder in discovered_folders:
            folder_name = os.path.basename(folder['path'])
            output_path = os.path.join(args.output, folder_name + '.m4b')
            config = {
                'input': folder['path'],
                'output': output_path,
                'sort_by': args.sort_by,
                'chapter_titles': args.chapter_titles,
                'series_name': args.series_name,
                'part_titles': args.part_titles,
                'author_name': args.author_name,
                'narrator_name': args.narrator_name,
                'author_fix': args.author_fix,
                'album_sort_prefix': args.album_sort_prefix,
                'album_suffix': args.album_suffix,
                'folder_type': folder['type']
            }
            print(f"[INFO] Converting folder to M4B: {folder['path']}")
            m4b_path = convert_folder_to_m4b(config['input'], config['output'], config=config, sort_by=config['sort_by'], chapter_titles=config['chapter_titles'], series_name=config['series_name'], author_fix=config['author_fix'], cli_author=config['author_name'], original_source_path=config['input'])
            print(f"[SUCCESS] M4B created at: {m4b_path}")
    elif args.mode == 'add-chapters':
        config = {
            'output': args.input  # For add-chapters, input is the M4B file
        }
        print("[INFO] Adding chapters to M4B...")
        # Placeholder: add_chapters_to_m4b(config['output'], chapters_info)
        pass
    # ...existing code...
    elif args.mode == 'mutate-convert':
        from audiobook_p.utils import discover_audiobook_folders
        discovered_folders = discover_audiobook_folders(args.input, max_depth=args.max_depth)
        if not discovered_folders:
            print("[INFO] No audiobook folders found.")
            return
        from audiobook_p.main import cmd_mutate_convert
        for folder in discovered_folders:
            folder_name = os.path.basename(folder['path'])
            output_path = os.path.join(args.output, folder_name + '.m4b')
            config = {
                'input': folder['path'],
                'output': output_path,
                'sort_by': args.sort_by,
                'chapter_titles': args.chapter_titles,
                'series_name': args.series_name,
                'part_titles': args.part_titles,
                'author_name': args.author_name,
                'narrator_name': args.narrator_name,
                'author_fix': args.author_fix,
                'album_sort_prefix': args.album_sort_prefix,
                'album_suffix': args.album_suffix,
                'folder_type': folder['type']
            }
            print(f"[INFO] Mutate and convert folder to M4B: {folder['path']}")
            class ArgsObj:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            args_obj = ArgsObj(**config, source=config['input'], destination=config['output'], root_path=args.input)
            m4b_path = cmd_mutate_convert(args_obj)
            print(f"[SUCCESS] Mutate-convert M4B created at: {m4b_path}")
    elif args.mode == 'mutate':
        from audiobook_p.utils import discover_audiobook_folders
        discovered_folders = discover_audiobook_folders(args.input, max_depth=args.max_depth)
        if not discovered_folders:
            print("[INFO] No audiobook folders found.")
            return
        from audiobook_p.main import mutate_metadata
        for folder in discovered_folders:
            config = {
                'input': folder['path'],
                'sort_by': args.sort_by,
                'chapter_titles': args.chapter_titles,
                'series_name': args.series_name,
                'part_titles': args.part_titles,
                'author_name': args.author_name,
                'narrator_name': args.narrator_name,
                'author_fix': args.author_fix,
                'album_sort_prefix': args.album_sort_prefix,
                'album_suffix': args.album_suffix,
                'folder_type': folder['type']
            }
            print(f"[INFO] Mutating metadata in folder: {folder['path']}")
            meta = extract_metadata_from_folder(config['input'], config['folder_type'], sort_by=config['sort_by'])
            mutated = mutate_metadata(
                meta,
                album_sort_prefix=config['album_sort_prefix'],
                album_suffix=config['album_suffix'],
                sort_by=config['sort_by'],
                chapter_titles=config['chapter_titles'],
                series_name=config['series_name'],
                part_titles=config['part_titles'],
                author_name=config['author_name'],
                narrator_name=config['narrator_name'],
                author_fix=config['author_fix'],
                in_place=True
            )
            print(f"[SUCCESS] Mutated metadata for folder: {mutated['folder']}")
    else:
        print("[ERROR] Unknown mode.")
        parser.print_help()
    # ...existing code...

if __name__ == "__main__":
    main()
