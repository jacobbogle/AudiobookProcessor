"""
Audiobook Processor - Core Processing Operations
"""

import os
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Auto-install required packages
try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm


def process_folder(folder_path, title_name=None, author_name=None, bitrate=None, ffmpeg_path='ffmpeg', delete_combined=False, compress_originals=False, delete_originals=False, output_format='m4a', destination=None, combine_only=False, combine_all=False, metadata=False, cover_path=None, sort_as=None, min_files=1, sort_prefix_parent=False, sort_prefix_label=None, custom_prefix=None, custom_suffix=None, sort_as_prefix=None, album_prefix=None, album_suffix=None, title_suffix=None):
    """Process a folder: combine MP3s/M4A, convert format with metadata, or update metadata only."""
    folder_path = Path(folder_path)
    if not folder_path.exists():
        print(f"Folder not found: {folder_path}")
        return False

    # Check if this folder contains MP3 files directly
    mp3_files = sorted([str(f) for f in folder_path.glob('*.mp3')])

    # Also look for M4A files for metadata mode and combine_all
    m4a_files = []
    if combine_all or metadata:
        m4a_files = sorted([str(f) for f in folder_path.glob('*.m4a')])
        if combine_all and m4a_files:
            print(f"[COMBINE-ALL] Found {len(m4a_files)} M4A file(s) to include in combination")
            # For combine_all, we need to convert M4A back to WAV/MP3 for combining
            # Will be handled in the combining logic below
        elif metadata and m4a_files and not mp3_files:
            print(f"[METADATA] Found {len(m4a_files)} M4A file(s) for metadata update")

    # Check minimum file requirement (with special handling for certain modes)
    min_required = min_files
    if metadata:
        # Metadata mode can work with any number of files >= 1
        min_required = 1
    elif combine_only and len(mp3_files) >= 1:
        # Combine-only can work with 1+ files (single file just gets metadata applied)
        min_required = 1
    elif combine_all and len(mp3_files) + len(m4a_files) >= 1:
        # Combine-all can work with 1+ audio files (MP3 or M4A)
        min_required = 1

    # For combine-all/metadata with only M4A files, skip the MP3-only check
    if metadata:
        # Metadata mode works with any audio files (MP3 or M4A)
        if len(mp3_files) + len(m4a_files) < min_required:
            print(f"Folder {folder_path} has {len(mp3_files)} MP3 + {len(m4a_files)} M4A files, but minimum required for metadata mode is {min_required}")
            return False
    elif not combine_all and len(mp3_files) < min_required:
        mode_desc = "combine-only" if combine_only else "standard"
        print(f"Folder {folder_path} has {len(mp3_files)} MP3 files, but minimum required for {mode_desc} mode is {min_required}")
        return False

    # For combine-all with M4A files, allow processing
    if combine_all and len(mp3_files) + len(m4a_files) < min_required:
        print(f"Folder {folder_path} has {len(mp3_files)} MP3 + {len(m4a_files)} M4A files, but minimum required for combine-all mode is {min_required}")
        return False

    # If no audio files in current folder, check for subfolders with MP3 files (unless metadata mode with M4A files)
    if not mp3_files and not (combine_all and m4a_files) and not (metadata and m4a_files):
        print(f"No audio files found directly in: {folder_path}")
        print("Checking for subfolders with MP3 files...")

        # Find subfolders containing MP3 files
        mp3_subfolders = []
        for subfolder in folder_path.iterdir():
            if subfolder.is_dir():
                subfolder_mp3s = list(subfolder.glob('*.mp3'))
                if subfolder_mp3s:
                    mp3_subfolders.append((subfolder, subfolder_mp3s))

        if not mp3_subfolders:
            print(f"No MP3 files found in {folder_path} or its subfolders")
            return False

        # Process each subfolder separately
        print(f"Found {len(mp3_subfolders)} subfolders with MP3 files:")
        all_success = True

        for subfolder, subfolder_mp3s in mp3_subfolders:
            print(f"\n[FOLDER] Processing subfolder: {subfolder.name} ({len(subfolder_mp3s)} files)")

            # Recursively process this subfolder
            success = process_folder(
                str(subfolder),
                title_name=None,  # Use subfolder name
                author_name=author_name,  # Pass through author name
                bitrate=bitrate,
                ffmpeg_path=ffmpeg_path,
                delete_combined=delete_combined,
                compress_originals=compress_originals,
                delete_originals=delete_originals,
                output_format=output_format,
                destination=destination,
                combine_only=combine_only,
                combine_all=combine_all,
                metadata=metadata,
                cover_path=cover_path,
                sort_as=sort_as,
                min_files=min_files
            )

            if not success:
                print(f"[ERROR] Failed to process subfolder: {subfolder.name}")
                all_success = False
            else:
                print(f"[SUCCESS] Successfully processed subfolder: {subfolder.name}")

        return all_success

    print(f"Found {len(mp3_files)} MP3 files and {len(m4a_files)} M4A files in {folder_path}")

    # Handle metadata mode or format conversion
    if metadata or output_format == 'm4a':
        # Include all audio files for metadata update
        all_audio_files = mp3_files + m4a_files
        should_convert_to_m4a = (output_format == 'm4a') and len(mp3_files) > 0

        if should_convert_to_m4a:
            print(f"\n[METADATA] Updating metadata on {len(all_audio_files)} audio files and converting {len(mp3_files)} MP3 files to M4A")
        else:
            print(f"\n[METADATA] Updating metadata on {len(all_audio_files)} audio files without combining or converting")

        # Prepare metadata for the folder
        # Always use the original folder name for the album
        folder_name = folder_path.name
        from .utils import book_title_style
        tag_title, filename_base = book_title_style(folder_name)
        folder_title = tag_title        # For sort_title, use title_name if it includes parent prefix
        # (title_name is set by get_prefixed_title when prefix_parent/custom_prefix are used)
        if title_name:
            # For sort_title, use title_name as-is (don't strip book numbers like book_title_style does)
            # Just do basic formatting: normalize spaces and title case
            sort_title_base = ' '.join(title_name.strip().split())  # Normalize spaces
            # Apply simple title case without removing book numbers
            words = sort_title_base.split()
            sort_title_base = ' '.join(word.capitalize() for word in words)
        else:
            sort_title_base = folder_title  # Use original folder title if no prefix

        # Process each file with metadata
        success_count = 0
        total_files = len(all_audio_files)
        for track_index, audio_file in enumerate(all_audio_files, 1):
            audio_path = Path(audio_file)

            # Prepare file-specific metadata
            file_metadata = {}

            # Set title to filename (raw, without book_title_style processing for metadata mode)
            file_title = audio_path.stem
            file_metadata['title'] = file_title

            # Set album title - use original folder title
            album_title = folder_title

            # Apply album prefix/suffix if specified
            if album_prefix:
                album_title = f"{album_prefix}{album_title}"
            if album_suffix:
                album_title = f"{album_title} - {album_suffix}"

            file_metadata['album'] = album_title            # Set genre to Audiobook
            file_metadata['genre'] = 'Audiobook'

            # Set track number (chapter number)
            file_metadata['track_number'] = track_index
            file_metadata['total_tracks'] = total_files

            # Add author if specified
            if author_name:
                file_metadata['artist'] = author_name

            # Add cover if specified
            if cover_path:
                file_metadata['cover_path'] = cover_path

            # For metadata mode, use raw filename for sort title (no prefix logic)
            file_metadata['sort_title'] = file_title

            # Set album sort order (for iTunes album grouping/sorting)
            # Use the prefixed sort_title_base so the album sorts correctly as a group
            file_metadata['album_sort'] = sort_title_base

            # Extract existing metadata and merge
            try:
                from .metadata import extract_all_metadata
                existing_metadata = extract_all_metadata(str(audio_path))
                if existing_metadata:
                    temp_metadata = existing_metadata.copy()
                    # Don't override our explicitly set fields
                    for key in ['title', 'artist', 'album', 'genre']:
                        if key in file_metadata:
                            temp_metadata.pop(key, None)
                    file_metadata.update(temp_metadata)
            except Exception:
                pass

            print(f"[METADATA] Updating: {audio_path.name}")
            print(f"  Title: {file_metadata.get('title', 'N/A')}")
            print(f"  Artist: {file_metadata.get('artist', 'N/A')}")
            print(f"  Album: {file_metadata.get('album', 'N/A')}")

            # Store metadata for later (will be used if format conversion happens)
            # This metadata will be applied to converted files

            from .metadata import apply_mp3_metadata
            if apply_mp3_metadata(str(audio_path), file_metadata):
                success_count += 1
            else:
                print(f"[ERROR] Failed to update metadata for: {audio_file}")

        # Handle compression if requested (but skip if format conversion + destination - will be handled post-destination)
        should_convert_to_m4a = (output_format == 'm4a') and len(mp3_files) > 0
        skip_early_compression = should_convert_to_m4a and destination

        if compress_originals and success_count > 0 and not skip_early_compression:
            from .compression import compress_original_files
            compress_success, archive_path = compress_original_files(
                folder_path, mp3_files, title_name or folder_path.name, delete_originals
            )
            if compress_success:
                print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
            else:
                print(f"[WARNING] Compression failed")
        elif skip_early_compression:
            print(f"[COMPRESS] Deferring compression until after destination push...")

        print(f"\n[METADATA] Processing complete: {success_count}/{len(all_audio_files)} files updated successfully")

        # Define the final folder path for operations
        final_folder_path = Path(folder_path)
        conversion_success = 0

        # Handle format conversion if requested
        should_convert_to_m4a = (output_format == 'm4a') and len(mp3_files) > 0
        conversion_happened = False

        if should_convert_to_m4a:
            print(f"\n[CONVERT] Converting MP3 files to M4A format...")

            # Create a new directory for converted files
            conversion_output_dir = final_folder_path.parent / f"{final_folder_path.name}_m4a"
            if conversion_output_dir.exists():
                shutil.rmtree(conversion_output_dir)
            conversion_output_dir.mkdir(parents=True)

            conversion_success = 0
            for mp3_file in mp3_files:
                mp3_path = Path(mp3_file)
                m4a_file = conversion_output_dir / f"{mp3_path.stem}.m4a"

                # Extract metadata for this file
                from .metadata import extract_all_metadata
                file_metadata = extract_all_metadata(mp3_file) or {}

                # Set basic metadata
                file_metadata.update({
                    'title': mp3_path.stem,
                    'album': folder_title,
                    'genre': 'Audiobook'
                })

                from .converter import convert_to_m4a
                if convert_to_m4a(mp3_file, str(m4a_file), bitrate or '128k', file_metadata, ffmpeg_path):
                    conversion_success += 1
                    print(f"[CONVERT] ✅ {mp3_path.name} -> {m4a_file.name}")
                else:
                    print(f"[CONVERT] ❌ Failed: {mp3_path.name}")

            if conversion_success == len(mp3_files):
                print(f"[CONVERT] ✅ All {len(mp3_files)} MP3 files converted to M4A")
                conversion_happened = True
                final_folder_path = conversion_output_dir
            else:
                print(f"[CONVERT] ❌ Only {conversion_success}/{len(mp3_files)} MP3 files converted successfully")
                return False

        # Handle destination copying if requested
        if destination and conversion_happened:
            dest_path = Path(destination)
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy the converted folder to destination
            dest_folder = dest_path / final_folder_path.name
            if dest_folder.exists():
                shutil.rmtree(dest_folder)

            print(f"[DESTINATION] Copying to: {dest_folder}")
            shutil.copytree(final_folder_path, dest_folder)

            # Now handle compression if it was deferred
            if compress_originals and skip_early_compression:
                from .compression import compress_original_files
                compress_success, archive_path = compress_original_files(
                    folder_path, mp3_files, title_name or folder_path.name, delete_originals
                )
                if compress_success:
                    print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
                else:
                    print(f"[WARNING] Compression failed")

            # Clean up temporary conversion directory
            if conversion_happened and final_folder_path != folder_path:
                try:
                    shutil.rmtree(final_folder_path)
                    print(f"[CLEANUP] Removed temporary conversion directory")
                except Exception as e:
                    print(f"[WARNING] Could not remove temporary directory: {e}")

            final_folder_path = dest_folder

        # Handle deletion of combined MP3 if requested
        if delete_combined and conversion_happened:
            try:
                combined_mp3 = folder_path / f"{folder_path.name}.mp3"
                if combined_mp3.exists():
                    combined_mp3.unlink()
                    print(f"[DELETE] Removed combined MP3: {combined_mp3.name}")
            except Exception as e:
                print(f"[WARNING] Could not delete combined MP3: {e}")

        return True

    # Handle combining mode (combine_only or combine_all)
    if combine_only or combine_all:
        print(f"\n[COMBINE] Combining audio files...")

        # Determine which files to combine
        files_to_combine = mp3_files.copy()
        if combine_all and m4a_files:
            files_to_combine.extend(m4a_files)

        if len(files_to_combine) < 1:
            print(f"No audio files to combine in: {folder_path}")
            return False

        # Generate output filename
        if title_name:
            output_base = title_name
        else:
            output_base = folder_path.name

        from .utils import book_title_style
        tag_title, filename_base = book_title_style(output_base)

        # Apply title suffix if specified
        if title_suffix:
            from .utils import apply_title_suffix
            tag_title = apply_title_suffix(tag_title, title_suffix)

        output_filename = f"{filename_base}.mp3"
        output_file = folder_path / output_filename

        print(f"[COMBINE] Creating: {output_filename}")
        print(f"  Combining {len(files_to_combine)} files")
        print(f"  Title: {tag_title}")

        # Prepare metadata for combined file
        combined_metadata = {
            'title': tag_title,
            'album': tag_title,
            'genre': 'Audiobook'
        }

        if author_name:
            combined_metadata['artist'] = author_name

        if cover_path:
            combined_metadata['cover_path'] = cover_path

        # Add sort title for proper iTunes sorting
        if sort_as:
            combined_metadata['sort_title'] = sort_as
        elif sort_prefix_parent or custom_prefix:
            # Use prefixed title for album sort
            combined_metadata['sort_title'] = tag_title
        else:
            combined_metadata['sort_title'] = filename_base

        # Apply sort_as_prefix if specified
        if sort_as_prefix:
            combined_metadata['sort_title'] = f"{sort_as_prefix}{combined_metadata['sort_title']}"

        # Set album sort order
        combined_metadata['album_sort'] = combined_metadata['sort_title']

        # Combine the files
        from .metadata import combine_mp3_files_with_metadata
        success = combine_mp3_files_with_metadata(
            files_to_combine, str(output_file), bitrate or '128k', combined_metadata
        )

        if not success:
            print(f"[ERROR] Failed to combine files in: {folder_path}")
            return False

        print(f"[COMBINE] ✅ Created combined file: {output_filename}")

        # Handle compression if requested
        if compress_originals:
            from .compression import compress_original_files
            compress_success, archive_path = compress_original_files(
                folder_path, files_to_combine, title_name or folder_path.name, delete_originals
            )
            if compress_success:
                print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
            else:
                print(f"[WARNING] Compression failed")

        # Handle destination copying if requested
        if destination:
            dest_path = Path(destination)
            dest_path.mkdir(parents=True, exist_ok=True)

            # Copy the combined file to destination
            dest_file = dest_path / output_filename
            print(f"[DESTINATION] Copying to: {dest_file}")
            shutil.copy2(output_file, dest_file)

            # Clean up source if requested
            if delete_combined:
                try:
                    output_file.unlink()
                    print(f"[DELETE] Removed source combined file")
                except Exception as e:
                    print(f"[WARNING] Could not delete source file: {e}")

        return True

    # Standard processing mode: combine MP3s, convert to M4A, apply metadata
    print(f"\n[PROCESS] Standard processing mode")

    # Generate output filename
    if title_name:
        output_base = title_name
    else:
        output_base = folder_path.name

    from .utils import book_title_style
    tag_title, filename_base = book_title_style(output_base)

    # Apply title suffix if specified
    if title_suffix:
        from .utils import apply_title_suffix
        tag_title = apply_title_suffix(tag_title, title_suffix)

    output_filename = f"{filename_base}.mp3"
    output_file = folder_path / output_filename

    print(f"[PROCESS] Creating: {output_filename}")
    print(f"  Combining {len(mp3_files)} MP3 files")
    print(f"  Title: {tag_title}")

    # Prepare metadata for combined file
    combined_metadata = {
        'title': tag_title,
        'album': tag_title,
        'genre': 'Audiobook'
    }

    if author_name:
        combined_metadata['artist'] = author_name

    if cover_path:
        combined_metadata['cover_path'] = cover_path

    # Add sort title for proper iTunes sorting
    if sort_as:
        combined_metadata['sort_title'] = sort_as
    elif sort_prefix_parent or custom_prefix:
        # Use prefixed title for album sort
        combined_metadata['sort_title'] = tag_title
    else:
        combined_metadata['sort_title'] = filename_base

    # Apply sort_as_prefix if specified
    if sort_as_prefix:
        combined_metadata['sort_title'] = f"{sort_as_prefix}{combined_metadata['sort_title']}"

    # Set album sort order
    combined_metadata['album_sort'] = combined_metadata['sort_title']

    # Combine the MP3 files
    from .metadata import combine_mp3_files_with_metadata
    success = combine_mp3_files_with_metadata(
        mp3_files, str(output_file), bitrate or '128k', combined_metadata
    )

    if not success:
        print(f"[ERROR] Failed to process folder: {folder_path}")
        return False

    print(f"[PROCESS] ✅ Created combined file: {output_filename}")

    # Convert to M4A if requested
    if output_format == 'm4a':
        m4a_file = output_file.with_suffix('.m4a')
        print(f"[CONVERT] Converting to M4A: {m4a_file.name}")

        from .converter import convert_to_m4a
        if convert_to_m4a(str(output_file), str(m4a_file), bitrate or '128k', combined_metadata, ffmpeg_path):
            print(f"[CONVERT] ✅ Created M4A: {m4a_file.name}")

            # Delete combined MP3 if requested
            if delete_combined:
                try:
                    output_file.unlink()
                    print(f"[DELETE] Removed combined MP3")
                    output_file = m4a_file
                except Exception as e:
                    print(f"[WARNING] Could not delete combined MP3: {e}")
        else:
            print(f"[CONVERT] ❌ M4A conversion failed")
            return False

    # Handle compression if requested
    if compress_originals:
        from .compression import compress_original_files
        compress_success, archive_path = compress_original_files(
            folder_path, mp3_files, title_name or folder_path.name, delete_originals
        )
        if compress_success:
            print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
        else:
            print(f"[WARNING] Compression failed")

    # Handle destination copying if requested
    if destination:
        dest_path = Path(destination)
        dest_path.mkdir(parents=True, exist_ok=True)

        # Copy the final file to destination
        dest_file = dest_path / output_file.name
        print(f"[DESTINATION] Copying to: {dest_file}")
        shutil.copy2(output_file, dest_file)

        # Clean up source if requested
        if delete_combined:
            try:
                output_file.unlink()
                print(f"[DELETE] Removed source file")
            except Exception as e:
                print(f"[WARNING] Could not delete source file: {e}")

    return True


