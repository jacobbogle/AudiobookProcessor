"""
Audiobook Processor - Metadata Operations
"""

import os
import re
import json
import tempfile
import subprocess
import shutil
from pathlib import Path

# Auto-install required packages
try:
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TCON, TSOT, APIC, TXXX, TRCK
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen import File as MutagenFile
except ImportError:
    print("mutagen not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3, ID3NoHeaderError, TIT2, TPE1, TALB, TDRC, TCON, TSOT, APIC, TXXX, TRCK
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen import File as MutagenFile


def extract_all_metadata(mp3_file):
    """Extract metadata, cover art, and chapters from an audio file (MP3 or M4A).

    Handles both MP3 (ID3 tags) and M4A/MP4 (iTunes tags) formats.
    """
    metadata = {}
    file_ext = Path(mp3_file).suffix.lower()

    # Try M4A/MP4 format first if the file is M4A
    if file_ext in ['.m4a', '.mp4', '.m4b']:
        try:
            mp4 = MP4(mp3_file)

            # Duration
            if hasattr(mp4.info, 'length'):
                metadata['duration_ms'] = int(mp4.info.length * 1000)

            # Text metadata
            if '\xa9nam' in mp4:  # Title
                metadata['title'] = str(mp4['\xa9nam'][0])
            if '\xa9ART' in mp4:  # Artist
                metadata['artist'] = str(mp4['\xa9ART'][0])
            if '\xa9alb' in mp4:  # Album
                metadata['album'] = str(mp4['\xa9alb'][0])
            if '\xa9day' in mp4:  # Date
                metadata['date'] = str(mp4['\xa9day'][0])
            if '\xa9gen' in mp4:  # Genre
                metadata['genre'] = str(mp4['\xa9gen'][0])

            # Cover art from M4A
            if 'covr' in mp4:
                cover_data = bytes(mp4['covr'][0])
                # Determine cover format (JPEG by default for M4A)
                ext = '.jpg'  # M4A covers are typically JPEG
                cover_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                cover_file.write(cover_data)
                cover_file.close()
                metadata['cover_path'] = cover_file.name
                print(f"[COVER] Extracted M4A cover art from {Path(mp3_file).name}")

            return metadata
        except Exception as e:
            print(f"[DEBUG] M4A metadata extraction failed: {e}")
            # Fall through to MP3 extraction

    # Try MP3 format
    try:
        # Basic metadata
        try:
            audio = MP3(mp3_file)
            if audio and hasattr(audio.info, 'length'):
                metadata['duration_ms'] = int(audio.info.length * 1000)
        except Exception:
            pass

        # ID3 tags
        try:
            id3 = ID3(mp3_file)

            # Text frames
            if 'TIT2' in id3:
                metadata['title'] = str(id3['TIT2'].text[0])
            if 'TPE1' in id3:
                metadata['artist'] = str(id3['TPE1'].text[0])
            if 'TALB' in id3:
                metadata['album'] = str(id3['TALB'].text[0])
            if 'TDRC' in id3:
                metadata['date'] = str(id3['TDRC'].text[0])
            if 'TCON' in id3:
                metadata['genre'] = str(id3['TCON'].text[0])

            # Cover art
            apics = id3.getall('APIC')
            if apics:
                cover_data = apics[0].data
                ext = '.jpg' if apics[0].mime == 'image/jpeg' else '.png'
                cover_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                cover_file.write(cover_data)
                cover_file.close()
                metadata['cover_path'] = cover_file.name
                print(f"[COVER] Extracted MP3 cover art from {Path(mp3_file).name}")

            # Chapters
            chapters = []
            chaps = id3.getall('CHAP')
            for chap in chaps:
                chapter = {
                    'start_ms': getattr(chap, 'start_time', 0),
                    'end_ms': getattr(chap, 'end_time', 0)
                }
                # Try to get chapter title
                if hasattr(chap, 'sub_frames'):
                    for frame in chap.sub_frames:
                        if frame.FrameID == 'TIT2':
                            chapter['title'] = str(frame.text[0])
                            break
                chapters.append(chapter)
            if chapters:
                metadata['chapters'] = chapters

        except Exception:
            pass

        return metadata
    except Exception:
        return {}


def apply_mp3_metadata(mp3_file, metadata):
    """Apply metadata to an audio file (MP3 or M4A) using mutagen.

    Automatically detects file format and applies appropriate metadata tags.
    Supports ID3 tags for MP3 and iTunes tags for M4A/MP4.
    """
    file_ext = Path(mp3_file).suffix.lower()

    # Handle M4A/MP4 files
    if file_ext in ['.m4a', '.mp4', '.m4b']:
        try:
            mp4 = MP4(mp3_file)

            # Text metadata
            if metadata.get('title'):
                mp4['\xa9nam'] = [str(metadata['title'])]

            if metadata.get('artist'):
                mp4['\xa9ART'] = [str(metadata['artist'])]

            if metadata.get('album'):
                mp4['\xa9alb'] = [str(metadata['album'])]

            if metadata.get('date'):
                mp4['\xa9day'] = [str(metadata['date'])]

            if metadata.get('genre'):
                mp4['\xa9gen'] = [str(metadata['genre'])]

            # Sort title (for proper library ordering)
            if metadata.get('sort_title'):
                mp4['sonm'] = [str(metadata['sort_title'])]

            # Album sort order (for proper album ordering in iTunes)
            if metadata.get('album_sort'):
                mp4['soal'] = [str(metadata['album_sort'])]

            # Track number (chapter number for audiobooks)
            if metadata.get('track_number'):
                track_num = int(metadata['track_number'])
                total_tracks = int(metadata.get('total_tracks', 0))
                if total_tracks > 0:
                    mp4['trkn'] = [(track_num, total_tracks)]
                else:
                    mp4['trkn'] = [(track_num, 0)]

            # Mark as audiobook
            try:
                mp4['stik'] = [2]  # Audiobook
            except Exception:
                pass

            # Add cover art if available
            if metadata.get('cover_path'):
                try:
                    with open(metadata['cover_path'], 'rb') as cover_file:
                        cover_data = cover_file.read()
                        # Determine image type from file extension
                        fmt = MP4Cover.FORMAT_JPEG if metadata['cover_path'].lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
                        mp4['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
                        print(f"[COVER] Applied cover art to M4A: {Path(mp3_file).name}")
                except Exception as e:
                    print(f"[WARNING] Could not add M4A cover art: {e}")

            mp4.save()
            print(f"[METADATA] Applied metadata to M4A: {Path(mp3_file).name}")
            return True

        except Exception as e:
            print(f"[ERROR] Error applying M4A metadata: {e}")
            return False

    # Handle MP3 files (original logic)
    try:
        # Load or create ID3 tags
        try:
            id3 = ID3(mp3_file)
        except ID3NoHeaderError:
            id3 = ID3()

        # Apply metadata
        if metadata.get('title'):
            id3['TIT2'] = TIT2(encoding=3, text=metadata['title'])

        if metadata.get('artist'):
            id3['TPE1'] = TPE1(encoding=3, text=metadata['artist'])

        if metadata.get('album'):
            id3['TALB'] = TALB(encoding=3, text=metadata['album'])

        if metadata.get('date'):
            id3['TDRC'] = TDRC(encoding=3, text=metadata['date'])

        if metadata.get('genre'):
            id3['TCON'] = TCON(encoding=3, text=metadata['genre'])

        # Sort title (for proper library ordering)
        if metadata.get('sort_title'):
            id3['TSOT'] = TSOT(encoding=3, text=metadata['sort_title'])

        # Album sort order (for proper album ordering in iTunes)
        if metadata.get('album_sort'):
            id3['TXXX:ALBUMSORT'] = TXXX(encoding=3, desc='ALBUMSORT', text=metadata['album_sort'])

        # Track number (chapter number for audiobooks)
        if metadata.get('track_number'):
            track_num = int(metadata['track_number'])
            total_tracks = int(metadata.get('total_tracks', 0))
            if total_tracks > 0:
                id3['TRCK'] = TRCK(encoding=3, text=f"{track_num}/{total_tracks}")
            else:
                id3['TRCK'] = TRCK(encoding=3, text=str(track_num))

        # iTunes audiobook-specific metadata
        # Media Kind is automatically set to Audiobook when genre is "Audiobook"
        # Remember playback position (enabled by default for audiobooks)
        id3['TXXX:iTunMOVI'] = TXXX(encoding=3, desc='iTunMOVI', text='1')

        # Skip when shuffling (recommended for audiobooks)
        id3['TXXX:iTunesSkipWhenShuffling'] = TXXX(encoding=3, desc='iTunesSkipWhenShuffling', text='1')

        # Add cover art if available
        if metadata.get('cover_path'):
            try:
                with open(metadata['cover_path'], 'rb') as cover_file:
                    cover_data = cover_file.read()
                    # Determine image type
                    if metadata['cover_path'].lower().endswith('.png'):
                        mime_type = 'image/png'
                    else:
                        mime_type = 'image/jpeg'

                    id3['APIC'] = APIC(
                        encoding=3,
                        mime=mime_type,
                        type=3,  # Cover (front)
                        desc='Cover',
                        data=cover_data
                    )
                print(f"[COVER] Applied cover art to MP3: {Path(mp3_file).name}")
            except Exception as e:
                print(f"[WARNING] Could not add MP3 cover art: {e}")

        # Save the tags
        id3.save(mp3_file)
        print(f"[METADATA] Applied metadata to MP3: {Path(mp3_file).name}")
        return True

    except Exception as e:
        print(f"[ERROR] Error applying MP3 metadata: {e}")
        return False


def write_ffmetadata(metadata, out_path):
    """Write ffmpeg metadata file for chapters and other metadata."""
    if not metadata.get('chapters'):
        return None

    md_path = out_path + '.metadata.txt'
    try:
        with open(md_path, 'w', encoding='utf-8') as f:
            # Write basic metadata
            if metadata.get('title'):
                f.write(f"title={metadata['title']}\n")
            if metadata.get('artist'):
                f.write(f"artist={metadata['artist']}\n")
            if metadata.get('album'):
                f.write(f"album={metadata['album']}\n")

            # Write chapters
            for i, chapter in enumerate(metadata['chapters']):
                start_time = chapter.get('start_ms', 0) / 1000.0
                end_time = chapter.get('end_ms', 0) / 1000.0
                title = chapter.get('title', f'Chapter {i+1}')

                f.write('[CHAPTER]\n')
                f.write('TIMEBASE=1/1000\n')
                f.write(f'START={int(start_time * 1000)}\n')
                f.write(f'END={int(end_time * 1000)}\n')
                f.write(f'title={title}\n')

        return md_path
    except Exception as e:
        print(f"[WARNING] Could not write metadata file: {e}")
        return None


def process_metadata_command(args):
    """Process the metadata command to update metadata on existing MP3 files."""
    print(f"[METADATA] Updating metadata on {len(args.files)} MP3 file(s)")

    # Prepare metadata dictionary
    metadata = {}

    # Load metadata from JSON file if provided
    if args.metadata_json:
        try:
            with open(args.metadata_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to read metadata JSON: {e}")
            return False

    # Process each file
    success_count = 0
    for mp3_file in args.files:
        mp3_path = Path(mp3_file)
        if not mp3_path.exists():
            print(f"[ERROR] File not found: {mp3_file}")
            continue

        if mp3_path.suffix.lower() not in ['.mp3', '.m4a', '.mp4']:
            print(f"[WARNING] Skipping non-audio file: {mp3_file}")
            continue

        # Prepare file-specific metadata
        file_metadata = metadata.copy()

        # Set default title to filename if not specified
        title_arg = getattr(args, 'title', None) or getattr(args, 'title_name', None)
        if not title_arg:
            # Use filename without extension as default title
            default_title = mp3_path.stem
            # Apply book title styling
            from .utils import book_title_style
            tag_title, filename_base = book_title_style(default_title)
            file_metadata['title'] = tag_title
        else:
            # Use provided title with book styling
            from .utils import book_title_style
            tag_title, filename_base = book_title_style(title_arg)
            file_metadata['title'] = tag_title

        # Set album to same as title if not specified
        if not getattr(args, 'album', None) and 'album' not in file_metadata:
            file_metadata['album'] = file_metadata['title']

        # Set genre to Audiobook if not specified
        if not getattr(args, 'genre', None) and 'genre' not in file_metadata:
            file_metadata['genre'] = 'Audiobook'

        # Override with command line arguments (these take precedence)
        if title_arg:
            file_metadata['title'] = title_arg
        if getattr(args, 'author', None) or getattr(args, 'author_name', None):
            author_arg = getattr(args, 'author', None) or getattr(args, 'author_name', None)
            file_metadata['artist'] = author_arg
        if getattr(args, 'album', None):
            file_metadata['album'] = args.album
        if getattr(args, 'genre', None):
            file_metadata['genre'] = args.genre
        if getattr(args, 'year', None):
            file_metadata['date'] = args.year
        if getattr(args, 'sort_as', None):
            file_metadata['sort_title'] = args.sort_as
        if getattr(args, 'cover', None):
            file_metadata['cover_path'] = args.cover

        # Extract existing metadata and merge (like folder processing does)
        try:
            existing_metadata = extract_all_metadata(str(mp3_path))
            if existing_metadata:
                # Preserve existing metadata but allow overrides
                temp_metadata = existing_metadata.copy()
                # Don't override our explicitly set fields
                for key in ['title', 'artist', 'album', 'genre', 'date', 'sort_title', 'cover_path']:
                    if key in file_metadata:
                        temp_metadata.pop(key, None)
                file_metadata.update(temp_metadata)
        except Exception:
            pass

        print(f"[METADATA] Updating: {mp3_path.name}")
        print(f"  Title: {file_metadata.get('title', 'N/A')}")
        print(f"  Artist: {file_metadata.get('artist', 'N/A')}")
        print(f"  Album: {file_metadata.get('album', 'N/A')}")
        print(f"  Genre: {file_metadata.get('genre', 'N/A')}")
        if file_metadata.get('cover_path'):
            print(f"  Cover: {Path(file_metadata['cover_path']).name}")

        if apply_mp3_metadata(str(mp3_path), file_metadata):
            success_count += 1
        else:
            print(f"[ERROR] Failed to update metadata for: {mp3_file}")

    total_files = len(args.files)
    print(f"\n[METADATA] Processing complete: {success_count}/{total_files} files updated successfully")

    return success_count == total_files


def process_convert_command(args):
    """Process the convert command with the given arguments."""
    # Determine output path
    input_path = Path(args.input)
    if args.output:
        output_path = Path(args.output)
    else:
        # Generate output filename from input file
        output_path = input_path.with_suffix('.m4a')

    # Handle destination directory
    if args.destination:
        dest_dir = Path(args.destination)
        dest_dir.mkdir(parents=True, exist_ok=True)
        output_path = dest_dir / output_path.name
    elif not output_path.is_absolute():
        # If no destination specified and output is relative, place in input file's directory
        output_path = input_path.parent / output_path.name

    metadata = {}
    if args.metadata_json:
        try:
            with open(args.metadata_json, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        except Exception as e:
            print(f"Failed to read metadata JSON: {e}")
            return False

    input_stem = input_path.stem
    input_stem = input_stem.replace('combined', '').replace('Combined', '')
    from .utils import book_title_style
    tag_title, filename_base = book_title_style(input_stem)

    if 'title' not in metadata or not metadata.get('title'):
        metadata['title'] = tag_title
    if 'album' not in metadata or not metadata.get('album'):
        metadata['album'] = tag_title
    if 'artist' not in metadata and hasattr(args, 'author_name') and args.author_name:
        metadata['artist'] = args.author_name

    from .converter import convert_to_m4a
    ok = convert_to_m4a(str(input_path), str(output_path), bitrate=args.bitrate, metadata=metadata, ffmpeg_path=args.ffmpeg_path)
    if not ok:
        print('Conversion failed')
        return False

    print('Conversion complete')

    # Delete the input file if requested and conversion was successful
    if getattr(args, 'delete_origin', False):
        try:
            os.remove(str(input_path))
            print(f'Deleted input file: {input_path}')
        except Exception as e:
            print(f'Warning: Failed to delete input file {input_path}: {e}')

    return True


def process_combine_command(args):
    """Process the combine command with the given arguments."""
    # Determine output path
    if hasattr(args, 'output') and args.output:
        # Use pre-set output path (from file mode with title_suffix)
        output_path = Path(args.output)
    elif args.title_name:
        # Use title_name to generate output filename
        from .utils import book_title_style
        tag_title, filename_base = book_title_style(args.title_name)
        output_path = Path(filename_base + '.m4a')
    else:
        # Generate output filename from first input file
        first_file_path = Path(args.files[0])
        base_name = first_file_path.stem
        # Remove common prefixes like numbers
        base_name = re.sub(r'^\d+\s*-\s*', '', base_name)
        output_path = Path(base_name + '.m4a')

    # Handle destination directory
    if args.destination:
        dest_dir = Path(args.destination)
        dest_dir.mkdir(parents=True, exist_ok=True)
        output_path = dest_dir / output_path.name
    elif not output_path.is_absolute():
        # If no destination specified and output is relative, place in first input file's directory
        first_file_path = Path(args.files[0])
        output_path = first_file_path.parent / output_path.name

    is_m4a_output = output_path.suffix.lower() in ['.m4a', '.mp4']

    if is_m4a_output:
        # Combine to temporary MP3, then convert to M4A
        temp_mp3 = output_path.with_suffix('.tmp.mp3')

        # Step 1: Combine
        success = combine_mp3_files_with_metadata(args.files, str(temp_mp3), bitrate=args.bitrate)
        if not success:
            return False

        # Step 2: Convert
        input_stem = output_path.stem
        input_stem = input_stem.replace('combined', '').replace('Combined', '')
        from .utils import book_title_style
        tag_title, filename_base = book_title_style(input_stem)

        convert_metadata = {
            'title': tag_title,
            'album': tag_title,
            'genre': 'Audiobook'
        }
        if hasattr(args, 'author_name') and args.author_name:
            convert_metadata['artist'] = args.author_name

        from .converter import convert_to_m4a
        success = convert_to_m4a(str(temp_mp3), str(output_path), args.bitrate, convert_metadata, args.ffmpeg_path)

        # Cleanup or keep temp file based on delete_combined flag
        if args.delete_combined or success:
            try:
                os.remove(str(temp_mp3))
                if success and args.delete_combined:
                    print(f'Deleted temporary combined file: {temp_mp3}')
            except Exception as e:
                print(f'Warning: Failed to delete temporary file {temp_mp3}: {e}')

        return success
    else:
        # Just combine to MP3
        success = combine_mp3_files_with_metadata(args.files, str(output_path), args.bitrate)
        return success


def generate_chapter_markers(mp3_files):
    """
    Generate chapter markers for combined files using filenames.
    Returns list of chapter info with filenames as chapter titles.
    Removes _temp_ prefix from temporary files created during M4A conversion.
    Uses appropriate format-specific parsers (MP3, MP4/M4A) to avoid parser errors.
    """
    chapters = []
    current_time_ms = 0

    for mp3_file in mp3_files:
        try:
            file_ext = Path(mp3_file).suffix.lower()
            duration_ms = None

            # Use format-specific parser for better compatibility
            if file_ext in ['.m4a', '.mp4', '.m4b']:
                # Use mutagen.mp4 for M4A/MP4 files (avoids "can't sync to MPEG frame" errors)
                try:
                    audio = MP4(mp3_file)
                    if audio and hasattr(audio.info, 'length') and audio.info.length:
                        duration_ms = int(audio.info.length * 1000)
                except Exception as e:
                    print(f"[DEBUG] MP4 parser failed for {Path(mp3_file).name}: {e}")
                    duration_ms = None
            else:
                # Use mutagen.mp3 for MP3 files
                try:
                    audio = MP3(mp3_file)
                    if audio and hasattr(audio.info, 'length') and audio.info.length:
                        duration_ms = int(audio.info.length * 1000)
                except Exception as e:
                    print(f"[DEBUG] MP3 parser failed for {Path(mp3_file).name}: {e}")
                    duration_ms = None

            # If format-specific parser failed, fall back to generic mutagen.File
            if duration_ms is None:
                try:
                    audio = MutagenFile(mp3_file)
                    if audio and hasattr(audio.info, 'length') and audio.info.length:
                        duration_ms = int(audio.info.length * 1000)
                except Exception as e:
                    print(f"[DEBUG] Generic mutagen parser failed for {Path(mp3_file).name}: {e}")
                    duration_ms = None

            # Use filename (without extension) as chapter title
            filename_base = Path(mp3_file).stem  # Gets filename without extension

            # Remove _temp_ prefix if present (from M4A conversion)
            if filename_base.startswith('_temp_'):
                filename_base = filename_base[6:]  # Remove '_temp_' prefix

            if duration_ms is not None and duration_ms > 0:
                chapter = {
                    'title': filename_base,
                    'start_ms': current_time_ms,
                    'end_ms': current_time_ms + duration_ms
                }
                chapters.append(chapter)
                print(f"[CHAPTER] {filename_base}: {current_time_ms}ms - {current_time_ms + duration_ms}ms ({duration_ms/60000:.1f}min)")
                current_time_ms += duration_ms
            else:
                # Could not determine duration; use 1 second default
                print(f"[WARNING] Could not determine duration for {Path(mp3_file).name}, using 1 second default")
                chapter = {
                    'title': filename_base,
                    'start_ms': current_time_ms,
                    'end_ms': current_time_ms + 1000
                }
                chapters.append(chapter)
                current_time_ms += 1000

        except Exception as e:
            print(f"[WARNING] Unexpected error processing {Path(mp3_file).name}: {e}")
            # Create a minimal chapter entry without duration
            filename_base = Path(mp3_file).stem
            if filename_base.startswith('_temp_'):
                filename_base = filename_base[6:]
            chapter = {
                'title': filename_base,
                'start_ms': current_time_ms,
                'end_ms': current_time_ms + 1000  # Default 1 second
            }
            chapters.append(chapter)
            current_time_ms += 1000

    return chapters


def combine_mp3_files_with_metadata(mp3_files, output_file, bitrate='128k', metadata=None):
    """
    Combine MP3 files using ffmpeg concatenation to preserve original quality.
    Always uses ffmpeg for consistent quality preservation and performance.
    Generates chapter markers from filenames.
    """
    if not mp3_files:
        print("[ERROR] No MP3 files provided")
        return False

    print(f"Combining {len(mp3_files)} files with ffmpeg:")
    for mp3_file in mp3_files:
        print(f"  - {Path(mp3_file).name}")

    # Generate chapter markers from filenames
    print(f"\n[CHAPTERS] Generating chapter markers for {len(mp3_files)} files:")
    chapters = generate_chapter_markers(mp3_files)

    # Update metadata with chapters if not already present
    if metadata:
        if 'chapters' not in metadata or not metadata['chapters']:
            metadata['chapters'] = chapters
    else:
        metadata = {'chapters': chapters}

    # Always use ffmpeg concatenation for quality preservation
    return combine_mp3_files_ffmpeg_concat(mp3_files, output_file, metadata)


def combine_mp3_files_ffmpeg_concat(mp3_files, output_file, metadata=None):
    """
    Concatenate MP3 files using ffmpeg without re-encoding (preserves original quality).
    Much faster than pydub for combine-only operations.
    """
    import tempfile
    import subprocess

    # New approach: rely on a general concat helper that can stream-copy MP3 or M4A files
    try:
        temp_output = concat_without_reencoding(mp3_files, output_file, ffmpeg_path='ffmpeg')

        if not temp_output:
            return False

        # Apply metadata to the concatenated file if possible
        if metadata:
            print("Applying metadata to concatenated file...")
            import time
            time.sleep(0.5)  # Ensure file handle is released
            # Choose metadata applier based on output extension
            out_ext = Path(output_file).suffix.lower()
            if out_ext in ['.mp3']:
                success = apply_mp3_metadata(temp_output, metadata)
                if not success:
                    print("[WARNING]  Warning: Metadata application failed, but file was created")
            elif out_ext in ['.m4a', '.mp4']:
                try:
                    # Attempt to write mp4 tags
                    mp4 = MP4(temp_output)
                    if metadata.get('title'):
                        mp4['\xa9nam'] = [str(metadata.get('title'))]
                    if metadata.get('artist'):
                        mp4['\xa9ART'] = [str(metadata.get('artist'))]
                    if metadata.get('album'):
                        mp4['\xa9alb'] = [str(metadata.get('album'))]
                    mp4['\xa9gen'] = [metadata.get('genre') or 'Audiobook']
                    try:
                        mp4['stik'] = [2]
                    except Exception:
                        pass
                    cover_path = metadata.get('cover_path')
                    if cover_path and os.path.exists(cover_path):
                        with open(cover_path, 'rb') as cf:
                            cover_data = cf.read()
                        fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
                        mp4['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
                    mp4.save()
                except Exception as e:
                    print(f"[WARNING] Could not apply MP4 metadata: {e}")

        # Move to final location (if temp_output differs from requested output)
        if Path(temp_output).absolute() != Path(output_file).absolute():
            shutil.move(temp_output, output_file)

        # Report statistics
        final_size = Path(output_file).stat().st_size
        print(f"[SUCCESS] Concatenation complete!")
        print(f"   Final file: {Path(output_file).name}")
        print(f"   Size: {final_size / 1024:.1f} KB")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to concatenate MP3 files: {e}")
        # Clean up any temp files created during concatenation
        for temp_file in [locals().get('temp_output'), locals().get('concat_path')]:
            try:
                if temp_file and Path(temp_file).exists():
                    Path(temp_file).unlink(missing_ok=True)
            except Exception:
                pass
        return False


def concat_without_reencoding(input_files, desired_output, ffmpeg_path='ffmpeg'):
    """Concatenate arbitrary audio files (MP3/M4A) using ffmpeg concat demuxer without re-encoding.

    Returns the path to the created file (may be desired_output or a temporary file), or None on failure.
    """
    import tempfile
    try:
        desired_output = Path(desired_output)
        # Create temporary concat list file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as concat_file:
            concat_path = concat_file.name
            for f in input_files:
                abs_path = str(Path(f).absolute())
                concat_file.write(f"file '{abs_path}'\n")

        # Use desired extension to determine container (mp3 or mp4/m4a)
        ext = desired_output.suffix.lower()
        if ext in ['.m4a', '.mp4']:
            # ffmpeg will output to mp4 container
            temp_fd, temp_out = tempfile.mkstemp(suffix=ext, prefix='audiobook_concat_')
        else:
            # default to mp3 container
            temp_fd, temp_out = tempfile.mkstemp(suffix='.mp3', prefix='audiobook_concat_')
        os.close(temp_fd)

        # Build ffmpeg command using concat demuxer with stream copy
        # Map only audio streams to avoid copying embedded cover/video streams which
        # may be unsupported in the output container when copied directly.
        cmd = [
            ffmpeg_path, '-f', 'concat', '-safe', '0', '-i', concat_path,
            '-map', '0:a', '-c', 'copy', '-y', temp_out
        ]

        print(f"Concatenating {len(input_files)} files with ffmpeg (stream copy, no re-encoding)...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[ERROR] ffmpeg concat failed: {result.stderr}")
            Path(concat_path).unlink(missing_ok=True)
            Path(temp_out).unlink(missing_ok=True)
            return None

        # If output is MP4/M4A and we have chapter metadata, attempt to remux
        # ffmetadata into the file (no re-encoding) by using ffmpeg to map metadata.
        Path(concat_path).unlink(missing_ok=True)

        return temp_out

    except Exception as e:
        print(f"[ERROR] concat_without_reencoding failed: {e}")
        return None