#!/usr/bin/env python3
"""
Audiobook Processor - Combines multiple MP3 files and converts to M4A
Merges functionality from combine_mp3.py and convert_to_m4a.py
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path
import threading
import time
import argparse
import json
import re
import concurrent.futures
import zipfile

# Auto-install required packages
try:
    from pydub import AudioSegment
except ImportError:
    print("pydub not installed. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"])
    from pydub import AudioSegment

try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not installed. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm

try:
    import mutagen
except ImportError:
    print("mutagen not installed. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    import mutagen

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


def ensure_ffmpeg_on_path(ffmpeg_path=None):
    """Set pydub's ffmpeg/ffprobe paths if a path is provided or common installs exist."""
    if ffmpeg_path:
        candidate = ffmpeg_path
        if os.path.isdir(candidate):
            candidate = os.path.join(candidate, 'ffmpeg.exe')
        candidate = os.path.expandvars(candidate)
        candidate = os.path.expanduser(candidate)
        if os.path.exists(candidate):
            ff_dir = os.path.dirname(candidate)
            os.environ['PATH'] = ff_dir + os.pathsep + os.environ.get('PATH', '')
            try:
                AudioSegment.converter = candidate
            except Exception:
                pass
            probe = os.path.join(ff_dir, 'ffprobe.exe')
            if os.path.exists(probe):
                try:
                    AudioSegment.ffprobe = probe
                except Exception:
                    pass
            return candidate
    return None


def sanitize_filename(name: str) -> str:
    """Sanitize a filename base: remove numbers and special characters,
    collapse internal spaces, and trim leading/trailing whitespace.
    """
    if not name:
        return 'audiobook'
    s = ' '.join(name.strip().split())
    kept = ''.join(ch for ch in s if (ch.isalpha() or ch.isspace()))
    kept = ' '.join(kept.strip().split())
    if not kept:
        return 'audiobook'
    return kept


def book_title_style(text: str):
    """Return (tag_title, filename_base).
    
    Rules:
    - Process input text to create proper title/album name
    - Normalize whitespace and convert separators to spaces
    - Remove leading digits, prefixes, and cleanup patterns
    - Title case with small words lowercased except first/last
    - Create Windows-safe filename version
    """
    if not text or not text.strip():
        return ('Audiobook', 'Audiobook')

    # Initial cleanup and normalization
    s = ' '.join(str(text).strip().split())
    
    # Remove file extensions
    s = re.sub(r'(?i)\.mp3$', '', s)
    
    # Remove trailing "_combined" that we added during processing
    s = re.sub(r'_combined$', '', s, flags=re.IGNORECASE)
    
    # Convert separators to spaces, but be selective with hyphens
    # Convert underscores and colons to spaces
    s = s.replace('_', ' ')
    s = s.replace(':', ' ')
    
    # Handle hyphens more carefully - preserve them in compound words
    # Only convert hyphens that are clearly separators (surrounded by spaces)
    s = re.sub(r'\s+-\s+', ' ', s)  # Convert hyphens with surrounding spaces to spaces
    # Keep hyphens within words like "Half-blood", "Titan's-Curse", etc.
    
    # Remove years in parentheses and extra content in brackets
    s = re.sub(r'\(\d{4}\)', '', s)
    s = re.sub(r'\[.*?\]', '', s)
    
    # Remove leading numbers and patterns:
    # "04 Title" → "Title"
    # "1 Title" → "Title"
    # "Book 3 Title" → "Title"
    # "Volume 5 Title" → "Title"
    s = re.sub(r'^\d+[\s\.]*', '', s)  # Remove leading numbers with separators
    s = re.sub(r'^(Book|Vol|Volume|Part)\s*\d+[\s]+', '', s, flags=re.IGNORECASE)  # Remove prefixes like "Book 3 " (only when followed by more content)

    # Remove embedded numbers that look like series/book numbers, but be more careful
    # Only remove if it's clearly a series indicator like "Book 1", "Vol 2", etc.
    s = re.sub(r'\s+(Book|Vol|Volume|Part)\s*\d+', '', s, flags=re.IGNORECASE)

    # Remove years in parentheses and extra content in brackets
    s = re.sub(r'\(\d{4}\)', '', s)
    s = re.sub(r'\[.*?\]', '', s)

    # Remove years attached with underscores or other separators (like _2020)
    # But preserve famous book titles that look like years
    famous_titles = ['1984', '2001', '451', '2010']
    if not any(title in s for title in famous_titles):
        s = re.sub(r'[\s_]+\d{4}$', '', s)  # Remove trailing years like " _2020"
        s = re.sub(r'^\d{4}[\s_-]+', '', s)  # Remove leading years like "2020 - "
    
    # Clean up extra whitespace and punctuation
    s = re.sub(r'\s+', ' ', s)  # Multiple spaces to single space
    s = s.strip(" \t\n\r\f\v'\"-.,:;()[]{}")
    
    # If nothing left after cleaning, use default
    if not s or len(s.strip()) < 2:
        return ('Audiobook', 'Audiobook')

    # Apply proper title casing
    small_words = {
        'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 'on', 'at', 'to',
        'from', 'by', 'in', 'of', 'with', 'as', 'is', 'if', 'than', 'via', 'per'
    }

    def title_case_piece(piece):
        # If the input is all uppercase, convert to proper title case
        if piece.isupper() and len(piece) > 3:
            piece = piece.lower()
            
        words = piece.split()
        if not words:
            return piece
        
        result = []
        for i, word in enumerate(words):
            lower_word = word.lower()
            # First and last words are always capitalized
            # Small words in the middle are kept lowercase
            if i == 0 or i == len(words) - 1 or lower_word not in small_words:
                result.append(word.capitalize())
            else:
                result.append(lower_word)
        
        return ' '.join(result)

    tag_title = title_case_piece(s)

    # Create filename-safe version
    fname = tag_title
    fname = fname.replace('"', '').replace("'", "'")
    fname = re.sub(r'[<>"/\\|\?\*]', '', fname)  # Remove Windows forbidden chars
    fname = ' '.join(fname.split())  # Normalize whitespace
    fname = fname.replace('—', '-').replace('–', '-')  # Normalize dashes
    
    # Ensure filename isn't empty
    if not fname or not fname.strip():
        fname = 'Audiobook'
    
    fname = fname.strip(' .-')

    return (tag_title, fname)


def detect_mp3_bitrate(mp3_file):
    """Detect the bitrate of an MP3 file in kbps (e.g., '128k', '192k')."""
    try:
        from mutagen.mp3 import MP3
        audio = MP3(mp3_file)
        if audio and hasattr(audio.info, 'bitrate'):
            # Convert bitrate from bits per second to kbps
            bitrate_kbps = audio.info.bitrate // 1000
            return f"{bitrate_kbps}k"
    except Exception as e:
        print(f"Warning: Could not detect bitrate from {mp3_file}: {e}")
    return None


def extract_all_metadata(mp3_file):
    """Extract metadata, cover art, and chapters from an audio file (MP3 or M4A).
    
    Handles both MP3 (ID3 tags) and M4A/MP4 (iTunes tags) formats.
    """
    metadata = {}
    file_ext = Path(mp3_file).suffix.lower()
    
    # Try M4A/MP4 format first if the file is M4A
    if file_ext in ['.m4a', '.mp4', '.m4b']:
        try:
            from mutagen.mp4 import MP4
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
        from mutagen.id3 import ID3
        from mutagen.mp3 import MP3
        
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