def process_multiple_folders(folders, bitrate=None, ffmpeg_path='ffmpeg', delete_combined=False, compress_originals=False, delete_originals=False, parallel=False, output_format='m4a', destination=None, author_name=None, combine_only=False, combine_all=False, metadata=False, cover_path=None, sort_as=None, sort_prefix_parent=False, sort_prefix_label=None, custom_prefix=None, custom_suffix=None, sort_as_prefix=None, album_prefix=None, album_suffix=None, title_suffix=None):
    """Process multiple folders, optionally in parallel."""
    if not folders:
        print("No folders to process")
        return False

    print(f"[BATCH] Processing {len(folders)} folders")
    if parallel:
        print("[BATCH] Using parallel processing")

    # Prepare common arguments for all folders
    common_args = {
        'bitrate': bitrate,
        'ffmpeg_path': ffmpeg_path,
        'delete_combined': delete_combined,
        'compress_originals': compress_originals,
        'delete_originals': delete_originals,
        'output_format': output_format,
        'destination': destination,
        'combine_only': combine_only,
        'combine_all': combine_all,
        'metadata': metadata,
        'cover_path': cover_path,
        'sort_as': sort_as,
        'sort_prefix_parent': sort_prefix_parent,
        'sort_prefix_label': sort_prefix_label,
        'custom_prefix': custom_prefix,
        'custom_suffix': custom_suffix,
        'sort_as_prefix': sort_as_prefix,
        'album_prefix': album_prefix,
        'album_suffix': album_suffix,
        'title_suffix': title_suffix
    }

    success_count = 0
    total_folders = len(folders)

    if parallel and len(folders) > 1:
        # Process folders in parallel
        max_workers = min(len(folders), 4)  # Limit to 4 concurrent workers

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_folder = {}
            for folder_path in folders:
                # Generate title for this folder
                folder_path_obj = Path(folder_path)
                if sort_prefix_parent or custom_prefix:
                    from .utils import get_prefixed_title
                    title_name = get_prefixed_title(
                        folder_path_obj, sort_prefix_parent, sort_prefix_label, custom_prefix
                    )
                else:
                    title_name = None

                args = common_args.copy()
                args.update({
                    'folder_path': folder_path,
                    'title_name': title_name,
                    'author_name': author_name
                })

                future = executor.submit(process_folder, **args)
                future_to_folder[future] = folder_path_obj.name

            # Collect results as they complete
            for future in as_completed(future_to_folder):
                folder_name = future_to_folder[future]
                try:
                    success = future.result()
                    if success:
                        print(f"[BATCH] ✅ Completed: {folder_name}")
                        success_count += 1
                    else:
                        print(f"[BATCH] ❌ Failed: {folder_name}")
                except Exception as e:
                    print(f"[BATCH] ❌ Error in {folder_name}: {e}")

    else:
        # Process folders sequentially
        for folder_path in folders:
            folder_path_obj = Path(folder_path)

            # Generate title for this folder
            if sort_prefix_parent or custom_prefix:
                from .utils import get_prefixed_title
                title_name = get_prefixed_title(
                    folder_path_obj, sort_prefix_parent, sort_prefix_label, custom_prefix
                )
            else:
                title_name = None

            print(f"\n[BATCH] Processing: {folder_path_obj.name}")

            success = process_folder(
                folder_path,
                title_name=title_name,
                author_name=author_name,
                **common_args
            )

            if success:
                success_count += 1
                print(f"[BATCH] ✅ Completed: {folder_path_obj.name}")
            else:
                print(f"[BATCH] ❌ Failed: {folder_path_obj.name}")

    print(f"\n[BATCH] Processing complete: {success_count}/{total_folders} folders processed successfully")
    return success_count == total_folders