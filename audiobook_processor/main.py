#!/usr/bin/env python3
"""
Audiobook Processor - Main Entry Point
Combines multiple MP3 files and converts to M4A
"""

import os
import sys
import argparse

# Import power management for long-running jobs
try:
    from power_manager import ProcessingSession
    POWER_MANAGEMENT_AVAILABLE = True
except ImportError:
    POWER_MANAGEMENT_AVAILABLE = False
    print("[WARNING]  Power management not available (power_manager.py not found)")

    # Create a dummy context manager for compatibility
    class ProcessingSession:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

from pathlib import Path
from .processor import process_multiple_folders, process_folder
from .metadata import process_metadata_command, process_convert_command, process_combine_command
from .utils import find_mp3_folders, get_prefixed_title, apply_title_suffix, ensure_ffmpeg_on_path
from .compression import compress_original_files


def main():
    parser = argparse.ArgumentParser(description='Audiobook Processor - Combine MP3s and convert to M4A')

    # Mode selection
    subparsers = parser.add_subparsers(dest='mode', help='Processing mode')

    # Batch processing mode (NEW)
    batch_parser = subparsers.add_parser('batch', help='Process multiple folders recursively')
    batch_parser.add_argument('root_path', help='Root directory to scan for folders with MP3 files')
    batch_parser.add_argument('-d', '--destination', help='Destination directory for processed files (default: same as source)')
    batch_parser.add_argument('-f', '--format', choices=['m4a', 'mp3'], default=None, help='Output format: m4a or mp3 (format conversion only applied if specified)')
    batch_parser.add_argument('-b', '--bitrate', default=None, help='Audio bitrate (e.g., 128k). If not specified, auto-detects from first MP3 file, defaults to 128k')
    batch_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    batch_parser.add_argument('--parallel', action='store_true', help='Process folders in parallel (faster but uses more resources)')
    batch_parser.add_argument('--min-files', type=int, default=2, help='Minimum number of MP3 files required to process a folder (default: 2)')
    batch_parser.add_argument('--batch-size', type=int, default=5, help='Number of folders to process simultaneously in each batch (default: 5)')
    batch_parser.add_argument('--compress-originals', action='store_true', help='Compress original MP3 files into ZIP archives')
    batch_parser.add_argument('--delete-originals', action='store_true', help='Delete original MP3 files after compression (requires --compress-originals)')
    batch_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    batch_parser.add_argument('--combine-mp3', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A')
    batch_parser.add_argument('--combine-all', action='store_true', help='Combine both MP3 and M4A files found in folder, process to final format')
    batch_parser.add_argument('--combine-only', action='store_true', help='[DEPRECATED] Use --combine-mp3 instead')
    batch_parser.add_argument('--metadata', action='store_true', help='Update metadata on MP3/M4A files without combining; use --format to convert format if needed')
    batch_parser.add_argument('-t', '--title-name', help='Title for the audiobook (also used as filename base). If not specified, uses folder name')
    batch_parser.add_argument('-a', '--author-name', help='Author/artist name for metadata')
    batch_parser.add_argument('-s', '--sort-as', help='Sort title for proper library ordering')
    batch_parser.add_argument('-c', '--cover', help='Path to cover image file (JPG/PNG) to embed')
    batch_parser.add_argument('--title-suffix', help='Custom suffix string to append to the end of titles')
    batch_parser.add_argument('--sort-prefix-parent', action='store_true', help='Prepend parent folder name to sort title (format: "ParentFolder : BookName")')
    batch_parser.add_argument('--sort-prefix-label', help='Label to prepend to parent folder in sort title (used with --sort-prefix-parent, separated by " : ")')
    batch_parser.add_argument('--custom-prefix', help='Custom prefix string to prepend to titles (used with --sort-prefix-parent or standalone)')
    batch_parser.add_argument('--custom-suffix', help='Custom suffix string to append to folder names')
    batch_parser.add_argument('--sort-as-prefix', help='Prefix string to prepend to the sort-as metadata field')
    batch_parser.add_argument('--album-prefix', help='Prefix string to prepend to the album metadata field')
    batch_parser.add_argument('--album-suffix', help='Suffix string to append to the album metadata field')

    # Folder processing mode
    folder_parser = subparsers.add_parser('folder', help='Process entire folder')
    folder_parser.add_argument('folder_path', help='Path to folder containing MP3 files')
    folder_parser.add_argument('-d', '--destination', help='Destination directory for processed files (default: same as source)')
    folder_parser.add_argument('-t', '--title-name', help='Title for the audiobook (also used as filename base)')
    folder_parser.add_argument('-a', '--author-name', help='Author/artist name for metadata')
    folder_parser.add_argument('-s', '--sort-as', help='Sort title for proper library ordering')
    folder_parser.add_argument('-c', '--cover', help='Path to cover image file (JPG/PNG) to embed')
    folder_parser.add_argument('--title-suffix', help='Custom suffix string to append to the end of titles')
    folder_parser.add_argument('-f', '--format', choices=['m4a', 'mp3'], default=None, help='Output format: m4a or mp3 (format conversion only applied if specified)')
    folder_parser.add_argument('-b', '--bitrate', default=None, help='Audio bitrate (e.g., 128k). If not specified, auto-detects from first MP3 file, defaults to 128k')
    folder_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    folder_parser.add_argument('--delete-combined', action='store_true', help='Delete combined MP3 after conversion')
    folder_parser.add_argument('--combine-mp3', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A')
    folder_parser.add_argument('--combine-all', action='store_true', help='Combine both MP3 and M4A files found in folder, process to final format')
    folder_parser.add_argument('--combine-only', action='store_true', help='[DEPRECATED] Use --combine-mp3 instead')
    folder_parser.add_argument('--metadata', action='store_true', help='Update metadata on MP3/M4A files without combining; use --format to convert format if needed')
    folder_parser.add_argument('--compress-originals', action='store_true', help='Compress original MP3 files into ZIP archive')
    folder_parser.add_argument('--delete-originals', action='store_true', help='Delete original MP3 files after compression (requires --compress-originals)')
    folder_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    folder_parser.add_argument('--min-files', type=int, default=1, help='Minimum number of MP3 files required to process folder (default: 1)')
    folder_parser.add_argument('--sort-prefix-parent', action='store_true', help='Prepend parent folder name to sort title (format: "ParentFolder : BookName")')
    folder_parser.add_argument('--sort-prefix-label', help='Label to prepend to parent folder in sort title (used with --sort-prefix-parent, separated by " : ")')
    folder_parser.add_argument('--custom-prefix', help='Custom prefix string to prepend to titles (used with --sort-prefix-parent or standalone)')
    folder_parser.add_argument('--custom-suffix', help='Custom suffix string to append to folder names')
    folder_parser.add_argument('--sort-as-prefix', help='Prefix string to prepend to the sort-as metadata field')
    folder_parser.add_argument('--album-prefix', help='Prefix string to prepend to the album metadata field')
    folder_parser.add_argument('--album-suffix', help='Suffix string to append to the album metadata field')

    # File processing mode (combine or convert based on number of files)
    file_parser = subparsers.add_parser('file', help='Process files: combine multiple MP3s or convert single MP3 to M4A')
    file_parser.add_argument('files', nargs='+', help='MP3 file(s) to process. Multiple files = combine, single file = convert to M4A')
    file_parser.add_argument('-t', '--title-name', help='Title for the output (also used as filename base). If not specified, uses first input filename')
    file_parser.add_argument('-a', '--author-name', help='Author/artist name for metadata')
    file_parser.add_argument('-s', '--sort-as', help='Sort title for proper library ordering')
    file_parser.add_argument('-c', '--cover', help='Path to cover image file (JPG/PNG) to embed')
    file_parser.add_argument('--title-suffix', help='Custom suffix string to append to the end of titles')
    file_parser.add_argument('-d', '--destination', help='Destination directory for output file (default: same as first input file)')
    file_parser.add_argument('-b', '--bitrate', default=None, help='Audio bitrate (e.g., 128k). If not specified, auto-detects from first MP3 file, defaults to 128k')
    file_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    file_parser.add_argument('--delete-combined', action='store_true', help='Delete combined MP3 after M4A conversion (combine mode only)')
    file_parser.add_argument('--combine-mp3', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A (combine mode only)')
    file_parser.add_argument('--combine-all', action='store_true', help='Combine both MP3 and M4A files, process to final format')
    file_parser.add_argument('--combine-only', action='store_true', help='[DEPRECATED] Use --combine-mp3 instead')
    file_parser.add_argument('--metadata', action='store_true', help='Update metadata on MP3/M4A files; use --format to convert format if needed')
    file_parser.add_argument('--compress-origin', action='store_true', help='Compress original MP3 files into ZIP archive')
    file_parser.add_argument('--delete-origin', action='store_true', help='Delete original files after processing/compression (requires --compress-origin)')
    file_parser.add_argument('--metadata-json', help='Optional JSON file with metadata (convert mode only)')
    file_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')

    # Metadata-only mode (update metadata without combining or converting)
    metadata_parser = subparsers.add_parser('metadata', help='Update metadata on existing MP3 files (no combining or converting)')
    metadata_parser.add_argument('files', nargs='+', help='MP3 file(s) to update metadata on')
    metadata_parser.add_argument('-t', '--title', help='Title for the MP3 file(s)')
    metadata_parser.add_argument('-a', '--author', help='Author/artist name for metadata')
    metadata_parser.add_argument('-l', '--album', help='Album name for metadata')
    metadata_parser.add_argument('-g', '--genre', help='Genre for metadata (default: Audiobook)')
    metadata_parser.add_argument('-y', '--year', help='Year/date for metadata')
    metadata_parser.add_argument('-s', '--sort-as', help='Sort title for proper library ordering')
    metadata_parser.add_argument('-c', '--cover', help='Path to cover image file (JPG/PNG) to embed')
    metadata_parser.add_argument('--metadata-json', help='JSON file with complete metadata to apply')
    metadata_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        return

    # Handle backward compatibility: --combine-only is now --combine-mp3
    if hasattr(args, 'combine_only') and args.combine_only:
        print("[WARNING] --combine-only is deprecated. Use --combine-mp3 instead.")
        args.combine_mp3 = True

    # Rename combine_mp3 to combine_only for internal use (for backward compat with rest of code)
    if hasattr(args, 'combine_mp3'):
        combine_only = args.combine_mp3
    else:
        combine_only = getattr(args, 'combine_only', False)

    # Handle combine_all: set combine_only but allow M4A combining
    combine_all = getattr(args, 'combine_all', False)

    # Set up ffmpeg (only for modes that need it)
    if hasattr(args, 'ffmpeg_path'):
        ensure_ffmpeg_on_path(args.ffmpeg_path)

    if args.mode == 'batch':
        # Smart detection: Check if root path itself contains MP3 files
        root_path = Path(args.root_path)
        root_mp3_files = list(root_path.glob('*.mp3'))

        if len(root_mp3_files) >= args.min_files:
            # Root path contains MP3 files directly - process as single folder
            print(f"[FOLDER] Detected MP3 files directly in: {root_path}")
            print(f"         Found {len(root_mp3_files)} MP3 files - processing as single audiobook")
            mp3_folders = [root_path]
        else:
            # Find all folders with MP3 files (or MP3/M4A files if combine_all or metadata is enabled)
            mp3_folders = find_mp3_folders(args.root_path, args.min_files, include_m4a=(combine_all or getattr(args, 'metadata', False)))

        if not mp3_folders:
            file_type = "MP3/M4A" if (combine_all or getattr(args, 'metadata', False)) else "MP3"
            print(f"No folders with {args.min_files}+ {file_type} files found in: {args.root_path}")
            if len(root_mp3_files) > 0:
                print(f"Found {len(root_mp3_files)} MP3 files in root, but need at least {args.min_files}")
            sys.exit(1)

        print(f"\nFound {len(mp3_folders)} folders to process:")
        for folder in mp3_folders:
            mp3_count = len(list(folder.glob('*.mp3')))
            print(f"  [FOLDER] {folder} ({mp3_count} files)")

        # Validate compression options
        # Allow delete-originals without compress-originals when using destination + format conversion
        destination_with_conversion = args.destination and args.format == 'm4a'
        if args.delete_originals and not args.compress_originals and not destination_with_conversion:
            print("[ERROR] --delete-originals requires --compress-originals (unless using --destination with --format m4a)")
            sys.exit(1)

        # Ask for confirmation before proceeding (unless auto-confirm is enabled)
        auto_confirm = os.environ.get('AUDIOBOOK_AUTO_CONFIRM', '0') == '1'

        if not auto_confirm:
            try:
                confirm = input(f"\nProcess all {len(mp3_folders)} folders? [Y/n]: ").strip().lower()
                if confirm and confirm not in ['y', 'yes']:
                    print("Operation cancelled.")
                    sys.exit(0)
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                sys.exit(0)
        else:
            print(f"\n[AUTO] Auto-confirming processing of {len(mp3_folders)} folders...")

        print("\n[NOTE] Note: Combined MP3 files will be automatically deleted after conversion to save disk space.")
        if args.compress_originals:
            print("[COMPRESS] Note: Original MP3 files will be compressed into ZIP archives.")
            if args.delete_originals:
                print("[DELETE] Note: Original MP3 files will be deleted after compression.")

        # Split folders into batches
        batch_size = args.batch_size
        total_folders = len(mp3_folders)
        num_batches = (total_folders + batch_size - 1) // batch_size  # Ceiling division

        print(f"\n[BATCH] Processing {total_folders} folders in {num_batches} batches of up to {batch_size} folders each")

        # Create batches
        folder_batches = []
        for i in range(0, total_folders, batch_size):
            batch = mp3_folders[i:i + batch_size]
            folder_batches.append(batch)

        # Use power management for long-running batch processing
        use_power_management = POWER_MANAGEMENT_AVAILABLE and (
            args.long_running or total_folders > 3
        )

        if use_power_management:
            print("[POWER] Starting long-running session with power management...")

        # Process all batches
        all_results = {}

        if use_power_management:
            with ProcessingSession(f"batch_{total_folders}_folders") as session:
                session.log_message("BATCH_START", f"Processing {total_folders} folders in {num_batches} batches")

                for batch_idx, batch_folders in enumerate(folder_batches, 1):
                    print(f"\n{'='*80}")
                    print(f"BATCH {batch_idx}/{num_batches}: Processing {len(batch_folders)} folders")
                    print(f"{'='*80}")

                    session.log_message(f"BATCH_{batch_idx}_START", f"Processing batch {batch_idx}/{num_batches} with {len(batch_folders)} folders")

                    # Process this batch
                    batch_results = process_multiple_folders(
                        batch_folders,
                        bitrate=args.bitrate,
                        ffmpeg_path=args.ffmpeg_path,
                        delete_combined=True,  # Always delete combined files in batch mode
                        compress_originals=args.compress_originals,
                        delete_originals=args.delete_originals,
                        parallel=args.parallel,
                        output_format=args.format,
                        destination=args.destination,
                        author_name=getattr(args, 'author_name', None),
                        combine_only=getattr(args, 'combine_only', False),
                        combine_all=combine_all,
                        metadata=getattr(args, 'metadata', False),
                        cover_path=getattr(args, 'cover', None),
                        sort_as=getattr(args, 'sort_as', None),
                        sort_prefix_parent=getattr(args, 'sort_prefix_parent', False),
                        sort_prefix_label=getattr(args, 'sort_prefix_label', None),
                        custom_prefix=getattr(args, 'custom_prefix', None),
                        custom_suffix=getattr(args, 'custom_suffix', None),
                        sort_as_prefix=getattr(args, 'sort_as_prefix', None),
                        album_prefix=getattr(args, 'album_prefix', None),
                        album_suffix=getattr(args, 'album_suffix', None),
                        title_suffix=getattr(args, 'title_suffix', None)
                    )

                    # Add batch results to overall results
                    all_results.update(batch_results)

                    successful_in_batch = len([folder for folder, success in batch_results.items() if success])
                    session.log_message(f"BATCH_{batch_idx}_COMPLETE", f"Batch {batch_idx}: {successful_in_batch}/{len(batch_results)} folders successful")

                    print(f"[BATCH] Completed batch {batch_idx}/{num_batches}: {successful_in_batch}/{len(batch_results)} successful")

                total_successful = len([folder for folder, success in all_results.items() if success])
                session.log_message("BATCH_COMPLETE", f"All batches complete: {total_successful}/{len(all_results)} folders successful")
        else:
            # Process without power management
            for batch_idx, batch_folders in enumerate(folder_batches, 1):
                print(f"\n{'='*80}")
                print(f"BATCH {batch_idx}/{num_batches}: Processing {len(batch_folders)} folders")
                print(f"{'='*80}")

                # Process this batch
                batch_results = process_multiple_folders(
                    batch_folders,
                    bitrate=args.bitrate,
                    ffmpeg_path=args.ffmpeg_path,
                    delete_combined=True,  # Always delete combined files in batch mode
                    compress_originals=args.compress_originals,
                    delete_originals=args.delete_originals,
                    parallel=args.parallel,
                    output_format=args.format,
                    destination=args.destination,
                    author_name=getattr(args, 'author_name', None),
                    combine_only=getattr(args, 'combine_only', False),
                    combine_all=combine_all,
                    metadata=getattr(args, 'metadata', False),
                    cover_path=getattr(args, 'cover', None),
                    sort_as=getattr(args, 'sort_as', None),
                    sort_prefix_parent=getattr(args, 'sort_prefix_parent', False),
                    sort_prefix_label=getattr(args, 'sort_prefix_label', None),
                    custom_prefix=getattr(args, 'custom_prefix', None),
                    custom_suffix=getattr(args, 'custom_suffix', None),
                    sort_as_prefix=getattr(args, 'sort_as_prefix', None),
                    album_prefix=getattr(args, 'album_prefix', None),
                    album_suffix=getattr(args, 'album_suffix', None),
                    title_suffix=getattr(args, 'title_suffix', None)
                )

                # Add batch results to overall results
                all_results.update(batch_results)

                successful_in_batch = len([folder for folder, success in batch_results.items() if success])
                print(f"[BATCH] Completed batch {batch_idx}/{num_batches}: {successful_in_batch}/{len(batch_results)} successful")

        # Use all_results instead of results for the summary
        results = all_results

        # Print summary
        print(f"\n{'='*80}")
        print("BATCH PROCESSING SUMMARY")
        print(f"{'='*80}")

        successful = [folder for folder, success in results.items() if success]
        failed = [folder for folder, success in results.items() if not success]

        print(f"[SUCCESS] Successfully processed: {len(successful)}/{len(results)} folders")
        if successful:
            for folder in successful:
                print(f"   [FOLDER] {folder}")

        if failed:
            print(f"\n[ERROR] Failed to process: {len(failed)} folders")
            for folder in failed:
                print(f"   [FOLDER] {folder}")

        print(f"\n[COMPLETE] Batch processing complete!")
        sys.exit(0 if not failed else 1)

    elif args.mode == 'folder':
        # Validate compression options
        # Allow delete-originals without compress-originals when using destination + format conversion
        destination_with_conversion = args.destination and args.format == 'm4a'
        if args.delete_originals and not args.compress_originals and not destination_with_conversion:
            print("[ERROR] Error: --delete-originals requires --compress-originals (unless using --destination with --format m4a)")
            sys.exit(1)

        # Generate title with prefix if requested (like in batch mode)
        sort_prefix_parent = getattr(args, 'sort_prefix_parent', False)
        sort_prefix_label = getattr(args, 'sort_prefix_label', None)
        custom_prefix = getattr(args, 'custom_prefix', None)

        title_name = args.title_name
        if sort_prefix_parent or custom_prefix:
            title_name = get_prefixed_title(args.folder_path, sort_prefix_parent=sort_prefix_parent, sort_prefix_label=sort_prefix_label, custom_prefix=custom_prefix)
            print(f"[TITLE] Generated title with prefix: {title_name}")

        # Check if power management should be used
        use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running

        if use_power_management:
            print("[POWER] Starting long-running session with power management...")
            with ProcessingSession("folder_processing") as session:
                session.log_message("FOLDER_START", f"Processing folder: {args.folder_path}")
                success = process_folder(
                    args.folder_path,
                    title_name,  # Use generated title_name
                    args.author_name,
                    args.bitrate,
                    args.ffmpeg_path,
                    args.delete_combined,
                    args.compress_originals,
                    args.delete_originals,
                    args.format,
                    args.destination,
                    combine_only=getattr(args, 'combine_only', False),
                    combine_all=combine_all,
                    metadata=getattr(args, 'metadata', False),
                    cover_path=getattr(args, 'cover', None),
                    sort_as=getattr(args, 'sort_as', None),
                    min_files=args.min_files,
                    sort_prefix_parent=sort_prefix_parent,
                    sort_prefix_label=sort_prefix_label,
                    custom_prefix=custom_prefix,
                    custom_suffix=getattr(args, 'custom_suffix', None),
                    sort_as_prefix=getattr(args, 'sort_as_prefix', None),
                    album_prefix=getattr(args, 'album_prefix', None),
                    album_suffix=getattr(args, 'album_suffix', None),
                    title_suffix=getattr(args, 'title_suffix', None)
                )
                session.log_message("FOLDER_COMPLETE", f"Folder processing {'successful' if success else 'failed'}")
        else:
            success = process_folder(
                args.folder_path,
                title_name,  # Use generated title_name
                args.author_name,
                args.bitrate,
                args.ffmpeg_path,
                args.delete_combined,
                args.compress_originals,
                args.delete_originals,
                args.format,
                args.destination,
                combine_only=getattr(args, 'combine_only', False),
                combine_all=combine_all,
                metadata=getattr(args, 'metadata', False),
                cover_path=getattr(args, 'cover', None),
                sort_as=getattr(args, 'sort_as', None),
                min_files=args.min_files,
                sort_prefix_parent=sort_prefix_parent,
                sort_prefix_label=sort_prefix_label,
                custom_prefix=custom_prefix,
                custom_suffix=getattr(args, 'custom_suffix', None),
                sort_as_prefix=getattr(args, 'sort_as_prefix', None),
                album_prefix=getattr(args, 'album_prefix', None),
                album_suffix=getattr(args, 'album_suffix', None),
                title_suffix=getattr(args, 'title_suffix', None)
            )
        sys.exit(0 if success else 1)

    elif args.mode == 'file':
        # Validate compression options
        if getattr(args, 'delete_origin', False) and not getattr(args, 'compress_origin', False):
            print("[ERROR] Error: --delete-origin requires --compress-origin")
            sys.exit(1)

        # Check if metadata mode
        if getattr(args, 'metadata', False):
            print(f"[MODE] Metadata mode - updating metadata on {len(args.files)} files")

            # Check if power management should be used
            use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running

            if use_power_management:
                print("[POWER] Starting long-running session with power management...")
                with ProcessingSession("file_metadata_processing") as session:
                    session.log_message("METADATA_START", f"Updating metadata on {len(args.files)} files")
                    success = process_metadata_command(args)
                    session.log_message("METADATA_COMPLETE", f"Metadata processing {'successful' if success else 'failed'}")
            else:
                success = process_metadata_command(args)

            sys.exit(0 if success else 1)

        # Determine mode based on number of files
        if len(args.files) == 1:
            # Single file - convert mode
            print(f"[MODE] Single file detected - converting to M4A")
            # Set up args for convert mode
            args.input = args.files[0]
            if not args.title_name:
                # Default output name for convert
                input_path = Path(args.files[0])
                args.title_name = input_path.stem  # Use filename without extension as title

            # Apply title suffix if provided
            title_suffix = getattr(args, 'title_suffix', None)
            if title_suffix:
                args.title_name = apply_title_suffix(args.title_name, title_suffix)
                print(f"[TITLE] Applied suffix '{title_suffix}' - Final title: {args.title_name}")

            # For convert mode, title_name becomes the output filename
            args.output = args.title_name + '.m4a'

            # Set default bitrate if not specified
            if args.bitrate is None:
                args.bitrate = '128k'

            # Check if power management should be used
            use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running

            if use_power_management:
                print("[POWER] Starting long-running session with power management...")
                with ProcessingSession("convert_processing") as session:
                    session.log_message("CONVERT_START", f"Converting file: {args.input}")
                    success = process_convert_command(args)
                    session.log_message("CONVERT_COMPLETE", f"Convert processing {'successful' if success else 'failed'}")
            else:
                success = process_convert_command(args)

            # Handle compression if requested
            if success and getattr(args, 'compress_origin', False):
                print("[COMPRESS] Compressing original file...")
                input_dir = str(Path(args.input).parent)
                compress_success, archive_path = compress_original_files(
                    input_dir, [args.input], args.title_name or Path(args.input).stem,
                    delete_originals=getattr(args, 'delete_origin', False)
                )
                if compress_success:
                    print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
                else:
                    print("[WARNING] Compression failed")
        else:
            # Multiple files - combine mode
            print(f"[MODE] Multiple files detected - combining {len(args.files)} files")

            # Apply title suffix if provided
            title_suffix = getattr(args, 'title_suffix', None)
            if title_suffix and args.title_name:
                args.title_name = apply_title_suffix(args.title_name, title_suffix)
                print(f"[TITLE] Applied suffix '{title_suffix}' - Final title: {args.title_name}")

            # Handle title_name for output filename
            if args.title_name:
                args.output = args.title_name + '.m4a'

            # Set default bitrate if not specified
            if args.bitrate is None:
                args.bitrate = '128k'

            # Check if power management should be used
            use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running

            if use_power_management:
                print("[POWER] Starting long-running session with power management...")
                with ProcessingSession("combine_processing") as session:
                    session.log_message("COMBINE_START", f"Combining {len(args.files)} files")
                    success = process_combine_command(args)
                    session.log_message("COMBINE_COMPLETE", f"Combine processing {'successful' if success else 'failed'}")
            else:
                success = process_combine_command(args)

            # Handle compression if requested
            if success and getattr(args, 'compress_origin', False):
                print("[COMPRESS] Compressing original files...")
                input_dir = str(Path(args.files[0]).parent)
                compress_success, archive_path = compress_original_files(
                    input_dir, args.files, args.title_name or Path(args.files[0]).stem,
                    delete_originals=getattr(args, 'delete_origin', False)
                )
                if compress_success:
                    print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
                else:
                    print("[WARNING] Compression failed")
        sys.exit(0 if success else 1)

    elif args.mode == 'metadata':
        # Check if power management should be used
        use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running

        if use_power_management:
            print("[POWER] Starting long-running session with power management...")
            with ProcessingSession("metadata_processing") as session:
                session.log_message("METADATA_START", f"Updating metadata on {len(args.files)} files")
                success = process_metadata_command(args)
                session.log_message("METADATA_COMPLETE", f"Metadata processing {'successful' if success else 'failed'}")
        else:
            success = process_metadata_command(args)
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()