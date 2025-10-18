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
    - Use parent folder name as title/album
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
    
    # Remove trailing patterns like "_combined" or " combined"
    s = re.sub(r'[\s_]*(combined|_combined)$', '', s, flags=re.IGNORECASE)
    
    # Convert separators to spaces (dashes, underscores)
    s = s.replace('_', ' ')
    s = s.replace('-', ' ')
    s = s.replace(':', ' ')
    
    # Remove years in parentheses and extra content in brackets
    s = re.sub(r'\(\d{4}\)', '', s)
    s = re.sub(r'\[.*?\]', '', s)
    
    # Remove leading numbers and patterns:
    # "04 Title" → "Title"
    # "1 Title" → "Title" 
    # "Book 3 Title" → "Title"
    # "Chapter 5 Title" → "Title"
    s = re.sub(r'^\d+[\s\.]*', '', s)  # Remove leading numbers with separators
    s = re.sub(r'^(Book|Chapter|Vol|Volume|Part)\s*\d*[\s]*', '', s, flags=re.IGNORECASE)  # Remove prefixes
    
    # Remove embedded numbers that look like series/book numbers
    s = re.sub(r'\s+(Book|Vol|Volume|Part)\s*\d+', '', s, flags=re.IGNORECASE)
    
    # Remove standalone years and numbers (but preserve things like "1984" if it's the title)
    words = s.split()
    filtered_words = []
    for i, word in enumerate(words):
        # Skip standalone numbers unless it might be a meaningful part of the title
        if word.isdigit():
            # Keep if it's a famous year/number that might be a title (like "1984")
            if word in ['1984', '2001', '2010', '451'] or len(word) != 4:
                # Skip most numbers, but keep famous book numbers
                if not (len(word) <= 2 and i < len(words) - 1):  # Skip small numbers unless at end
                    continue
        filtered_words.append(word)
    
    s = ' '.join(filtered_words)
    
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


def extract_all_metadata(mp3_file):
    """Extract metadata, cover art, and chapters from an MP3 file."""
    try:
        from mutagen.id3 import ID3
        from mutagen.mp3 import MP3
        
        metadata = {}
        
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


def export_with_progress(audio_segment, output_path, format='mp3', bitrate='32k', total_duration_ms=None):
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

    ok = convert_to_m4a(str(input_path), str(output_path), bitrate=args.bitrate, metadata=metadata, ffmpeg_path=args.ffmpeg_path)
    if not ok:
        print('Conversion failed')
        return False
    
    print('Conversion complete')
    
    # Delete the input file if requested and conversion was successful
    if args.delete_input:
        try:
            os.remove(str(input_path))
            print(f'Deleted input file: {input_path}')
        except Exception as e:
            print(f'Warning: Failed to delete input file {input_path}: {e}')
    
    return True


def process_combine_command(args):
    """Process the combine command with the given arguments."""
    # Determine output path
    if args.output:
        output_path = Path(args.output)
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
        success, metadata = combine_mp3_files(args.files, str(temp_mp3), args.bitrate)
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


def export_large_audio_chunked(audio_segment, output_path, format='mp3', bitrate='192k'):
    """Export extremely large audio files (20+ hours) using chunked approach."""
    # This is a fallback for the chunked method
    return export_large_with_ffmpeg(audio_segment, output_path, bitrate)