def export_with_progress(audio_segment, output_path, format='mp3', bitrate='128k', total_duration_ms=None):
    """Export audio with progress bar and large file handling."""
    if total_duration_ms is None:
        total_duration_ms = len(audio_segment)
    
    # Check if this is a very large audio file that needs chunked processing
    duration_hours = total_duration_ms / (1000 * 60 * 60)
    if duration_hours > 20:  # Over 20 hours, use chunked export
        return export_large_audio_chunked(audio_segment, output_path, format, bitrate)
    
    # Use a temporary file for export
    temp_path = output_path + '.tmp'
    
    try:
        # Export with better error handling
        print(f"Exporting to temporary file: {temp_path}")
        
        # Force garbage collection before export to free memory
        import gc
        gc.collect()
        
        # For large files, try direct MP3 export first to avoid WAV intermediate format
        if format == 'mp3' and duration_hours > 10:
            # Use ffmpeg for large files to avoid pydub memory issues
            return export_large_with_ffmpeg(audio_segment, output_path, bitrate)
        
        # Start progress tracking
        import threading
        import time
        
        # Progress bar setup
        duration_minutes = total_duration_ms / (1000 * 60)
        progress_bar = tqdm(total=duration_minutes, desc="Exporting combined file", unit="min", ncols=80)
        
        # Flag to control progress thread
        export_complete = threading.Event()
        
        def update_progress():
            """Update progress based on file size growth."""
            start_time = time.time()
            # Correct calculation: bitrate (kbps) * duration (ms) / 8 = bytes
            bitrate_kbps = int(bitrate.replace('k', ''))
            expected_size = (bitrate_kbps * total_duration_ms) // 8  # Expected file size in bytes
            
            while not export_complete.is_set():
                if os.path.exists(temp_path):
                    current_size = os.path.getsize(temp_path)
                    if expected_size > 0:
                        progress_ratio = min(current_size / expected_size, 1.0)
                        target_progress = progress_ratio * duration_minutes
                        progress_bar.n = target_progress
                        progress_bar.refresh()
                
                time.sleep(0.2)  # Update every 200ms
        
        # Start progress thread
        progress_thread = threading.Thread(target=update_progress, daemon=True)
        progress_thread.start()
        
        # Optimized pydub export for smaller files
        export_params = {
            'format': format,
            'bitrate': bitrate
        }
        
        # Add optimization parameters for MP3
        if format == 'mp3':
            export_params.update({
                'parameters': ['-q:a', '9']  # Use lowest quality for fastest encoding at 32k
            })
        
        # Perform the actual export
        audio_segment.export(temp_path, **export_params)
        
        # Signal export completion and wait for progress thread to finish
        export_complete.set()
        progress_thread.join(timeout=1.0)  # Wait up to 1 second for progress thread to finish
        
        # Finalize progress bar
        progress_bar.n = duration_minutes
        progress_bar.refresh()
        time.sleep(0.1)  # Small delay to ensure 100% is visible
        progress_bar.close()
        
        # Ensure the temporary file exists and has content
        if not os.path.exists(temp_path) or os.path.getsize(temp_path) == 0:
            raise Exception("Temporary file was not created or is empty")
        
        # Move to final location
        if os.path.exists(output_path):
            os.remove(output_path)
        shutil.move(temp_path, output_path)
        
        print(f"Export complete {os.path.basename(output_path)} {os.path.getsize(output_path)/1024:.1f}KB")
        return True
        
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")
        # Clean up temporary file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                print(f"Cleaned up temporary file: {temp_path}")
            except Exception as cleanup_error:
                print(f"Failed to clean up temporary file: {cleanup_error}")
        return False


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
    tag_title, filename_base = book_title_style(input_stem)

    if 'title' not in metadata or not metadata.get('title'):
        metadata['title'] = tag_title
    if 'album' not in metadata or not metadata.get('album'):
        metadata['album'] = tag_title
    if 'artist' not in metadata and hasattr(args, 'author_name') and args.author_name:
        metadata['artist'] = args.author_name

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
        success, metadata = combine_mp3_files_with_metadata(args.files, str(temp_mp3), bitrate=args.bitrate)
        if not success:
            return False
        
        # Step 2: Convert
        input_stem = output_path.stem
        input_stem = input_stem.replace('combined', '').replace('Combined', '')
        tag_title, filename_base = book_title_style(input_stem)
        
        convert_metadata = {
            'title': tag_title,
            'album': tag_title,
            'genre': 'Audiobook'
        }
        convert_metadata.update(metadata)
        if hasattr(args, 'author_name') and args.author_name:
            convert_metadata['artist'] = args.author_name
        
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
        success, _ = combine_mp3_files(args.files, str(output_path), args.bitrate)
        return success


