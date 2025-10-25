"""
CLI entrypoint for AudiobookProcessor.
Handles argument parsing and dispatches to the appropriate dataflow modules.
"""
import argparse
import os
from audiobook_p.mutation import convert_folder_to_m4b, add_chapters_to_m4b, ffmpeg_inject_chapters, add_audiobook_metadata
from audiobook_p.metadata_extraction import extract_metadata_from_folder
from audiobook_p.metadata_normalization import reformat_tag_for_file_type
from audiobook_p.utils import sanitize_string, book_title_logic, clean_album_name, sanitize_series_name, natural_sort_key, track_number_sort_key, parse_series_index_from_folder_name, discover_audiobook_folders


def main():
    parser = argparse.ArgumentParser(
        description="AudiobookProcessor: Modular audiobook metadata extraction, normalization, and conversion."
    )
    
    # Mode selection (optional, defaults to scan)
    parser.add_argument('--mode', choices=['extract', 'normalize', 'convert', 'add-chapters', 'add-metadata', 'mutate-convert', 'mutate', 'scan'], 
                       default='scan', help='Operation mode (default: scan)')
    
    # Positional arguments for input and output
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
    
    # Scan-specific options
    parser.add_argument('--type', choices=['auto', 'series', 'novel'], default='auto', 
                       help='How to treat the input path: auto=recursive scan, series=treat as series root with recursive search, novel=treat as single folder')
    parser.add_argument('--max-depth', type=int, default=5, help='Maximum directory depth to scan (default: 5)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed without actually processing')
    
    # Legacy aliases for backward compatibility
    parser.add_argument('--output', help='Output file or folder (alias for positional output)')
    
    args = parser.parse_args()
    
    # Handle output alias
    if hasattr(args, 'output') and args.output and not args.output:
        args.output = args.output

    # Validate required arguments for each mode
    if args.mode in ['extract', 'normalize', 'mutate'] and not args.input:
        print(f"[ERROR] {args.mode} mode requires an input path")
        return
    elif args.mode in ['convert', 'mutate-convert', 'scan'] and not args.input:
        print(f"[ERROR] {args.mode} mode requires an input path")
        return
    elif args.mode in ['convert', 'mutate-convert', 'scan'] and not args.output:
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
    elif args.mode == 'normalize':
        config = {
            'input': args.input
        }
        print("[INFO] Normalizing metadata (not yet implemented in CLI)...")
        # Placeholder for normalization logic
        pass
    elif args.mode == 'convert':
        output = args.output
        if os.path.isdir(output):
            from audiobook_p.utils import clean_album_name
            folder_name = os.path.basename(args.input)
            album_name = clean_album_name(folder_name)
            output = os.path.join(output, album_name + '.m4b')
        config = {
            'input': args.input,
            'output': output,
            'sort_by': args.sort_by,
            'chapter_titles': args.chapter_titles,
            'series_name': args.series_name,
            'part_titles': args.part_titles,
            'author_name': args.author_name,
            'narrator_name': args.narrator_name,
            'author_fix': args.author_fix,
            'album_sort_prefix': args.album_sort_prefix,
            'album_suffix': args.album_suffix,
            'folder_type': args.folder_type
        }
        print("[INFO] Converting folder to M4B...")
        m4b_path = convert_folder_to_m4b(config['input'], config['output'], config=config, sort_by=config['sort_by'], chapter_titles=config['chapter_titles'], series_name=config['series_name'], author_fix=config['author_fix'], cli_author=config['author_name'], original_source_path=config['input'])
        print(f"[SUCCESS] M4B created at: {m4b_path}")
    elif args.mode == 'add-chapters':
        config = {
            'output': args.input  # For add-chapters, input is the M4B file
        }
        print("[INFO] Adding chapters to M4B...")
        # Placeholder: add_chapters_to_m4b(config['output'], chapters_info)
        pass
    elif args.mode == 'add-metadata':
        config = {
            'output': args.input  # For add-metadata, input is the M4B file
        }
        print("[INFO] Adding metadata to M4B...")
        # Placeholder: add_audiobook_metadata(config['output'], ...)
        pass
    elif args.mode == 'mutate-convert':
        output = args.output
        if os.path.isdir(output):
            from audiobook_p.utils import clean_album_name
            folder_name = os.path.basename(args.input)
            album_name = clean_album_name(folder_name)
            output = os.path.join(output, album_name + '.m4b')
        config = {
            'input': args.input,
            'output': output,
            'sort_by': args.sort_by,
            'chapter_titles': args.chapter_titles,
            'series_name': args.series_name,
            'part_titles': args.part_titles,
            'author_name': args.author_name,
            'narrator_name': args.narrator_name,
            'author_fix': args.author_fix,
            'album_sort_prefix': args.album_sort_prefix,
            'album_suffix': args.album_suffix,
            'folder_type': args.folder_type
        }
        print("[INFO] Mutate and convert folder to M4B...")
        from audiobook_p.main import cmd_mutate_convert
        class ArgsObj:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        args_obj = ArgsObj(**config, source=config['input'], destination=config['output'])
        m4b_path = cmd_mutate_convert(args_obj)
        print(f"[SUCCESS] Mutate-convert M4B created at: {m4b_path}")
    elif args.mode == 'mutate':
        config = {
            'input': args.input,
            'sort_by': args.sort_by,
            'chapter_titles': args.chapter_titles,
            'series_name': args.series_name,
            'part_titles': args.part_titles,
            'author_name': args.author_name,
            'narrator_name': args.narrator_name,
            'author_fix': args.author_fix,
            'album_sort_prefix': args.album_sort_prefix,
            'album_suffix': args.album_suffix,
            'folder_type': args.folder_type
        }
        print("[INFO] Mutating metadata in folder...")
        from audiobook_p.main import mutate_metadata
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
    elif args.mode == 'scan':
        from audiobook_p.utils import discover_audiobook_folders

        if args.type == 'novel':
            # Treat input as single novel folder
            import os
            if not os.path.isdir(args.input):
                print(f"[ERROR] Input path is not a directory: {args.input}")
                return

            print(f"[INFO] Processing single novel folder: {args.input}")

            if args.dry_run:
                print(f"[INFO] Would process: {args.input} (novel)")
                print("[INFO] Dry run - not processing.")
                return

            # Process as single folder
            folder_name = os.path.basename(args.input)
            output_path = os.path.join(args.output, folder_name + '.m4b')

            # Ensure output directory exists
            os.makedirs(args.output, exist_ok=True)

            config = {
                'input': args.input,
                'output': output_path,
                'sort_by': args.sort_by,
                'chapter_titles': args.chapter_titles,
                'series_name': None,
                'part_titles': args.part_titles,
                'author_name': args.author_name,
                'narrator_name': args.narrator_name,
                'author_fix': args.author_fix,
                'album_sort_prefix': args.album_sort_prefix,
                'album_suffix': args.album_suffix,
                'folder_type': 'novel'
            }

            from audiobook_p.main import cmd_mutate_convert
            class ArgsObj:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)
            args_obj = ArgsObj(**config, source=config['input'], destination=config['output'])
            m4b_path = cmd_mutate_convert(args_obj)
            print(f"[SUCCESS] Created: {m4b_path}")

        elif args.type == 'series':
            # Treat input as series root, do recursive discovery
            print(f"[INFO] Scanning series directory for audiobook folders: {args.input}")
            discovered_folders = discover_audiobook_folders(args.input, max_depth=args.max_depth)

            if not discovered_folders:
                print("[INFO] No audiobook folders found in series.")
                return

            print(f"[INFO] Found {len(discovered_folders)} audiobook folder(s) in series:")
            for folder in discovered_folders:
                print(f"  - {folder['path']} ({folder['type']}, {folder['audio_files']} files)")

            if args.dry_run:
                print("[INFO] Dry run - not processing folders.")
                return

            # Process each discovered folder
            processed_count = 0
            for folder_info in discovered_folders:
                try:
                    print(f"[INFO] Processing {folder_info['type']} folder: {folder_info['path']}")

                    # Create output path based on folder structure
                    folder_name = os.path.basename(folder_info['path'])
                    output_path = os.path.join(args.output, folder_name + '.m4b')

                    # Ensure output directory exists
                    os.makedirs(args.output, exist_ok=True)

                    config = {
                        'input': folder_info['path'],
                        'output': output_path,
                        'sort_by': args.sort_by,
                        'chapter_titles': args.chapter_titles,
                        'series_name': None,  # Will be auto-detected
                        'part_titles': args.part_titles,
                        'author_name': args.author_name,
                        'narrator_name': args.narrator_name,
                        'author_fix': args.author_fix,
                        'album_sort_prefix': args.album_sort_prefix,
                        'album_suffix': args.album_suffix,
                        'folder_type': folder_info['type']  # Use detected type
                    }

                    from audiobook_p.main import cmd_mutate_convert
                    class ArgsObj:
                        def __init__(self, **kwargs):
                            self.__dict__.update(kwargs)
                    args_obj = ArgsObj(**config, source=config['input'], destination=config['output'])
                    m4b_path = cmd_mutate_convert(args_obj)
                    print(f"[SUCCESS] Created: {m4b_path}")
                    processed_count += 1

                except Exception as e:
                    print(f"[ERROR] Failed to process {folder_info['path']}: {e}")
                    continue

            print(f"[INFO] Series scan complete. Processed {processed_count}/{len(discovered_folders)} folders.")

        else:  # auto mode (default)
            print(f"[INFO] Auto-scanning directory for audiobook folders: {args.input}")
            discovered_folders = discover_audiobook_folders(args.input, max_depth=args.max_depth)

            if not discovered_folders:
                print("[INFO] No audiobook folders found.")
                return

            print(f"[INFO] Found {len(discovered_folders)} audiobook folder(s):")
            for folder in discovered_folders:
                print(f"  - {folder['path']} ({folder['type']}, {folder['audio_files']} files)")

            if args.dry_run:
                print("[INFO] Dry run - not processing folders.")
                return

            # Process each discovered folder
            processed_count = 0
            for folder_info in discovered_folders:
                try:
                    print(f"[INFO] Processing {folder_info['type']} folder: {folder_info['path']}")

                    # Create output path based on folder structure
                    folder_name = os.path.basename(folder_info['path'])
                    output_path = os.path.join(args.output, folder_name + '.m4b')

                    # Ensure output directory exists
                    os.makedirs(args.output, exist_ok=True)

                    config = {
                        'input': folder_info['path'],
                        'output': output_path,
                        'sort_by': args.sort_by,
                        'chapter_titles': args.chapter_titles,
                        'series_name': None,  # Will be auto-detected
                        'part_titles': args.part_titles,
                        'author_name': args.author_name,
                        'narrator_name': args.narrator_name,
                        'author_fix': args.author_fix,
                        'album_sort_prefix': args.album_sort_prefix,
                        'album_suffix': args.album_suffix,
                        'folder_type': folder_info['type']  # Use detected type
                    }

                    from audiobook_p.main import cmd_mutate_convert
                    class ArgsObj:
                        def __init__(self, **kwargs):
                            self.__dict__.update(kwargs)
                    args_obj = ArgsObj(**config, source=config['input'], destination=config['output'])
                    m4b_path = cmd_mutate_convert(args_obj)
                    print(f"[SUCCESS] Created: {m4b_path}")
                    processed_count += 1

                except Exception as e:
                    print(f"[ERROR] Failed to process {folder_info['path']}: {e}")
                    continue

            print(f"[INFO] Scan complete. Processed {processed_count}/{len(discovered_folders)} folders.")

        print(f"[INFO] Found {len(discovered_folders)} audiobook folder(s):")
        for folder in discovered_folders:
            print(f"  - {folder['path']} ({folder['type']}, {folder['audio_files']} files)")

        if args.dry_run:
            print("[INFO] Dry run - not processing folders.")
            return

        # Process each discovered folder
        processed_count = 0
        for folder_info in discovered_folders:
            try:
                print(f"[INFO] Processing {folder_info['type']} folder: {folder_info['path']}")

                # Create output path based on folder structure
                folder_name = os.path.basename(folder_info['path'])
                if folder_info['type'] == 'series':
                    # For series, create a subdirectory in output
                    output_path = os.path.join(args.output, folder_name + '.m4b')
                else:
                    # For novels, use the folder name directly
                    output_path = os.path.join(args.output, folder_name + '.m4b')

                # Ensure output directory exists
                os.makedirs(args.output, exist_ok=True)

                # Process the folder
                config = {
                    'input': folder_info['path'],
                    'output': output_path,
                    'sort_by': args.sort_by,
                    'chapter_titles': args.chapter_titles,
                    'series_name': None,  # Will be auto-detected
                    'part_titles': args.part_titles,
                    'author_name': args.author_name,
                    'narrator_name': args.narrator_name,
                    'author_fix': args.author_fix,
                    'album_sort_prefix': args.album_sort_prefix,
                    'album_suffix': args.album_suffix,
                    'folder_type': folder_info['type']  # Use detected type
                }

                from audiobook_p.main import cmd_mutate_convert
                class ArgsObj:
                    def __init__(self, **kwargs):
                        self.__dict__.update(kwargs)
                args_obj = ArgsObj(**config, source=config['input'], destination=config['output'])
                m4b_path = cmd_mutate_convert(args_obj)
                print(f"[SUCCESS] Created: {m4b_path}")
                processed_count += 1

            except Exception as e:
                print(f"[ERROR] Failed to process {folder_info['path']}: {e}")
                continue

        print(f"[INFO] Scan complete. Processed {processed_count}/{len(discovered_folders)} folders.")
    else:
        print("[ERROR] Unknown mode.")
        parser.print_help()

if __name__ == "__main__":
    main()