def combine_mp3_files(mp3_files, output_file, bitrate='32k'):
    """Combine multiple MP3 files into a single file."""
    print(f"Combining {len(mp3_files)} files:")
    for f in mp3_files:
        print(f"  - {os.path.basename(f)}")
    
    try:
        combined = AudioSegment.empty()
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
        if not cover_source:
            metadata = extract_all_metadata(mp3_files[0])
            combined_metadata.update(metadata)
        
        # Optimized loading with memory management
        for i, mp3_file in enumerate(tqdm(mp3_files, desc="Combining files", unit="file")):
            # Load with optimized parameters for speed
            audio = AudioSegment.from_mp3(mp3_file)
            combined += audio
            
            # Clear individual audio from memory immediately
            del audio
            
            # Force garbage collection every 10 files to manage memory
            if (i + 1) % 10 == 0:
                import gc
                gc.collect()
        
        print(f"Exporting combined file to: {output_file}")
        success = export_with_progress(combined, output_file, format='mp3', bitrate=bitrate, total_duration_ms=len(combined))
        
        if success:
            # After creating the combined file, embed the cover art if we found one
            if combined_metadata.get('cover_path'):
                try:
                    print(f"[COVER] Embedding cover art in combined file...")
                    from mutagen.id3 import ID3, APIC
                    
                    # Load the combined file's ID3 tags
                    try:
                        id3 = ID3(output_file)
                    except:
                        id3 = ID3()
                    
                    # Read the cover image
                    cover_path = combined_metadata['cover_path']
                    if os.path.exists(cover_path):
                        with open(cover_path, 'rb') as cover_file:
                            cover_data = cover_file.read()
                        
                        # Add cover art to the combined file
                        id3.add(APIC(
                            encoding=3,
                            mime='image/jpeg' if cover_path.lower().endswith(('.jpg', '.jpeg')) else 'image/png',
                            type=3,  # Cover (front)
                            desc='Cover',
                            data=cover_data
                        ))
                        
                        # Save the ID3 tags
                        id3.save(output_file)
                        print(f"[SUCCESS] Cover art embedded in combined file")
                    
                except Exception as e:
                    print(f"[WARNING]  Failed to embed cover art in combined file: {e}")
            
            duration_ms = len(combined)
            combined_metadata['duration_ms'] = duration_ms
            print(f"Successfully combined {len(mp3_files)} files!")
            print(f"Total duration: {duration_ms / 60000:.1f} minutes")
            return True, combined_metadata
        else:
            return False, {}
            
    except Exception as e:
        print(f"[ERROR] Failed to combine files: {e}")
        return False, {}


def combine_mp3_files_with_metadata(mp3_files, output_file, bitrate='32k', metadata=None):
    """
    Fast MP3 processing: Combine files and apply metadata in one optimized step.
    For combine-only mode, uses ffmpeg concatenation to preserve original quality.
    Otherwise uses pydub for combining with potential re-encoding.
    """
    if not mp3_files:
        print("[ERROR] No MP3 files provided")
        return False

    print(f"Combining {len(mp3_files)} files directly with metadata:")
    for mp3_file in mp3_files:
        print(f"  - {Path(mp3_file).name}")

    try:
        # For combine-only: Use ffmpeg concatenation to preserve original quality
        if bitrate == 'preserve' or bitrate == 'original':
            return combine_mp3_files_ffmpeg_concat(mp3_files, output_file, metadata)

        # Step 1: Combine files using pydub (fast)
        combined = AudioSegment.empty()

        # Use tqdm for progress
        try:
            from tqdm import tqdm
            file_iterator = tqdm(mp3_files, desc="Combining files", unit="file")
        except ImportError:
            file_iterator = mp3_files

        for mp3_file in file_iterator:
            try:
                audio = AudioSegment.from_mp3(mp3_file)
                combined += audio
            except Exception as e:
                print(f"[WARNING]  Warning: Could not load {mp3_file}: {e}")
                continue

        if len(combined) == 0:
            print("[ERROR] No audio data to export")
            return False

        # Step 2: Export directly to final filename with pydub
        print(f"Exporting combined file to: {output_file}")

        # Create temporary file in temp directory (not destination)
        import tempfile
        temp_fd, temp_file = tempfile.mkstemp(suffix='.mp3', prefix='audiobook_combine_')
        os.close(temp_fd)  # Close the file descriptor, we'll open it again

        # Simple export without broken progress bar
        print(f"Exporting to temporary file: {temp_file}")
        combined.export(temp_file, format="mp3", bitrate=bitrate)

        file_size = Path(temp_file).stat().st_size
        print(f"Export complete {Path(output_file).name} {file_size / 1024:.1f}KB")

        # Step 3: Apply metadata directly to the exported file
        if metadata:
            print("Applying metadata to combined file...")
            # Add small delay to ensure file handle is released on Windows
            import time
            time.sleep(0.5)
            success = apply_mp3_metadata(temp_file, metadata)
            if not success:
                print("[WARNING]  Warning: Metadata application failed, but file was created")

        # Step 4: Atomically move to final location
        shutil.move(temp_file, output_file)

        # Report final statistics
        duration_minutes = len(combined) / 60000
        final_size = Path(output_file).stat().st_size

        print(f"[SUCCESS] Fast MP3 combine complete!")
        print(f"   Final file: {Path(output_file).name}")
        print(f"   Duration: {duration_minutes:.1f} minutes")
        print(f"   Size: {final_size / 1024:.1f} KB")

        return True

    except Exception as e:
        # Clean up temp file if it exists
        if 'temp_file' in locals() and Path(temp_file).exists():
            try:
                Path(temp_file).unlink()
            except:
                pass

        print(f"[ERROR] Failed to combine MP3 files with metadata: {e}")
        return False