def export_large_with_ffmpeg(audio_segment, output_path, bitrate):
    """Export very large audio files using ffmpeg concatenation to avoid memory issues."""
    try:
        import tempfile
        import subprocess
        
        # Create temporary directory for chunks
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"[PROCESSING] Using chunked export for large audiobook...")
            
            # Split into 1-hour chunks to avoid memory issues
            chunk_duration = 60 * 60 * 1000  # 1 hour in milliseconds
            total_duration = len(audio_segment)
            chunk_files = []
            
            num_chunks = (total_duration + chunk_duration - 1) // chunk_duration
            print(f"[CHUNKS] Splitting into {num_chunks} chunks for processing...")
            
            # Progress bar for chunk creation
            chunk_progress = tqdm(range(num_chunks), desc="Creating chunks", unit="chunk", ncols=80)
            
            for i in chunk_progress:
                start_time = i * chunk_duration
                end_time = min(start_time + chunk_duration, total_duration)
                
                chunk = audio_segment[start_time:end_time]
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.mp3")
                
                # Update progress description with current chunk info
                chunk_hours = (end_time - start_time) / (1000 * 60 * 60)
                chunk_progress.set_description(f"Creating chunk {i+1}/{num_chunks} ({chunk_hours:.1f}h)")
                
                chunk.export(chunk_file, format='mp3', bitrate=bitrate, 
                           parameters=['-q:a', '9'])  # Fast encoding
                chunk_files.append(chunk_file)
                
                # Clear memory
                del chunk
                import gc
                gc.collect()
            
            chunk_progress.close()
            
            # Use ffmpeg to concatenate chunks
            print(f"[CONCAT] Concatenating {len(chunk_files)} chunks with ffmpeg...")
            
            # Create concat file for ffmpeg
            concat_file = os.path.join(temp_dir, "concat.txt")
            with open(concat_file, 'w') as f:
                for chunk_file in chunk_files:
                    f.write(f"file '{chunk_file}'\n")
            
            # Run ffmpeg concatenation with progress tracking
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
                '-i', concat_file, '-c', 'copy', output_path
            ]
            
            # Start progress tracking for concatenation
            concat_progress = tqdm(total=100, desc="Concatenating chunks", unit="%", ncols=80)
            concat_progress.set_description(f"Concatenating {len(chunk_files)} chunks")
            
            # Use threading to update progress during ffmpeg execution
            import threading
            import time
            
            concat_complete = threading.Event()
            
            def track_concat_progress():
                """Track concatenation progress by monitoring time and file size."""
                start_time = time.time()
                total_input_size = sum(os.path.getsize(cf) for cf in chunk_files)
                
                # Estimate time based on file size (rough approximation: 1MB takes ~0.1 seconds)
                estimated_time = max(total_input_size / (1024 * 1024 * 10), 5)  # At least 5 seconds
                
                while not concat_complete.is_set():
                    elapsed = time.time() - start_time
                    if os.path.exists(output_path):
                        current_size = os.path.getsize(output_path)
                        # Use a combination of time and size progress
                        time_progress = min((elapsed / estimated_time) * 100, 90)  # Time-based, max 90%
                        size_progress = min((current_size / total_input_size) * 100, 100) if total_input_size > 0 else 0
                        # Use the higher of the two estimates
                        progress_percent = max(time_progress, size_progress)
                        concat_progress.n = min(progress_percent, 99)  # Don't show 100% until actually complete
                        concat_progress.refresh()
                    
                    time.sleep(0.5)  # Update every 500ms
            
            # Start progress tracking thread
            progress_thread = threading.Thread(target=track_concat_progress, daemon=True)
            progress_thread.start()
            
            # Execute ffmpeg
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            # Signal completion and wait for progress thread
            concat_complete.set()
            progress_thread.join(timeout=2.0)  # Wait for progress thread to finish
            
            # Finalize progress bar
            concat_progress.n = 100
            concat_progress.refresh()
            time.sleep(0.1)  # Small delay to ensure 100% is visible
            concat_progress.close()
            
            if result.returncode == 0:
                print(f"[SUCCESS] Large file export complete: {os.path.basename(output_path)}")
                print(f"   File size: {os.path.getsize(output_path)/1024/1024:.1f} MB")
                return True
            else:
                print(f"[ERROR] FFmpeg concatenation failed: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"[ERROR] Large file export failed: {e}")
        return False


def export_large_audio_chunked(audio_segment, output_path, format='mp3', bitrate='128k'):
    """Export extremely large audio files (20+ hours) using chunked approach."""
    # This is a fallback for the chunked method
    return export_large_with_ffmpeg(audio_segment, output_path, bitrate)


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
                    from mutagen.mp4 import MP4
                    audio = MP4(mp3_file)
                    if audio and hasattr(audio.info, 'length') and audio.info.length:
                        duration_ms = int(audio.info.length * 1000)
                except Exception as e:
                    print(f"[DEBUG] MP4 parser failed for {Path(mp3_file).name}: {e}")
                    duration_ms = None
            else:
                # Use mutagen.mp3 for MP3 files
                try:
                    from mutagen.mp3 import MP3
                    audio = MP3(mp3_file)
                    if audio and hasattr(audio.info, 'length') and audio.info.length:
                        duration_ms = int(audio.info.length * 1000)
                except Exception as e:
                    print(f"[DEBUG] MP3 parser failed for {Path(mp3_file).name}: {e}")
                    duration_ms = None
            
            # If format-specific parser failed, fall back to generic mutagen.File
            if duration_ms is None:
                try:
                    from mutagen import File as MutagenFile
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


def combine_mp3_files(mp3_files, output_file, bitrate='128k'):
    """Combine multiple MP3 files into a single file using ffmpeg concatenation."""
    print(f"Combining {len(mp3_files)} files with ffmpeg:")
    for f in mp3_files:
        print(f"  - {os.path.basename(f)}")

    try:
        combined_metadata = {'duration_ms': 0}

        # Extract metadata from the first file that has cover art
        cover_source = None
        for mp3_file in mp3_files:
            metadata = extract_all_metadata(mp3_file)
            if metadata.get('cover_path') and not cover_source:
                cover_source = mp3_file
                combined_metadata.update(metadata)
                print(f"[COVER] Using cover art from: {os.path.basename(mp3_file)}")
                break

        # If no cover found in individual files, try the first file
        if not cover_source and mp3_files:
            metadata = extract_all_metadata(mp3_files[0])
            combined_metadata.update(metadata)

        # Generate chapter markers from filenames
        print(f"\n[CHAPTERS] Generating chapter markers for {len(mp3_files)} files:")
        chapters = generate_chapter_markers(mp3_files)
        combined_metadata['chapters'] = chapters

        # Use ffmpeg concatenation (stream copy; helper will choose container)
        success = combine_mp3_files_ffmpeg_concat(mp3_files, output_file, combined_metadata)

        if success:
            # Calculate total duration from the output file
            try:
                duration = get_duration_seconds(output_file)
                if duration:
                    duration_ms = int(duration * 1000)
                    combined_metadata['duration_ms'] = duration_ms
                    print(f"Successfully combined {len(mp3_files)} files!")
                    print(f"Total duration: {duration_ms / 60000:.1f} minutes")
                else:
                    print(f"Successfully combined {len(mp3_files)} files (duration unknown)")
                print(f"Total chapters: {len(chapters)}")
            except Exception as e:
                print(f"[WARNING] Could not determine duration: {e}")

            return True, combined_metadata
        else:
            return False, {}

    except Exception as e:
        print(f"[ERROR] Failed to combine files: {e}")
        return False, {}


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
                    from mutagen.mp4 import MP4, MP4Cover
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


def write_ffmetadata(metadata, out_path):
    """Write FFmpeg metadata file for chapters."""
    chapters = metadata.get('chapters') or []
    if not chapters:
        return None

    md_lines = [';FFMETADATA1']
    for k in ('title', 'artist', 'album', 'date', 'genre', 'comment'):
        v = metadata.get(k)
        if v:
            md_lines.append(f"{k}={v}")

    for ch in chapters:
        start = int(ch.get('start_ms') or 0)
        end = int(ch.get('end_ms') or start + 1000)
        md_lines.append('[CHAPTER]')
        md_lines.append('TIMEBASE=1/1000')
        md_lines.append(f'START={start}')
        md_lines.append(f'END={end}')
        if ch.get('title'):
            md_lines.append(f"title={ch.get('title')}")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
    tmp.write('\n'.join(md_lines).encode('utf-8'))
    tmp.close()
    return tmp.name


def get_duration_seconds(input_file, ffprobe_path=None):
    """Get duration of audio file in seconds using format-specific parsers.
    
    Prioritizes format-specific parsers (MP3 for .mp3, MP4 for .m4a/.mp4/.m4b)
    to avoid cross-format parser errors. Falls back to generic mutagen.File,
    then ffprobe, then returns None if all methods fail.
    """
    file_ext = Path(input_file).suffix.lower()
    
    # Try format-specific parser first
    try:
        if file_ext in ['.m4a', '.mp4', '.m4b']:
            # Use mutagen.mp4 for M4A/MP4 files
            from mutagen.mp4 import MP4
            audio = MP4(input_file)
            if audio and hasattr(audio.info, 'length') and audio.info.length:
                return float(audio.info.length)
    except Exception:
        pass
    
    try:
        if file_ext in ['.mp3']:
            # Use mutagen.mp3 for MP3 files
            from mutagen.mp3 import MP3
            audio = MP3(input_file)
            if audio and hasattr(audio.info, 'length') and audio.info.length:
                return float(audio.info.length)
    except Exception:
        pass
    
    # Fall back to generic mutagen parser
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(input_file)
        if audio and hasattr(audio.info, 'length') and audio.info.length:
            return float(audio.info.length)
    except Exception:
        pass

    # Last resort: try ffprobe
    try:
        probe = ffprobe_path or shutil.which('ffprobe')
        if probe:
            cmd = [probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = res.stdout.strip()
            if out:
                return float(out)
    except Exception:
        pass

    return None


def apply_mp3_metadata(mp3_file, metadata):
    """Apply metadata to an audio file (MP3 or M4A) using mutagen.
    
    Automatically detects file format and applies appropriate metadata tags.
    Supports ID3 tags for MP3 and iTunes tags for M4A/MP4.
    """
    file_ext = Path(mp3_file).suffix.lower()
    
    # Handle M4A/MP4 files
    if file_ext in ['.m4a', '.mp4', '.m4b']:
        try:
            from mutagen.mp4 import MP4, MP4Cover
            
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
        from mutagen.id3 import ID3NoHeaderError, ID3, TIT2, TPE1, TALB, TDRC, TCON, TSOT, APIC, TXXX
        
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
            from mutagen.id3 import TRCK
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


def convert_to_m4a(input_file, output_file, bitrate='128k', metadata=None, ffmpeg_path='ffmpeg'):
    """Convert MP3 to M4A with metadata preservation."""
    if metadata is None:
        metadata = {}

    # Try to extract cover and chapters if not provided
    try:
        if not metadata.get('cover_path') or not metadata.get('chapters'):
            src_meta = extract_all_metadata(input_file)
            if src_meta and src_meta.get('cover_path') and not metadata.get('cover_path'):
                metadata['cover_path'] = src_meta.get('cover_path')
            if src_meta and src_meta.get('chapters') and not metadata.get('chapters'):
                metadata['chapters'] = src_meta.get('chapters')
    except Exception:
        pass

    cmd = [ffmpeg_path, '-y', '-i', input_file]
    input_index = 1
    cover = metadata.get('cover_path')
    md_file = None

    if cover:
        cmd += ['-i', cover]
        input_index += 1

    md_file = write_ffmetadata(metadata, output_file) if metadata.get('chapters') else None
    if md_file:
        cmd += ['-f', 'ffmetadata', '-i', md_file]
        md_input_index = input_index
        input_index += 1
    else:
        md_input_index = None

    if cover and md_file:
        cmd += [
            '-map', '0:a',
            '-map', '1',
            '-map_metadata', str(md_input_index),
            '-c:a', 'aac', '-b:a', bitrate,
            '-c:v', 'mjpeg',
            '-metadata:s:v', 'title=Cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-disposition:v:0', 'attached_pic'
        ]
    elif cover:
        cmd += [
            '-map', '0:a',
            '-map', '1',
            '-c:a', 'aac', '-b:a', bitrate,
            '-c:v', 'mjpeg',
            '-metadata:s:v', 'title=Cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-disposition:v:0', 'attached_pic'
        ]
    elif md_file:
        cmd += [
            '-map', '0:a',
            '-map_metadata', str(md_input_index),
            '-c:a', 'aac', '-b:a', bitrate,
            '-vn'
        ]
    else:
        cmd += ['-c:a', 'aac', '-b:a', bitrate, '-vn']

    for field, tag in (('title', 'title'), ('artist', 'artist'), ('album', 'album'), ('date', 'date')):
        val = metadata.get(field)
        if val:
            cmd += ['-metadata', f'{tag}={val}']

    cmd += ['-f', 'mp4', output_file]

    print('Running ffmpeg to convert to m4a...')
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    pbar = None
    total_sec = None
    
    try:
        if metadata.get('duration_ms'):
            total_sec = metadata.get('duration_ms') / 1000.0
        else:
            total_sec = get_duration_seconds(input_file)
    except Exception:
        total_sec = None

    if total_sec:
        try:
            pbar = tqdm(total=total_sec, unit='s', desc='ffmpeg')
        except Exception:
            pbar = None

    time_re = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
    last_pos = 0.0
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        line = line.strip()
        m = time_re.search(line)
        if m and pbar:
            h = int(m.group(1))
            mm = int(m.group(2))
            ss = float(m.group(3))
            cur = h*3600 + mm*60 + ss
            try:
                delta = max(0.0, cur - last_pos)
                if delta > 0:
                    pbar.update(delta)
                    last_pos = cur
            except Exception:
                pass

    ret = proc.wait()
    if pbar:
        pbar.close()

    success = (ret == 0)

    if success:
        try:
            from mutagen.mp4 import MP4, MP4Cover
            mp4 = MP4(output_file)
            if metadata.get('title'):
                mp4['\xa9nam'] = [str(metadata.get('title'))]
            if metadata.get('artist'):
                mp4['\xa9ART'] = [str(metadata.get('artist'))]
            if metadata.get('album'):
                mp4['\xa9alb'] = [str(metadata.get('album'))]
            if metadata.get('sort_title'):
                mp4['sonm'] = [str(metadata.get('sort_title'))]  # Sort Title
            
            # Add track number if available
            if metadata.get('track_number'):
                try:
                    track_num = int(metadata['track_number'])
                    total_tracks = int(metadata.get('total_tracks', 0))
                    if total_tracks > 0:
                        mp4['trkn'] = [(track_num, total_tracks)]
                    else:
                        mp4['trkn'] = [(track_num, 0)]
                except ValueError:
                    pass
                    
            mp4['\xa9gen'] = [metadata.get('genre') or 'Audiobook']
            try:
                mp4['stik'] = [2]  # Audiobook
            except Exception:
                pass
            cover_path = metadata.get('cover_path')
            if cover_path and os.path.exists(cover_path):
                with open(cover_path, 'rb') as cf:
                    cover_data = cf.read()
                fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
                mp4['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
            mp4.save()
        except Exception:
            pass

    # Cleanup temporary files
    try:
        if cover and os.path.exists(cover):
            os.unlink(cover)
    except Exception:
        pass
    try:
        if md_file and os.path.exists(md_file):
            os.unlink(md_file)
    except Exception:
        pass

    return success


def find_mp3_folders(root_path, min_files=1, include_m4a=False):
    """Recursively find all folders containing MP3 files (and optionally M4A files).
    
    Args:
        root_path: Root directory to search
        min_files: Minimum number of audio files required to mark a folder
        include_m4a: If True, also look for and count M4A files alongside MP3 files
        
    Returns:
        List of folder paths that contain audio files
    """
    root_path = Path(root_path)
    audio_folders = []
    
    if include_m4a:
        print(f"Scanning for folders with MP3/M4A files in: {root_path}")
    else:
        print(f"Scanning for folders with MP3 files in: {root_path}")
    
    # Walk through all subdirectories
    for folder_path in root_path.rglob('*'):
        if folder_path.is_dir():
            # Count audio files in this specific folder (not subdirectories)
            mp3_files = list(folder_path.glob('*.mp3'))
            m4a_files = list(folder_path.glob('*.m4a')) if include_m4a else []
            audio_files = mp3_files + m4a_files
            
            if len(audio_files) >= min_files:
                audio_folders.append(folder_path)
                file_count_str = f"{len(mp3_files)} MP3 files"
                if include_m4a and m4a_files:
                    file_count_str += f", {len(m4a_files)} M4A files"
                print(f"  Found: {folder_path} ({file_count_str})")
    
    return audio_folders


def verify_and_retry_conversions(source_mp3_files, conversion_output_dir, bitrate, ffmpeg_path, max_retries=5):
    """
    Verify that all source MP3 files have been successfully converted to M4A.
    Retry conversion for missing files up to max_retries times per file.
    
    Args:
        source_mp3_files: List of source MP3 file paths
        conversion_output_dir: Path to the conversion output directory
        bitrate: Bitrate for conversion
        ffmpeg_path: Path to ffmpeg executable
        max_retries: Maximum retry attempts per file
    
    Returns:
        bool: True if all files were successfully converted, False otherwise
    """
    from pathlib import Path
    
    print(f"[VERIFY] Verifying conversion completeness...")
    
    # Create expected M4A file mapping
    expected_m4a_files = {}
    for mp3_file in source_mp3_files:
        mp3_path = Path(mp3_file)
        expected_m4a = conversion_output_dir / f"{mp3_path.stem}.m4a"
        expected_m4a_files[str(mp3_file)] = expected_m4a
    
    # Check which files are missing or incomplete
    missing_files = []
    for mp3_file, m4a_file in expected_m4a_files.items():
        if not m4a_file.exists():
            missing_files.append(mp3_file)
            print(f"[VERIFY] Missing: {Path(mp3_file).name} -> {m4a_file.name}")
        elif m4a_file.stat().st_size < 1024:  # File too small, likely incomplete
            missing_files.append(mp3_file)
            print(f"[VERIFY] Incomplete: {Path(mp3_file).name} -> {m4a_file.name} (size: {m4a_file.stat().st_size} bytes)")
    
    if not missing_files:
        print(f"[VERIFY] ✅ All {len(source_mp3_files)} files successfully converted")
        return True
    
    print(f"[VERIFY] Found {len(missing_files)} missing/incomplete files - attempting retries...")
    
    # Retry conversion for missing files
    retry_count = {}
    remaining_files = missing_files.copy()
    
    while remaining_files and max(retry_count.get(f, 0) for f in remaining_files) < max_retries:
        current_batch = remaining_files.copy()
        remaining_files = []
        
        for mp3_file in current_batch:
            mp3_path = Path(mp3_file)
            m4a_file = expected_m4a_files[mp3_file]
            
            # Initialize retry count
            if mp3_file not in retry_count:
                retry_count[mp3_file] = 0
            
            retry_count[mp3_file] += 1
            retry_num = retry_count[mp3_file]
            
            print(f"[RETRY] Attempt {retry_num}/{max_retries}: {mp3_path.name}")
            
            # Remove incomplete file if it exists
            if m4a_file.exists():
                try:
                    m4a_file.unlink()
                except Exception:
                    pass
            
            # Extract metadata from MP3 for conversion
            try:
                from mutagen.id3 import ID3
                id3 = ID3(str(mp3_path))
                convert_metadata = {
                    'title': str(id3.get('TIT2', '')),
                    'artist': str(id3.get('TPE1', '')),
                    'album': str(id3.get('TALB', '')),
                    'genre': str(id3.get('TCON', '')),
                    'sort_title': str(id3.get('TSOT', '')),
                }
                
                # Extract track number if available
                if 'TRCK' in id3:
                    track_info = str(id3.get('TRCK', ''))
                    if '/' in track_info:
                        track_num, total = track_info.split('/', 1)
                        convert_metadata['track_number'] = track_num
                        convert_metadata['total_tracks'] = total
                    else:
                        convert_metadata['track_number'] = track_info
            except Exception:
                convert_metadata = {}
            
            # Attempt conversion
            success = convert_to_m4a(str(mp3_path), str(m4a_file), bitrate=bitrate, metadata=convert_metadata, ffmpeg_path=ffmpeg_path)
            
            if success and m4a_file.exists() and m4a_file.stat().st_size >= 1024:
                print(f"[RETRY] ✅ Success: {mp3_path.name}")
            else:
                print(f"[RETRY] ❌ Failed: {mp3_path.name}")
                if retry_num < max_retries:
                    remaining_files.append(mp3_file)
                else:
                    print(f"[RETRY] ❌ Max retries ({max_retries}) reached for: {mp3_path.name}")
    
    # Final verification
    final_missing = []
    for mp3_file, m4a_file in expected_m4a_files.items():
        if not m4a_file.exists() or m4a_file.stat().st_size < 1024:
            final_missing.append(Path(mp3_file).name)
    
    if final_missing:
        print(f"[VERIFY] ❌ Final verification failed - {len(final_missing)} files could not be converted:")
        for filename in final_missing:
            print(f"[VERIFY]   - {filename}")
        return False
    else:
        print(f"[VERIFY] ✅ Final verification passed - all {len(source_mp3_files)} files successfully converted")
        return True



def process_multiple_folders(folders, bitrate=None, ffmpeg_path='ffmpeg', delete_combined=False, compress_originals=False, delete_originals=False, parallel=False, output_format='m4a', destination=None, author_name=None, combine_only=False, combine_all=False, metadata=False, cover_path=None, sort_as=None, sort_prefix_parent=False, sort_prefix_label=None, custom_prefix=None, custom_suffix=None, sort_as_prefix=None, album_prefix=None, album_suffix=None, title_suffix=None):
    """Process multiple folders containing MP3 files.
    
    Args:
        folders: List of folder paths to process
        bitrate: Audio bitrate for processing
        ffmpeg_path: Path to ffmpeg executable
        delete_combined: Whether to delete combined MP3 after conversion
        parallel: Whether to process folders in parallel (True) or sequentially (False)
        combine_only: If True, only combine MP3s and apply MP3 metadata (no conversion to M4A)
        combine_all: If True, include M4A files in combining alongside MP3s
        metadata: If True, only update metadata without combining or converting files
        cover_path: Path to cover image file to embed
        sort_as: Sort title for proper library ordering
        prefix_parent: If True, prepend parent folder name to title
        custom_prefix: Custom prefix string to prepend to titles
        
    Returns:
        Dictionary with results for each folder
    """
    import concurrent.futures
    import threading
    
    results = {}
    
    def process_single_folder(folder_path):
        """Process a single folder and return results."""
        try:
            print(f"\n{'='*60}")
            print(f"Processing: {folder_path}")
            print(f"{'='*60}")
            
            # Generate title with prefix if requested
            if sort_prefix_parent or custom_prefix:
                title_name = get_prefixed_title(folder_path, sort_prefix_parent=sort_prefix_parent, sort_prefix_label=sort_prefix_label, custom_prefix=custom_prefix)
                print(f"[TITLE] Generated title with prefix: {title_name}")
            else:
                title_name = None  # Use folder name as-is
            
            # Determine destination for this folder
            folder_destination = None
            if destination:
                # Place files directly in the destination directory (no subdirectories)
                folder_destination = Path(destination)
                # Ensure the destination directory exists
                folder_destination.mkdir(parents=True, exist_ok=True)
            
            success = process_folder(
                str(folder_path), 
                title_name=title_name,  # Use generated title or folder name
                author_name=author_name,
                bitrate=bitrate, 
                ffmpeg_path=ffmpeg_path, 
                delete_combined=delete_combined,
                compress_originals=compress_originals,
                delete_originals=delete_originals,
                output_format=output_format,
                    destination=str(folder_destination) if folder_destination else None,
                combine_only=combine_only,
                combine_all=combine_all,
                metadata=metadata,
                cover_path=cover_path,
                sort_as=sort_as,
                sort_prefix_parent=sort_prefix_parent,
                sort_prefix_label=sort_prefix_label,
                custom_prefix=custom_prefix,
                custom_suffix=custom_suffix,
                sort_as_prefix=sort_as_prefix,
                album_prefix=album_prefix,
                album_suffix=album_suffix,
                title_suffix=title_suffix
            )
            
            if success:
                print(f"[SUCCESS] Successfully processed: {folder_path}")
            else:
                print(f"[ERROR] Failed to process: {folder_path}")
                
            return folder_path, success
            
        except Exception as e:
            print(f"[ERROR] Error processing {folder_path}: {e}")
            return folder_path, False
    
    if parallel and len(folders) > 1:
        print(f"\n[PROCESSING] Processing {len(folders)} folders in parallel...")
        print("Note: Parallel processing may use significant system resources.")
        
        # Use ThreadPoolExecutor for I/O bound operations
        # Limit concurrent workers to avoid overwhelming the system
        max_workers = min(len(folders), 3)  # Process max 3 folders at once
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_folder = {executor.submit(process_single_folder, folder): folder for folder in folders}
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_folder):
                folder_path, success = future.result()
                results[str(folder_path)] = success
                
    else:
        print(f"\n[PROCESSING] Processing {len(folders)} folders sequentially...")
        
        for i, folder_path in enumerate(folders, 1):
            print(f"\n[{i}/{len(folders)}] Processing folder...")
            folder_path_str, success = process_single_folder(folder_path)
            results[str(folder_path_str)] = success
    
    return results


def compress_original_files(folder_path, mp3_files, output_name, delete_originals=False):
    """Compress the original MP3 files into a ZIP archive.
    
    Args:
        folder_path: Path to the folder containing the files
        mp3_files: List of MP3 file paths to compress
        output_name: Base name for the archive
        delete_originals: Whether to delete original files after compression
        
    Returns:
        tuple: (success, archive_path)
    """
    try:
        folder_path = Path(folder_path)
        archive_name = f"{output_name}_original_files.zip"
        archive_path = folder_path / archive_name
        
        print(f"\n[COMPRESS] Compressing {len(mp3_files)} original MP3 files...")
        print(f"Archive: {archive_name}")
        
        # Create ZIP archive with optimized compression for speed
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as zipf:
            total_original_size = 0
            
            for mp3_file in tqdm(mp3_files, desc="Compressing files", unit="file"):
                mp3_path = Path(mp3_file)
                if mp3_path.exists():
                    # Get file size before compression
                    file_size = mp3_path.stat().st_size
                    total_original_size += file_size
                    
                    # Add file to archive with just the filename (no path)
                    zipf.write(mp3_path, mp3_path.name)
        
        # Get compressed size
        compressed_size = archive_path.stat().st_size
        compression_ratio = (1 - compressed_size / total_original_size) * 100
        
        print(f"[SUCCESS] Compression complete!")
        print(f"   Original size: {total_original_size / (1024*1024):.1f} MB")
        print(f"   Compressed size: {compressed_size / (1024*1024):.1f} MB")
        print(f"   Compression ratio: {compression_ratio:.1f}%")
        
        # Delete original files if requested
        if delete_originals:
            deleted_count = 0
            for mp3_file in mp3_files:
                try:
                    os.remove(mp3_file)
                    deleted_count += 1
                except Exception as e:
                    print(f"[WARNING]  Failed to delete {mp3_file}: {e}")
            
            if deleted_count > 0:
                print(f"[DELETE] Deleted {deleted_count} original MP3 files")
        
        return True, str(archive_path)
        
    except Exception as e:
        print(f"[ERROR] Compression failed: {e}")
        return False, None


def create_series_sort_title(folder_path, is_mp3_folder=True):
    """
    Create a sort title with series organization.
    Format: 'SERIES NAME : BOOK NAME'
    
    Args:
        folder_path: Path to the audiobook folder
        is_mp3_folder: True if this folder contains MP3s, False if it's a parent folder
    
    Returns:
        str: Sort title in format 'Parent Folder : Current Folder'
    """
    folder_path = Path(folder_path)
    
    if is_mp3_folder:
        # Standard case: folder contains MP3 files
        book_name = folder_path.name
        parent_folder = folder_path.parent
        series_name = parent_folder.name
    else:
        # Parent folder case: use the folder name as series, but no specific book name
        # This case is handled in process_folder when we find the actual MP3 folder
        return folder_path.name
    
    # Skip if parent is just the root audiobooks folder or similar generic names
    generic_names = {'audiobooks', 'books', 'audio', 'media', 'music', 'downloads', 'desktop', 'documents', 'standalone'}
    
    if series_name.lower() in generic_names:
        # If parent is generic, just use the book name
        return book_name
    else:
        # Create series-organized sort title
        return f"{series_name} : {book_name}"


def get_prefixed_title(folder_path, sort_prefix_parent=False, sort_prefix_label=None, custom_prefix=None):
    """
    Generate a title for a folder with optional parent folder prefix.
    
    Args:
        folder_path: Path to the audiobook folder
        sort_prefix_parent: If True, prepend parent folder name
        sort_prefix_label: Label to prepend to parent folder (used with sort_prefix_parent), separated by ' : '
        custom_prefix: Custom prefix string to prepend
    
    Returns:
        str: Title with optional prefix (format: "Label : ParentFolder - BookName" or "ParentFolder - BookName")
    """
    folder_path = Path(folder_path)
    book_name = folder_path.name
    
    # Build prefix
    prefix_parts = []
    
    if custom_prefix:
        prefix_parts.append(custom_prefix)
    
    if sort_prefix_parent:
        parent_name = folder_path.parent.name
        # Skip generic parent names
        generic_names = {'audiobooks', 'books', 'audio', 'media', 'music', 'downloads', 'desktop', 'documents', 'standalone'}
        if parent_name.lower() not in generic_names:
            # If sort_prefix_label is provided, prepend it with ' : ' separator
            if sort_prefix_label:
                parent_name = f"{sort_prefix_label} : {parent_name}"
            prefix_parts.append(parent_name)
    
    # Combine prefix and book name
    if prefix_parts:
        prefix_str = ' - '.join(prefix_parts)
        return f"{prefix_str} - {book_name}"
    else:
        return book_name


def apply_title_suffix(title, suffix):
    """
    Apply a custom suffix to the end of a title.
    
    Args:
        title: The original title
        suffix: The suffix string to append
    
    Returns:
        str: Title with suffix appended (format: "Title - Suffix" or "Title [Suffix]")
    """
    if not suffix or not title:
        return title
    
    # If suffix starts with a special character, append directly
    # Otherwise, append with a space or dash
    if suffix.startswith(('[', '(', '-', '–', '—')):
        return f"{title}{suffix}"
    else:
        return f"{title} - {suffix}"



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
            
            # Set title to filename (like metadata mode)
            file_title = audio_path.stem
            tag_title, filename_base = book_title_style(file_title)
            file_metadata['title'] = tag_title
            
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
            
            # Add sort title if specified
            if sort_as:
                file_metadata['sort_title'] = sort_as
            else:
                # For track-level sort (sort name), use the prefixed album title for proper series grouping
                # This ensures all tracks from this album sort together under the series in iTunes
                if sort_prefix_parent or custom_prefix:
                    file_metadata['sort_title'] = sort_title_base
                else:
                    # Use the original filename without extension for individual track sorting
                    file_metadata['sort_title'] = filename_base
            
            # Apply sort_as_prefix if specified
            if sort_as_prefix:
                file_metadata['sort_title'] = f"{sort_as_prefix}{file_metadata['sort_title']}"
            
            # Set album sort order (for iTunes album grouping/sorting)
            # Use the prefixed sort_title_base so the album sorts correctly as a group
            file_metadata['album_sort'] = sort_title_base
            
            # Extract existing metadata and merge
            try:
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
            
            if apply_mp3_metadata(str(audio_path), file_metadata):
                success_count += 1
            else:
                print(f"[ERROR] Failed to update metadata for: {audio_file}")
        
        # Handle compression if requested (but skip if format conversion + destination - will be handled post-destination)
        should_convert_to_m4a = (output_format == 'm4a') and len(mp3_files) > 0
        skip_early_compression = should_convert_to_m4a and destination
        
        if compress_originals and success_count > 0 and not skip_early_compression:
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
                import shutil
                shutil.rmtree(conversion_output_dir)
            conversion_output_dir.mkdir(parents=True)
            
            conversion_success = 0
            for mp3_file in mp3_files:
                mp3_path = Path(mp3_file)
                m4a_file = conversion_output_dir / f"{mp3_path.stem}.m4a"
                
                print(f"[CONVERT] Converting: {mp3_path.name} -> {m4a_file.name}")
                
                # Extract metadata from the MP3
                try:
                    from mutagen.id3 import ID3
                    id3 = ID3(str(mp3_path))
                    convert_metadata = {
                        'title': str(id3.get('TIT2', '')),
                        'artist': str(id3.get('TPE1', '')),
                        'album': str(id3.get('TALB', '')),
                        'genre': str(id3.get('TCON', '')),
                        'sort_title': str(id3.get('TSOT', '')),
                    }
                    
                    # Extract track number if available
                    if 'TRCK' in id3:
                        track_info = str(id3.get('TRCK', ''))
                        if '/' in track_info:
                            track_num, total = track_info.split('/', 1)
                            convert_metadata['track_number'] = track_num
                            convert_metadata['total_tracks'] = total
                        else:
                            convert_metadata['track_number'] = track_info
                except Exception:
                    convert_metadata = {}
                
                # Convert to M4A
                if convert_to_m4a(str(mp3_path), str(m4a_file), bitrate=bitrate or '128k', metadata=convert_metadata, ffmpeg_path=ffmpeg_path):
                    print(f"[CONVERT] Successfully converted: {m4a_file.name}")
                    conversion_success += 1
                else:
                    print(f"[ERROR] Failed to convert: {mp3_path.name}")
            
            print(f"[CONVERT] Conversion complete: {conversion_success}/{len(mp3_files)} files converted")
            
            # Verify conversion completeness and retry missing files
            verification_success = False
            if conversion_success > 0:
                verification_success = verify_and_retry_conversions(
                    mp3_files, conversion_output_dir, bitrate or '128k', ffmpeg_path
                )
            
            # Only do folder renaming if verification passed
            if verification_success:
                import shutil
                conversion_happened = True
                # Rename the original folder
                original_folder = final_folder_path.parent / f"{final_folder_path.name}_original"
                if not original_folder.exists():
                    final_folder_path.rename(original_folder)
                    print(f"[FOLDER] Original folder renamed to: {original_folder.name}")
                
                # Rename converted folder to original name
                conversion_output_dir.rename(final_folder_path)
                print(f"[FOLDER] Converted folder renamed to: {final_folder_path.name}")
            else:
                # Cleanup failed conversion and cancel processing for this folder
                print(f"[ERROR] Conversion verification failed - cleaning up and canceling folder processing")
                if conversion_output_dir.exists():
                    import shutil
                    shutil.rmtree(conversion_output_dir)
                    print(f"[CLEANUP] Removed incomplete conversion folder")
                return False
        
        # Apply folder-level operations for metadata mode
        
        # Apply custom prefix/suffix to folder name
        if custom_prefix or custom_suffix:
            folder_name = final_folder_path.name
            new_folder_name = folder_name
            
            if custom_prefix:
                new_folder_name = f"{custom_prefix}{new_folder_name}"
            if custom_suffix:
                new_folder_name = f"{new_folder_name}{custom_suffix}"
            
            if new_folder_name != folder_name:
                new_folder_path = final_folder_path.parent / new_folder_name
                if not new_folder_path.exists():
                    final_folder_path.rename(new_folder_path)
                    final_folder_path = new_folder_path
                    print(f"[FOLDER] Renamed folder: {folder_name} -> {new_folder_name}")
                else:
                    print(f"[WARNING] Destination folder already exists: {new_folder_name}")
        
        # Handle destination - move only if conversion happened, copy otherwise
        if destination:
            destination_path = Path(destination)
            destination_path.mkdir(parents=True, exist_ok=True)
            final_destination = destination_path / final_folder_path.name
            
            # Check if destination folder exists to avoid overwriting
            if not final_destination.exists():
                import shutil
                if conversion_happened:
                    # If conversion happened, MOVE the folder to destination
                    shutil.move(str(final_folder_path), str(final_destination))
                    print(f"[FOLDER] Moved converted folder to destination: {final_destination}")
                else:
                    # Otherwise, copy the folder to destination
                    shutil.copytree(str(final_folder_path), str(final_destination))
                    print(f"[FOLDER] Copied folder to destination: {final_destination}")
            else:
                print(f"[WARNING] Destination folder already exists: {final_destination}")
        
        # Restore original folder name if conversion happened and files were moved to destination
        if conversion_happened and destination and conversion_success > 0:
            original_folder = final_folder_path.parent / f"{final_folder_path.name}_original"
            if original_folder.exists():
                try:
                    # Restore the original folder name
                    restored_folder = final_folder_path.parent / final_folder_path.name
                    if not restored_folder.exists():
                        original_folder.rename(restored_folder)
                        print(f"[FOLDER] Restored original folder name: {restored_folder.name}")
                    else:
                        print(f"[WARNING] Cannot restore folder name - target exists: {restored_folder.name}")
                except Exception as e:
                    print(f"[WARNING] Failed to restore original folder name: {e}")
        
        # Handle cleanup of original files after successful destination push
        if conversion_happened and destination and conversion_success > 0:
            destination_success = False
            
            # Check if destination push was successful
            if destination:
                destination_path = Path(destination)
                final_destination = destination_path / final_folder_path.name
                if final_destination.exists():
                    # Verify destination has the expected files
                    dest_m4a_files = list(final_destination.glob("*.m4a"))
                    if len(dest_m4a_files) == conversion_success:
                        destination_success = True
                        print(f"[CLEANUP] Destination push verified: {len(dest_m4a_files)} files at destination")
                    else:
                        print(f"[WARNING] Destination verification failed: expected {conversion_success}, found {len(dest_m4a_files)} files")
            
            # Execute cleanup options if destination push was successful
            if destination_success:
                original_folder = final_folder_path.parent / f"{final_folder_path.name}_original"
                restored_folder = final_folder_path.parent / final_folder_path.name
                
                # Get the list of original MP3 files for cleanup
                cleanup_mp3_files = []
                if restored_folder.exists():
                    cleanup_mp3_files = list(restored_folder.glob("*.mp3"))
                elif original_folder.exists():
                    cleanup_mp3_files = list(original_folder.glob("*.mp3"))
                
                # Handle compression option
                if compress_originals and cleanup_mp3_files:
                    print(f"[CLEANUP] Compressing original files after successful destination push...")
                    compress_success, archive_path = compress_original_files(
                        restored_folder if restored_folder.exists() else original_folder,
                        [str(f) for f in cleanup_mp3_files],
                        final_folder_path.name,
                        delete_originals=delete_originals
                    )
                    if compress_success:
                        print(f"[CLEANUP] ✅ Created archive: {Path(archive_path).name}")
                        if delete_originals:
                            print(f"[CLEANUP] ✅ Original files deleted after compression")
                    else:
                        print(f"[CLEANUP] ❌ Compression failed")
                
                # Handle delete originals option (if not already handled by compression)
                elif delete_originals and cleanup_mp3_files:
                    print(f"[CLEANUP] Deleting original files after successful destination push...")
                    deleted_count = 0
                    for mp3_file in cleanup_mp3_files:
                        try:
                            mp3_file.unlink()
                            deleted_count += 1
                        except Exception as e:
                            print(f"[CLEANUP] ❌ Failed to delete {mp3_file.name}: {e}")
                    
                    if deleted_count == len(cleanup_mp3_files):
                        print(f"[CLEANUP] ✅ Deleted {deleted_count} original MP3 files")
                        
                        # Remove empty folder if all files were deleted
                        folder_to_check = restored_folder if restored_folder.exists() else original_folder
                        if folder_to_check.exists():
                            remaining_files = list(folder_to_check.glob("*"))
                            if not remaining_files:
                                try:
                                    folder_to_check.rmdir()
                                    print(f"[CLEANUP] ✅ Removed empty original folder: {folder_to_check.name}")
                                except Exception as e:
                                    print(f"[CLEANUP] ❌ Failed to remove empty folder: {e}")
                    else:
                        print(f"[CLEANUP] ⚠️ Deleted {deleted_count}/{len(cleanup_mp3_files)} original files")
                
                # Summary message
                if compress_originals or delete_originals:
                    if cleanup_mp3_files:
                        print(f"[CLEANUP] Post-destination cleanup completed")
                    else:
                        print(f"[CLEANUP] No original files found for cleanup")
        
        return success_count == len(all_audio_files)
    
    # If only M4A files with combine_all, skip to combining logic below
    # (The combine_mp3_files function will handle both MP3 and M4A files)
    if not mp3_files and m4a_files and combine_all:
        print(f"\n[M4A-ONLY] M4A-only folder detected - will combine M4A files directly")
        # Use m4a_files as-is in the combining logic below
    
    # Auto-detect bitrate from first audio file if not specified
    if bitrate is None and (mp3_files or m4a_files):
        first_audio_file = mp3_files[0] if mp3_files else m4a_files[0]
        detected_bitrate = detect_mp3_bitrate(first_audio_file) if first_audio_file.endswith('.mp3') else None
        if detected_bitrate:
            bitrate = detected_bitrate
            print(f"[BITRATE] Auto-detected bitrate from first file: {bitrate}")
        else:
            bitrate = '128k'  # Fallback default
            print(f"[BITRATE] Could not detect bitrate, using default: {bitrate}")
    elif bitrate is None:
        bitrate = '128k'
        print(f"[BITRATE] Using default bitrate: {bitrate}")
    
    # Handle single file case - skip combining but still apply metadata
    if len(mp3_files) == 1:
        print(f"\n[SINGLE] Single file detected - applying metadata without combining")
        single_file = Path(mp3_files[0])
        
        # Determine output name for single file
        if not title_name:
            folder_name = folder_path.name
            tag_title, filename_base = book_title_style(folder_name)
            title_name = filename_base
        else:
            tag_title, filename_base = book_title_style(title_name)
            title_name = filename_base
        
        # Determine output directory
        if destination:
            output_dir = Path(destination)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using custom output destination: {output_dir}")
        else:
            output_dir = folder_path
        
        # Set up final output path
        if output_format.lower() == 'mp3':
            final_output = output_dir / f"{title_name}.mp3"
        else:
            final_output = output_dir / f"{title_name}.m4a"
        
        # Copy the single file to the new location (if different)
        if single_file != final_output:
            if output_format.lower() == 'mp3':
                # Copy MP3 and apply metadata
                shutil.copy2(single_file, final_output)
                print(f"Copied single file to: {final_output}")
            else:
                # Convert single MP3 to M4A
                print(f"Converting single file to M4A: {final_output}")
        
        # Prepare metadata
        metadata = {
            'title': tag_title,
            'album': tag_title,
            'genre': 'Audiobook',
            'sort_title': create_series_sort_title(folder_path, is_mp3_folder=True)
        }
        
        if author_name:
            metadata['artist'] = author_name
        
        # Extract existing metadata from the source file
        try:
            existing_metadata = extract_all_metadata(str(single_file))
            if existing_metadata:
                temp_metadata = existing_metadata.copy()
                temp_metadata.pop('title', None)
                temp_metadata.pop('album', None)
                temp_metadata.pop('genre', None)
                metadata.update(temp_metadata)
        except Exception as e:
            print(f"Warning: Could not extract existing metadata: {e}")
        
        # Apply metadata
        if output_format.lower() == 'mp3':
            # Apply metadata to copied MP3
            success = apply_mp3_metadata(str(final_output), metadata)
            if not success:
                print("[ERROR] Failed to apply metadata to single MP3 file")
                return False
        else:
            # Convert to M4A with metadata
            success = convert_to_m4a(str(single_file), str(final_output), bitrate, metadata, ffmpeg_path)
            if not success:
                print("[ERROR] Failed to convert single file to M4A")
                return False
        
        print(f"[SUCCESS] Single file processing complete: {final_output}")
        return True
    
    # If combine_only requested, force MP3 output and skip conversion steps
    if combine_only:
        print("[OPTION] combine-only requested: will combine MP3s and apply MP3 metadata only (no conversion)")
        output_format = 'mp3'

    # Multiple files - proceed with combining
    print(f"Multiple files detected - proceeding with combination")
    
    # If combine_all, prepare M4A files for combining
    all_files_to_combine = mp3_files.copy()
    if combine_all and m4a_files:
        print(f"[COMBINE-ALL] Will include {len(m4a_files)} M4A files in the combination")
        all_files_to_combine.extend(m4a_files)
        print(f"[COMBINE-ALL] Total files to combine: {len(all_files_to_combine)} (MP3: {len(mp3_files)}, M4A: {len(m4a_files)})")
    
    # Determine output name
    if not title_name:
        folder_name = folder_path.name
        tag_title, filename_base = book_title_style(folder_name)
        title_name = filename_base
    else:
        tag_title, filename_base = book_title_style(title_name)
        title_name = filename_base
    
    # Apply title suffix if provided
    if title_suffix:
        title_name = apply_title_suffix(title_name, title_suffix)
        tag_title = apply_title_suffix(tag_title, title_suffix)
        print(f"[TITLE] Applied suffix '{title_suffix}' - Final title: {title_name}")
    
    # Determine output directory
    if destination:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Using custom output destination: {output_dir}")
    else:
        output_dir = folder_path
    
    # Set up paths based on output format
    combined_mp3 = output_dir / f"{title_name}_combined.mp3"
    if output_format.lower() == 'mp3':
        final_output = output_dir / f"{title_name}.mp3"
    else:
        final_output = output_dir / f"{title_name}.m4a"
    
    # Optimize processing based on output format
    if output_format.lower() == 'mp3':
        # FAST MP3 PATH: Direct combine with immediate metadata application
        print(f"\n[START] Fast MP3 Processing: Combining directly to final file...")
        
        # Prepare metadata first
        metadata = {
            'title': tag_title,
            'album': tag_title,
            'genre': 'Audiobook',
            'sort_title': create_series_sort_title(folder_path, is_mp3_folder=True)  # Series : Book format for organization
        }
        
        if author_name:
            metadata['artist'] = author_name
        
        # Try to get any existing metadata from first file
        try:
            if all_files_to_combine:
                existing_metadata = extract_all_metadata(all_files_to_combine[0])
                if existing_metadata:
                    # Add existing metadata but preserve our title/album/genre
                    temp_metadata = existing_metadata.copy()
                    temp_metadata.pop('title', None)
                    temp_metadata.pop('album', None)
                    temp_metadata.pop('genre', None)
                    metadata.update(temp_metadata)
        except Exception:
            pass
        
        # Combine directly to final filename with metadata using ffmpeg
        # If combine_all with M4A files, combine_mp3_files_with_metadata will convert M4A to MP3 first
        success = combine_mp3_files_with_metadata(all_files_to_combine, str(final_output), bitrate, metadata)
        if not success:
            print("Failed to combine files with metadata")
            return False
        
        print(f"[SUCCESS] Fast MP3 processing complete: {final_output}")
        
    else:
        # M4A processing path
        # STANDARD WORKFLOW: Combine then convert
        print(f"\nStep 1: Combining files...")
        
        # With combine_all, include both MP3 and M4A files in combination
        files_to_combine = mp3_files.copy()
        if combine_all and m4a_files:
            print(f"[COMBINE-ALL] Including {len(m4a_files)} M4A file(s) in combination")
            files_to_combine.extend(m4a_files)

        if not files_to_combine:
            print("No audio files found to combine")
            return False

        # Determine present extensions; if mixed, abort since we will NOT convert
        exts = set([Path(f).suffix.lower() for f in files_to_combine])
        if len(exts) > 1:
            print(f"[ERROR] Mixed input formats detected: {exts}. Both combine modes are configured to NOT convert files. Aborting.")
            return False

        input_ext = exts.pop()
        # Final output will preserve the input container (no conversion)
        final_output = output_dir / f"{title_name}{input_ext}"

        print(f"Combining {len(files_to_combine)} files into {final_output.name} without conversion")

        success, combine_metadata = combine_mp3_files(files_to_combine, str(final_output), bitrate)
        if not success:
            print("Failed to combine files without conversion")
            return False
    
    print('Processing complete')
    
    # Step 3: Delete combined MP3 if requested (only applies to M4A path)
    if delete_combined and output_format.lower() == 'm4a':
        try:
            os.remove(str(combined_mp3))
            print(f'Deleted combined file: {combined_mp3}')
        except Exception as e:
            print(f'Warning: Failed to delete combined file {combined_mp3}: {e}')
    
    # Step 4: Compress original files if requested
    if compress_originals:
        compress_success, archive_path = compress_original_files(
            folder_path, mp3_files, title_name, delete_originals
        )
        if compress_success:
            print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
        else:
            print(f"[WARNING]  Compression failed, but {output_format.upper()} processing was successful")
    
    print(f"\nSuccess! Created: {final_output}")
    return True


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
        
        if mp3_path.suffix.lower() != '.mp3':
            print(f"[WARNING] Skipping non-MP3 file: {mp3_file}")
            continue
        
        # Prepare file-specific metadata
        file_metadata = metadata.copy()
        
        # Set default title to filename if not specified
        title_arg = getattr(args, 'title', None) or getattr(args, 'title_name', None)
        if not title_arg:
            # Use filename without extension as default title
            default_title = mp3_path.stem
            # Apply book title styling
            tag_title, filename_base = book_title_style(default_title)
            file_metadata['title'] = tag_title
        else:
            # Use provided title with book styling
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
                input_path = Path(args.input)
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