def combine_mp3_files_ffmpeg_concat(mp3_files, output_file, metadata=None):
    """
    Concatenate MP3 files using ffmpeg without re-encoding (preserves original quality).
    Much faster than pydub for combine-only operations.
    """
    import tempfile
    import subprocess

    try:
        # Create temporary concat file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as concat_file:
            concat_path = concat_file.name
            for mp3_file in mp3_files:
                # Escape single quotes in filename for ffmpeg
                escaped_file = str(Path(mp3_file)).replace("'", "\\'")
                concat_file.write(f"file '{escaped_file}'\n")

        # Create temporary output file in temp directory (not destination)
        import tempfile
        temp_fd, temp_output = tempfile.mkstemp(suffix='.mp3', prefix='audiobook_concat_')
        os.close(temp_fd)  # Close the file descriptor

        # Use ffmpeg to concatenate without re-encoding
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', concat_path,
            '-c', 'copy',  # No re-encoding
            '-f', 'mp3',   # Specify output format
            '-y',  # Overwrite output
            temp_output
        ]

        print(f"Concatenating {len(mp3_files)} MP3 files with ffmpeg (no re-encoding)...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            print(f"[ERROR] ffmpeg concatenation failed: {result.stderr}")
            # Clean up
            Path(concat_path).unlink(missing_ok=True)
            Path(temp_output).unlink(missing_ok=True)
            return False

        # Clean up concat file
        Path(concat_path).unlink(missing_ok=True)

        # Apply metadata to the concatenated file
        if metadata:
            print("Applying metadata to concatenated file...")
            import time
            time.sleep(0.5)  # Ensure file handle is released
            success = apply_mp3_metadata(temp_output, metadata)
            if not success:
                print("[WARNING]  Warning: Metadata application failed, but file was created")

        # Move to final location
        shutil.move(temp_output, output_file)

        # Report statistics
        final_size = Path(output_file).stat().st_size
        print(f"[SUCCESS] MP3 concatenation complete!")
        print(f"   Final file: {Path(output_file).name}")
        print(f"   Size: {final_size / 1024:.1f} KB")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to concatenate MP3 files: {e}")
        # Clean up any temp files
        for temp_file in [temp_output if 'temp_output' in locals() else None, concat_path if 'concat_path' in locals() else None]:
            if temp_file and Path(temp_file).exists():
                Path(temp_file).unlink(missing_ok=True)
        return False


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
    """Get duration of audio file in seconds."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(input_file)
        if audio and hasattr(audio.info, 'length') and audio.info.length:
            return float(audio.info.length)
    except Exception:
        pass

    try:
        probe = ffprobe_path or shutil.which('ffprobe')
        if probe:
            cmd = [probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
            res = subprocess.run(cmd, capture_output=True, text=True)
            out = res.stdout.strip()
            if out:
                return float(out)
    except Exception:
        pass

    return None


def apply_mp3_metadata(mp3_file, metadata):
    """Apply metadata to an MP3 file using mutagen."""
    try:
        from mutagen.id3 import ID3NoHeaderError, ID3, TIT2, TPE1, TALB, TDRC, TCON, TSOT, APIC
        
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
            except Exception as e:
                print(f"Warning: Could not add cover art: {e}")
        
        # Save the tags
        id3.save(mp3_file)
        print(f"Applied metadata to {mp3_file}")
        return True
        
    except Exception as e:
        print(f"Error applying MP3 metadata: {e}")
        return False


def convert_to_m4a(input_file, output_file, bitrate='32k', metadata=None, ffmpeg_path='ffmpeg'):
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


def find_mp3_folders(root_path, min_files=1):
    """Recursively find all folders containing MP3 files.
    
    Args:
        root_path: Root directory to search
        min_files: Minimum number of MP3 files required to mark a folder
        
    Returns:
        List of folder paths that contain MP3 files
    """
    root_path = Path(root_path)
    mp3_folders = []
    
    print(f"Scanning for folders with MP3 files in: {root_path}")
    
    # Walk through all subdirectories
    for folder_path in root_path.rglob('*'):
        if folder_path.is_dir():
            # Count MP3 files in this specific folder (not subdirectories)
            mp3_files = list(folder_path.glob('*.mp3'))
            if len(mp3_files) >= min_files:
                mp3_folders.append(folder_path)
                print(f"  Found: {folder_path} ({len(mp3_files)} MP3 files)")
    
    return mp3_folders


def process_multiple_folders(folders, bitrate='32k', ffmpeg_path='ffmpeg', delete_combined=False, compress_originals=False, delete_originals=False, parallel=False, output_format='m4a', destination=None, convert_first=False, combine_only=False):
    """Process multiple folders containing MP3 files.
    
    Args:
        folders: List of folder paths to process
        bitrate: Audio bitrate for processing
        ffmpeg_path: Path to ffmpeg executable
        delete_combined: Whether to delete combined MP3 after conversion
        parallel: Whether to process folders in parallel (True) or sequentially (False)
    convert_first: Whether to convert individual MP3s first, then combine (True) or combine first, then convert (False)
    combine_only: If True, only combine MP3s and apply MP3 metadata (no conversion to M4A)
        
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
            
            # Determine destination for this folder
            folder_destination = None
            if destination:
                # Place files directly in the destination directory (no subdirectories)
                folder_destination = Path(destination)
                # Ensure the destination directory exists
                folder_destination.mkdir(parents=True, exist_ok=True)
            
            # Use convert_first parameter only when explicitly set
            use_convert_first = convert_first
            
            success = process_folder(
                str(folder_path), 
                output_name=None,  # Use folder name
                bitrate=bitrate, 
                ffmpeg_path=ffmpeg_path, 
                delete_combined=delete_combined,
                compress_originals=compress_originals,
                delete_originals=delete_originals,
                output_format=output_format,
                    destination=str(folder_destination) if folder_destination else None,
                    convert_first=use_convert_first,
                    combine_only=combine_only
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


def process_folder(folder_path, output_name=None, bitrate='32k', ffmpeg_path='ffmpeg', delete_combined=False, compress_originals=False, delete_originals=False, output_format='m4a', destination=None, convert_first=False, combine_only=False):
    """Process a folder: combine MP3s and convert to M4A or keep as MP3 with metadata.
    
    Args:
        convert_first: If True, convert individual MP3s first, then combine.
                       If False (default), combine first, then convert.
    """
    folder_path = Path(folder_path)
    if not folder_path.exists():
        print(f"Folder not found: {folder_path}")
        return False
    
    # Check if this folder contains MP3 files directly
    mp3_files = sorted([str(f) for f in folder_path.glob('*.mp3')])
    
    # If no MP3 files in current folder, check for subfolders with MP3 files
    if not mp3_files:
        print(f"No MP3 files found directly in: {folder_path}")
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
                output_name=None,  # Use subfolder name
                bitrate=bitrate,
                ffmpeg_path=ffmpeg_path,
                delete_combined=delete_combined,
                compress_originals=compress_originals,
                delete_originals=delete_originals,
                output_format=output_format,
                destination=destination
            )
            
            if not success:
                print(f"[ERROR] Failed to process subfolder: {subfolder.name}")
                all_success = False
            else:
                print(f"[SUCCESS] Successfully processed subfolder: {subfolder.name}")
        
        return all_success
    
    print(f"Found {len(mp3_files)} MP3 files in {folder_path}")
    
    # Handle single file case - skip combining but still apply metadata
    if len(mp3_files) == 1:
        print(f"\n[SINGLE] Single file detected - applying metadata without combining")
        single_file = Path(mp3_files[0])
        
        # Determine output name for single file
        if not output_name:
            folder_name = folder_path.name
            folder_name = folder_name.replace('combined', '').replace('Combined', '')
            tag_title, filename_base = book_title_style(folder_name)
            output_name = filename_base
        else:
            tag_title, filename_base = book_title_style(output_name)
            output_name = filename_base
        
        # Determine output directory
        if destination:
            output_dir = Path(destination)
            output_dir.mkdir(parents=True, exist_ok=True)
            print(f"Using custom output destination: {output_dir}")
        else:
            output_dir = folder_path
        
        # Set up final output path
        if output_format.lower() == 'mp3':
            final_output = output_dir / f"{output_name}.mp3"
        else:
            final_output = output_dir / f"{output_name}.m4a"
        
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
    
    # Determine output name
    if not output_name:
        folder_name = folder_path.name
        folder_name = folder_name.replace('combined', '').replace('Combined', '')
        tag_title, filename_base = book_title_style(folder_name)
        output_name = filename_base
    else:
        tag_title, filename_base = book_title_style(output_name)
        output_name = filename_base
    
    # Determine output directory
    if destination:
        output_dir = Path(destination)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Using custom output destination: {output_dir}")
    else:
        output_dir = folder_path
    
    # Set up paths based on output format
    combined_mp3 = output_dir / f"{output_name}_combined.mp3"
    if output_format.lower() == 'mp3':
        final_output = output_dir / f"{output_name}.mp3"
    else:
        final_output = output_dir / f"{output_name}.m4a"
    
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
        
        # Try to get any existing metadata from first file
        try:
            if mp3_files:
                existing_metadata = extract_all_metadata(mp3_files[0])
                if existing_metadata:
                    # Add existing metadata but preserve our title/album/genre
                    temp_metadata = existing_metadata.copy()
                    temp_metadata.pop('title', None)
                    temp_metadata.pop('album', None)
                    temp_metadata.pop('genre', None)
                    metadata.update(temp_metadata)
        except Exception:
            pass
        
        # Combine directly to final filename with metadata
        # Use 'preserve' bitrate for combine-only to avoid re-encoding
        combine_bitrate = 'preserve' if combine_only else bitrate
        success = combine_mp3_files_with_metadata(mp3_files, str(final_output), combine_bitrate, metadata)
        if not success:
            print("Failed to combine MP3 files with metadata")
            return False
        
        print(f"[SUCCESS] Fast MP3 processing complete: {final_output}")
        
    else:
        # M4A processing - choose workflow based on convert_first parameter
        if convert_first:
            # CONVERT-FIRST WORKFLOW: Convert each MP3 to M4A, then combine M4As
            print(f"\n[CONVERT-FIRST] Converting individual MP3 files to M4A...")
            
            converted_m4a_files = []
            import tempfile
            import shutil
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Step 1: Convert each MP3 to M4A individually
                for i, mp3_file in enumerate(mp3_files, 1):
                    print(f"Converting {i}/{len(mp3_files)}: {Path(mp3_file).name}")
                    m4a_file = Path(temp_dir) / f"converted_{i:03d}.m4a"
                    
                    # Convert single MP3 to M4A
                    success = convert_to_m4a(mp3_file, str(m4a_file), bitrate, {}, ffmpeg_path)
                    if not success:
                        print(f"Failed to convert {mp3_file}")
                        return False
                    
                    converted_m4a_files.append(str(m4a_file))
                
                # Step 2: Combine the converted M4A files
                print(f"\n[CONVERT-FIRST] Combining {len(converted_m4a_files)} M4A files...")
                
                # Prepare metadata
                metadata = {
                    'title': tag_title,
                    'album': tag_title,
                    'genre': 'Audiobook',
                    'sort_title': create_series_sort_title(folder_path, is_mp3_folder=True)
                }
                
                # For M4A combination, we need to use a different approach since pydub might not handle M4A combination well
                # Use ffmpeg to concatenate M4A files
                concat_file = Path(temp_dir) / "concat_list.txt"
                with open(concat_file, 'w') as f:
                    for m4a_file in converted_m4a_files:
                        f.write(f"file '{m4a_file}'\n")
                
                # Use ffmpeg to concatenate
                ffmpeg_cmd = [
                    ffmpeg_path, '-y', '-f', 'concat', '-safe', '0',
                    '-i', str(concat_file), '-c', 'copy', str(final_output)
                ]
                
                result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    print(f"Failed to combine M4A files: {result.stderr}")
                    return False
                
                # Apply metadata to the final M4A file
                final_metadata = {
                    'title': tag_title,
                    'album': tag_title,
                    'genre': 'Audiobook',
                    'sort_title': create_series_sort_title(folder_path, is_mp3_folder=True)
                }
                
                # Try to get metadata from the first converted file to preserve additional info
                if converted_m4a_files:
                    first_m4a_metadata = extract_all_metadata(converted_m4a_files[0])
                    if first_m4a_metadata:
                        # Preserve cover art and chapters if available
                        if first_m4a_metadata.get('cover_path'):
                            final_metadata['cover_path'] = first_m4a_metadata['cover_path']
                        if first_m4a_metadata.get('chapters'):
                            final_metadata['chapters'] = first_m4a_metadata['chapters']
                
                # Apply metadata using mutagen
                try:
                    from mutagen.mp4 import MP4, MP4Cover
                    mp4 = MP4(str(final_output))
                    if final_metadata.get('title'):
                        mp4['\xa9nam'] = [str(final_metadata.get('title'))]
                    if final_metadata.get('album'):
                        mp4['\xa9alb'] = [str(final_metadata.get('album'))]
                    if final_metadata.get('sort_title'):
                        mp4['sonm'] = [str(final_metadata.get('sort_title'))]  # Sort Title
                    mp4['\xa9gen'] = [final_metadata.get('genre') or 'Audiobook']
                    try:
                        mp4['stik'] = [2]  # Audiobook
                    except Exception:
                        pass
                    cover_path = final_metadata.get('cover_path')
                    if cover_path and os.path.exists(cover_path):
                        with open(cover_path, 'rb') as cf:
                            cover_data = cf.read()
                        fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
                        mp4['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
                    mp4.save()
                    print("Metadata applied to combined M4A file")
                except Exception as e:
                    print(f"Warning: Failed to apply metadata to combined M4A: {e}")
                
        else:
            # STANDARD WORKFLOW: Combine then convert
            print(f"\nStep 1: Combining MP3 files...")
            success, combine_metadata = combine_mp3_files(mp3_files, str(combined_mp3), bitrate)
            if not success:
                print("Failed to combine MP3 files")
                return False
            
            # Prepare metadata
            metadata = {
                'title': tag_title,
                'album': tag_title,
                'genre': 'Audiobook',
                'sort_title': create_series_sort_title(folder_path, is_mp3_folder=True)  # Series : Book format for organization
            }
            # Add metadata from combine step but preserve our title, album, and genre
            temp_metadata = combine_metadata.copy()
            temp_metadata.pop('title', None)  # Remove title from combined metadata
            temp_metadata.pop('album', None)  # Remove album from combined metadata
            temp_metadata.pop('genre', None)  # Remove genre from combined metadata
            metadata.update(temp_metadata)
            
            print(f"\nStep 2: Converting to M4A...")
            success = convert_to_m4a(str(combined_mp3), str(final_output), bitrate, metadata, ffmpeg_path)
            if not success:
                print("Failed to convert to M4A")
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
            folder_path, mp3_files, output_name, delete_originals
        )
        if compress_success:
            print(f"[COMPRESS] Created archive: {Path(archive_path).name}")
        else:
            print(f"[WARNING]  Compression failed, but {output_format.upper()} processing was successful")
    
    print(f"\nSuccess! Created: {final_output}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Audiobook Processor - Combine MP3s and convert to M4A')
    
    # Mode selection
    subparsers = parser.add_subparsers(dest='mode', help='Processing mode')
    
    # Batch processing mode (NEW)
    batch_parser = subparsers.add_parser('batch', help='Process multiple folders recursively')
    batch_parser.add_argument('root_path', help='Root directory to scan for folders with MP3 files')
    batch_parser.add_argument('-d', '--destination', help='Destination directory for processed files (default: same as source)')
    batch_parser.add_argument('-f', '--format', choices=['m4a', 'mp3'], default='m4a', help='Output format: m4a (default) or mp3')
    batch_parser.add_argument('-b', '--bitrate', default='192k', help='Audio bitrate (e.g., 192k)')
    batch_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    batch_parser.add_argument('--parallel', action='store_true', help='Process folders in parallel (faster but uses more resources)')
    batch_parser.add_argument('--min-files', type=int, default=2, help='Minimum number of MP3 files required to process a folder (default: 2)')
    batch_parser.add_argument('--compress-originals', action='store_true', help='Compress original MP3 files into ZIP archives')
    batch_parser.add_argument('--delete-originals', action='store_true', help='Delete original MP3 files after compression (requires --compress-originals)')
    batch_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    batch_parser.add_argument('--convert-first', action='store_true', help='Convert individual MP3 files to M4A first, then combine (default: combine first, then convert)')
    batch_parser.add_argument('--combine-only', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A')
    batch_parser.add_argument('--batch-size', type=int, default=5, help='Number of folders to process in each batch (default: 5)')
    # Note: Combined files are automatically deleted in batch mode to save disk space
    
    # Folder processing mode
    folder_parser = subparsers.add_parser('folder', help='Process entire folder')
    folder_parser.add_argument('folder_path', help='Path to folder containing MP3 files')
    folder_parser.add_argument('-d', '--destination', help='Destination directory for processed files (default: same as source)')
    folder_parser.add_argument('-o', '--output-name', help='Output filename base (without extension)')
    folder_parser.add_argument('-f', '--format', choices=['m4a', 'mp3'], default='m4a', help='Output format: m4a (default) or mp3')
    folder_parser.add_argument('-b', '--bitrate', default='192k', help='Audio bitrate (e.g., 192k)')
    folder_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    folder_parser.add_argument('--delete-combined', action='store_true', help='Delete combined MP3 after conversion')
    folder_parser.add_argument('--combine-only', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A')
    folder_parser.add_argument('--compress-originals', action='store_true', help='Compress original MP3 files into ZIP archive')
    folder_parser.add_argument('--delete-originals', action='store_true', help='Delete original MP3 files after compression (requires --compress-originals)')
    folder_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    
    # Manual mode (combine specific files)
    manual_parser = subparsers.add_parser('combine', help='Combine specific MP3 files')
    manual_parser.add_argument('files', nargs='+', help='MP3 files to combine')
    manual_parser.add_argument('-o', '--output', help='Output file (MP3 or M4A). If not specified, uses first input filename with appropriate extension')
    manual_parser.add_argument('-d', '--destination', help='Destination directory for output file (default: same as first input file)')
    manual_parser.add_argument('-b', '--bitrate', default='192k', help='Audio bitrate (e.g., 192k)')
    manual_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    manual_parser.add_argument('--delete-combined', action='store_true', help='Delete combined MP3 after M4A conversion')
    manual_parser.add_argument('--combine-only', action='store_true', help='Only combine MP3s and apply metadata, do not convert to M4A')
    manual_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    
    # Convert mode (convert existing MP3 to M4A)
    convert_parser = subparsers.add_parser('convert', help='Convert MP3 to M4A')
    convert_parser.add_argument('-i', '--input', required=True, help='Input MP3 file')
    convert_parser.add_argument('-o', '--output', help='Output M4A file. If not specified, uses input filename with .m4a extension')
    convert_parser.add_argument('-d', '--destination', help='Destination directory for output file (default: same as input file)')
    convert_parser.add_argument('-b', '--bitrate', default='192k', help='AAC bitrate (e.g., 192k)')
    convert_parser.add_argument('--ffmpeg-path', default='ffmpeg', help='Path to ffmpeg executable')
    convert_parser.add_argument('--metadata-json', help='Optional JSON file with metadata')
    convert_parser.add_argument('--delete-input', action='store_true', help='Delete input file after conversion')
    convert_parser.add_argument('--long-running', action='store_true', help='Prevent system sleep during processing (requires power_manager.py)')
    
    args = parser.parse_args()
    
    if not args.mode:
        parser.print_help()
        return
    
    # Set up ffmpeg
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
            # Find all folders with MP3 files (original batch behavior)
            mp3_folders = find_mp3_folders(args.root_path, args.min_files)
        
        if not mp3_folders:
            print(f"No folders with {args.min_files}+ MP3 files found in: {args.root_path}")
            if len(root_mp3_files) > 0:
                print(f"Found {len(root_mp3_files)} MP3 files in root, but need at least {args.min_files}")
            sys.exit(1)
        
        print(f"\nFound {len(mp3_folders)} folders to process:")
        for folder in mp3_folders:
            mp3_count = len(list(folder.glob('*.mp3')))
            print(f"  [FOLDER] {folder} ({mp3_count} files)")
        
        # Validate compression options
        if args.delete_originals and not args.compress_originals:
            print("[ERROR] --delete-originals requires --compress-originals")
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
                        convert_first=getattr(args, 'convert_first', False),
                        combine_only=getattr(args, 'combine_only', False)
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
                    convert_first=getattr(args, 'convert_first', False),
                    combine_only=getattr(args, 'combine_only', False)
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
        if args.delete_originals and not args.compress_originals:
            print("[ERROR] Error: --delete-originals requires --compress-originals")
            sys.exit(1)
        
        # Check if power management should be used
        use_power_management = POWER_MANAGEMENT_AVAILABLE and args.long_running
        
        if use_power_management:
            print("[POWER] Starting long-running session with power management...")
            with ProcessingSession("folder_processing") as session:
                session.log_message("FOLDER_START", f"Processing folder: {args.folder_path}")
                success = process_folder(
                    args.folder_path, 
                    args.output_name, 
                    args.bitrate, 
                    args.ffmpeg_path, 
                    args.delete_combined,
                    args.compress_originals,
                    args.delete_originals,
                    args.format,
                    args.destination,
                    convert_first=getattr(args, 'convert_first', False),
                    combine_only=getattr(args, 'combine_only', False)
                )
                session.log_message("FOLDER_COMPLETE", f"Folder processing {'successful' if success else 'failed'}")
        else:
            success = process_folder(
                args.folder_path, 
                args.output_name, 
                args.bitrate, 
                args.ffmpeg_path, 
                args.delete_combined,
                args.compress_originals,
                args.delete_originals,
                args.format,
                args.destination,
                convert_first=getattr(args, 'convert_first', False),
                combine_only=getattr(args, 'combine_only', False)
            )
        sys.exit(0 if success else 1)
        
    elif args.mode == 'combine':
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
        sys.exit(0 if success else 1)
            
    elif args.mode == 'convert':
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
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()