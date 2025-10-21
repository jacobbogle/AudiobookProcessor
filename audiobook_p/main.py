import glob
import os
"""Audiobook P - Main CLI entrypoint for audiobook processing"""

import argparse
import json
import shutil
import sys
import tempfile

# Auto-install required packages
try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TXXX, TPE2, TCOM, TPOS, TSOP, TSO2
except ImportError:
    print("mutagen not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TXXX, TPE2, TCOM, TPOS, TSOP, TSO2

# Import functions from utils
try:
    import sys
    import os
    # Add the parent directory (AudiobookProcessor root) to the Python path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(script_dir)
    sys.path.insert(0, parent_dir)

    from audiobook_processor.utils import novel_verify, series_verify, batch_verify, book_title_logic, remove_track_numbers
except ImportError as e:
    # Fallback if import fails
    novel_verify = None
    series_verify = None
    batch_verify = None
    book_title_logic = lambda x: x  # No-op fallback
    remove_track_numbers = lambda x: x  # No-op fallback


def extract_metadata_from_file(file_path):
    """
    Extract metadata from a single file using the combined-metadata-mapping.json.
    Returns a dict with descriptive keys and their values.
    """
    # Find the mapping file relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')

    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = MutagenFile(file_path)
    if audio is None:
        raise ValueError("Could not load audio file: {}".format(file_path))

    extracted = {}
    
    # Combine all metadata sections from the new mapping structure
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    for desc_key, info in all_fields.items():
        # Get mutagen keys from the new structure
        mutagen_keys = info.get('mutagen_keys', {})
        tags = []
        
        # Add both MP4 and ID3 tags if available
        if 'mp4' in mutagen_keys:
            tags.append(mutagen_keys['mp4'])
        if 'id3' in mutagen_keys:
            tags.append(mutagen_keys['id3'])
            
        # Handle special cases for cover art
        if desc_key == 'picture':
            tags.extend(['covr', 'APIC:'])
        
        value = None

        # Try each tag until we find a value
        for tag in tags:
            if hasattr(audio, 'tags') and audio.tags:
                if tag in audio.tags:
                    raw_value = audio.tags[tag]
                    # Handle different types
                    if isinstance(raw_value, list):
                        if len(raw_value) > 0:
                            item = raw_value[0]
                            if isinstance(item, (str, int, float)):
                                value = item
                            elif hasattr(item, 'text'):
                                # Handle ID3 frames and other objects with text attribute
                                text_value = item.text
                                if isinstance(text_value, list) and len(text_value) > 0:
                                    value = text_value[0]
                                else:
                                    value = text_value
                            else:
                                # Handle binary objects like cover art - mark as present
                                if desc_key == 'picture':
                                    value = 'Present'
                                else:
                                    continue
                    elif isinstance(raw_value, (str, int, float)):
                        value = raw_value
                    elif hasattr(raw_value, 'text'):
                        # Handle ID3 frames directly
                        text_value = raw_value.text
                        if isinstance(text_value, list) and len(text_value) > 0:
                            value = text_value[0]
                        else:
                            value = text_value
                    else:
                        # Handle binary objects like cover art - mark as present
                        if desc_key == 'picture':
                            value = 'Present'
                        else:
                            continue
                    break
            # For some formats, tags might be direct attributes
            elif hasattr(audio, tag):
                raw_value = getattr(audio, tag)
                if isinstance(raw_value, (str, int, float)):
                    value = raw_value
                elif isinstance(raw_value, list) and len(raw_value) > 0:
                    item = raw_value[0]
                    if isinstance(item, (str, int, float)):
                        value = item
                    elif hasattr(item, 'text'):
                        value = item.text
                    else:
                        # Handle binary objects like cover art - mark as present
                        if desc_key == 'picture':
                            value = 'Present'
                        else:
                            continue
                else:
                    # Handle binary objects like cover art - mark as present
                    if desc_key == 'picture':
                        value = 'Present'
                    else:
                        continue
                break

        # If no value found, use empty
        if value is None:
            value = ''

        extracted[desc_key] = value

    return extracted


def extract_metadata_from_folder(folder_path, folder_type):
    """
    Extract metadata from all audio files in a folder.
    Returns a dict with folder type, folder path, and file paths as keys with their metadata as values.
    """
    folder_path = folder_path
    if not os.path.isdir(folder_path):
        raise ValueError("Path is not a directory: {}".format(folder_path))

    # Find all audio files in the folder
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))

    if not audio_files:
        raise ValueError("No audio files found in: {}".format(folder_path))

    # Sort files alphabetically
    audio_files.sort()

    results = {}
    for audio_file in audio_files:
        try:
            metadata = extract_metadata_from_file(str(audio_file))
            results[str(audio_file)] = metadata
        except Exception as e:
            results[str(audio_file)] = {"error": str(e)}

    return {
        "folder_type": folder_type,
        "folder": str(folder_path),
        "files": results
    }


def copy_folder(source_path, max_attempts=5):
    """
    Copy a folder to a temporary location with retry logic.

    Args:
        source_path: Path to the folder to copy
        max_attempts: Maximum number of copy attempts (default: 5)

    Returns:
        Path to the temporary folder on success, None on failure after all attempts
    """
    source_path = source_path

    # Validate source path
    if not os.path.exists(source_path) or not os.path.isdir(source_path):
        return None

    for attempt in range(max_attempts):
        try:
            # Create a temporary directory
            temp_dir = tempfile.mkdtemp(prefix="audiobook_copy_")
            temp_path = temp_dir

            # Copy the entire folder
            shutil.copytree(source_path, os.path.join(temp_path, os.path.basename(source_path)), dirs_exist_ok=True)

            # Return the path to the copied folder
            return str(os.path.join(temp_path, os.path.basename(source_path)))

        except Exception as e:
            # Clean up failed temp directory if it was created
            try:
                if 'temp_path' in locals():
                    shutil.rmtree(temp_path, ignore_errors=True)
            except:
                pass

            # If this was the last attempt, return None
            if attempt == max_attempts - 1:
                return None

            # Otherwise continue to next attempt
            continue

    # This should never be reached, but just in case
    return None


def apply_metadata_to_file(file_path, metadata_dict):
    """
    Apply metadata changes to an audio file using the combined-metadata-mapping.json.

    Args:
        file_path: Path to the audio file
        metadata_dict: Dict with descriptive keys and values to apply
    """
    # Find the mapping file relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    
    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = MutagenFile(file_path)
    if audio is None:
        raise ValueError("Could not load audio file: {}".format(file_path))

    # Check if this is an MP3 file
    is_mp3 = isinstance(audio, MP3)
    
    # Combine all metadata sections from the new mapping structure
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    # Apply each metadata field
    for desc_key, value in metadata_dict.items():
        if desc_key not in all_fields:
            continue

        info = all_fields[desc_key]
        mutagen_keys = info.get('mutagen_keys', {})
        
        # Skip if value is None or empty (except for picture which we preserve)
        if value is None or (isinstance(value, str) and not value.strip()):
            if desc_key != 'picture':  # Always preserve picture
                continue

        # Get appropriate tags based on file format
        tags_to_try = []
        if is_mp3 and 'id3' in mutagen_keys:
            tags_to_try.append(mutagen_keys['id3'])
        elif not is_mp3 and 'mp4' in mutagen_keys:
            tags_to_try.append(mutagen_keys['mp4'])
        
        # Apply to each tag
        for tag in tags_to_try:
            try:
                if is_mp3 and hasattr(audio, 'tags') and audio.tags is not None:
                    # MP3 files need proper ID3 frames
                    if tag == 'TIT2':
                        audio.tags.add(TIT2(encoding=3, text=value))
                    elif tag == 'TPE1':
                        audio.tags.add(TPE1(encoding=3, text=value))
                    elif tag == 'TALB':
                        audio.tags.add(TALB(encoding=3, text=value))
                    elif tag == 'TCON':
                        audio.tags.add(TCON(encoding=3, text=value))
                    elif tag == 'TPE2':
                        audio.tags.add(TPE2(encoding=3, text=value))
                    elif tag == 'TCOM':
                        audio.tags.add(TCOM(encoding=3, text=value))
                    elif tag == 'TRCK':
                        audio.tags.add(TRCK(encoding=3, text=value))
                    elif tag == 'TPOS':
                        audio.tags.add(TPOS(encoding=3, text=value))
                    elif tag == 'TSOA':
                        audio.tags.add(TSOA(encoding=3, text=value))
                    elif tag == 'TSOT':
                        audio.tags.add(TSOT(encoding=3, text=value))
                    elif tag == 'TSOP':
                        audio.tags.add(TSOP(encoding=3, text=value))
                    elif tag == 'TSO2':
                        audio.tags.add(TSO2(encoding=3, text=value))
                    elif tag == 'TMED':
                        audio.tags.add(TMED(encoding=3, text=value))
                    # Skip other tags for now
                elif hasattr(audio, 'tags') and audio.tags is not None:
                    # Handle different tag types for other formats (MP4/M4A/M4B)
                    if desc_key == 'picture':
                        # Preserve existing picture data
                        if tag in audio.tags:
                            continue  # Don't overwrite existing pictures
                    elif desc_key in ['track_number', 'disc_number', 'total_tracks', 'total_discs']:
                        # Integer fields for MP4
                        if isinstance(value, (int, str)) and str(value).isdigit():
                            audio.tags[tag] = [int(value)]
                    elif desc_key == 'media_kind':
                        # Special handling for stik field (media kind)
                        if tag == 'stik':
                            audio.tags[tag] = [int(value) if str(value).isdigit() else 2]  # Default to audiobook
                    elif desc_key == 'gapless_playback':
                        # Special handling for pgap field (gapless playback)
                        if tag == 'pgap':
                            audio.tags[tag] = [True if value else False]
                    else:
                        # String fields for MP4
                        audio.tags[tag] = [str(value)]
                elif hasattr(audio, tag):
                    # Direct attribute (for some formats)
                    if desc_key in ['track_number', 'disc_number', 'total_tracks', 'total_discs', 'media_kind']:
                        if isinstance(value, (int, str)) and str(value).isdigit():
                            setattr(audio, tag, int(value))
                    else:
                        setattr(audio, tag, str(value))
            except Exception:
                # Skip tags that can't be set
                continue

    # Save the changes
    audio.save()


def mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None):
    """
    Mutate metadata for all files in a folder based on folder type.

    Args:
        metadata_dict: Dict with:
            - folder_type: "novel" or "series"
            - folder: path to source folder
            - files: dict of {file_path: metadata_dict}
        album_sort_prefix: Optional string to prefix album_sort with " : " separator
        album_suffix: Optional string to suffix album with " - " separator

    Returns:
        Path to the mutated temporary folder
    """
    folder_type = metadata_dict.get('folder_type')
    source_folder = metadata_dict.get('folder')
    files_dict = metadata_dict.get('files', {})

    if not source_folder or not files_dict:
        raise ValueError("Invalid metadata_dict: missing folder or files")

    # Copy folder to temp location
    temp_folder = copy_folder(source_folder)
    if not temp_folder:
        raise ValueError("Failed to copy folder: {}".format(source_folder))

    temp_path = temp_folder

    # Get folder names for processing
    source_path = source_folder
    folder_name = os.path.basename(source_path)
    cleaned_folder_name = book_title_logic(folder_name)

    # For series, get parent folder name
    parent_name = ""
    cleaned_parent_name = ""
    if folder_type == "series":
        parent_name = os.path.basename(os.path.dirname(source_path))
        cleaned_parent_name = book_title_logic(parent_name)

    # Process each file
    sorted_files = sorted(files_dict.keys())
    for index, source_file_path in enumerate(sorted_files, 1):
        metadata = files_dict[source_file_path]

        # Get corresponding temp file path
        source_file = source_file_path
        temp_file = os.path.join(temp_path, os.path.basename(source_file))

        if not os.path.exists(temp_file):
            continue  # Skip if temp file doesn't exist

        # Create updated metadata dict
        updated_metadata = metadata.copy()

        # Clean existing text metadata values
        for key, value in updated_metadata.items():
            if isinstance(value, str) and key not in ['picture', 'sort_title', 'chapter_sort']:  # Don't clean picture, sort_title, or chapter_sort
                updated_metadata[key] = book_title_logic(value)

        # Apply folder-type specific logic
        if folder_type == "series":
            # Add cleaned folder name to album
            updated_metadata['album'] = cleaned_folder_name
            # Add cleaned parent folder name to front of album_sort
            updated_metadata['album_sort'] = "{} - {}".format(cleaned_parent_name, cleaned_folder_name)
        elif folder_type == "novel":
            # Add cleaned folder name to album and album_sort
            updated_metadata['album'] = cleaned_folder_name
            updated_metadata['album_sort'] = cleaned_folder_name

        # Apply album_sort prefix if provided
        if album_sort_prefix:
            current_album_sort = updated_metadata.get('album_sort', '')
            updated_metadata['album_sort'] = "{} : {}".format(album_sort_prefix, current_album_sort)

        # Apply album suffix if provided
        if album_suffix:
            current_album = updated_metadata.get('album', '')
            updated_metadata['album'] = "{} - {}".format(current_album, album_suffix)

        # Set title to cleaned file name (without extension)
        file_stem = os.path.splitext(os.path.basename(source_file))[0]
        cleaned_title = book_title_logic(file_stem)
        updated_metadata['title'] = cleaned_title

        # Set sort_title to uncleaned title
        updated_metadata['sort_title'] = file_stem

        # Set track number
        updated_metadata['track'] = str(index)

        # Set media_kind and genre to "Audiobook"
        updated_metadata['media_kind'] = "Audiobook"
        updated_metadata['genre'] = "Audiobook"

        # Apply changes to the temp file
        try:
            apply_metadata_to_file(str(temp_file), updated_metadata)
        except Exception as e:
            print("Warning: Failed to update metadata for {}: {}".format(temp_file, e))

    # Clean up the folder name in temp directory
    cleaned_temp_folder_name = book_title_logic(os.path.basename(temp_path))
    new_temp_path = os.path.dirname(temp_path) / cleaned_temp_folder_name

    # Rename the folder if name changed
    if cleaned_temp_folder_name != os.path.basename(temp_path):
        temp_path.rename(new_temp_path)
        temp_folder = str(new_temp_path)

    return temp_folder


def convert_folder_to_m4b(folder_path, output_path, config=None):
    """
    Convert a folder of audio files (os.path.join(MP3, M4A)) to a single M4B file with chapters.

    Args:
        folder_path: Path to folder containing audio files
        output_path: Path for the output M4B file
        config: Optional configuration object for settings

    Returns:
        Path to the created M4B file
    """
    folder_path = folder_path
    output_path = output_path

    if not os.path.isdir(folder_path):
        raise ValueError("Path is not a directory: {}".format(folder_path))

    # Find all audio files in the folder
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))

    if not audio_files:
        raise ValueError("No audio files found in: {}".format(folder_path))

    # Sort files alphabetically (assuming they represent chapter order)
    audio_files.sort()

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Create chapter metadata file for ffmpeg
    import tempfile
    
    # Create a temporary file list for ffmpeg concatenation
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=folder_path) as f:
        file_list_path = f.name
        for audio_file in audio_files:
            # Escape single quotes properly for ffmpeg concat
            escaped_path = str(audio_file).replace("'", "'\\''")
            f.write("file '{}'\n".format(escaped_path))

    # Create chapter metadata file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=folder_path) as f:
        metadata_path = f.name
        f.write(";FFMETADATA1\n")
        
        # Calculate chapter timestamps and write metadata
        current_time = 0
        for i, audio_file in enumerate(audio_files):
            # Get duration from source file
            source_audio = MutagenFile(audio_file)
            if source_audio and hasattr(source_audio, 'info') and hasattr(source_audio.info, 'length'):
                duration_ms = int(source_audio.info.length * 1000)  # Convert to milliseconds
            else:
                # Fallback: estimate 10 minutes per chapter if duration can't be read
                duration_ms = 600000  # 10 minutes in milliseconds

            # Get chapter title from source file metadata or use filename
            chapter_title = "Chapter {}".format(i+1)
            try:
                source_metadata = extract_metadata_from_file(audio_file)
                if source_metadata.get('title'):
                    chapter_title = source_metadata['title']
                else:
                    # Use filename without extension as fallback
                    file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                    chapter_title = file_stem
            except:
                # Use filename without extension as final fallback
                file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                chapter_title = file_stem

            # Write chapter info to metadata file
            f.write("\n[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write("START={}\n".format(current_time))
            f.write("END={}\n".format(current_time + duration_ms))
            f.write("title={}\n".format(chapter_title))
            
            current_time += duration_ms

    try:
        # Use ffmpeg with concat input and chapter metadata
        import subprocess

        # Get audio quality from config if available
        audio_quality = '128k'  # Default
        try:
            if config:
                audio_quality = config.get('processing.ffmpeg_quality', '128k')
        except:
            pass

        # Build the ffmpeg command with chapter metadata
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', file_list_path,
            '-i', metadata_path,
            '-map_metadata', '1',  # Use metadata from second input (metadata file)
            '-vn',  # Skip video streams (album art)
            '-c:a', 'aac',
            '-b:a', audio_quality,
            '-f', 'mp4',
            '-movflags', '+faststart',
            '-y',  # Overwrite output
            str(output_path)
        ]

        # Run the command
        result = subprocess.call(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result != 0:
            # Get the error output by running again with visible output
            try:
                error_output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                raise Exception("ffmpeg failed: {}".format(error_output))
            except subprocess.CalledProcessError as e:
                raise Exception("ffmpeg failed with exit code {}: {}".format(e.returncode, e.output))

        # Verify the output file was created and has content
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Output file was not created or is empty")

        # Add additional metadata to the M4B file (audiobook-specific tags)
        add_audiobook_metadata(str(output_path), audio_files)

        return str(output_path)

    finally:
        # Clean up temporary files
        try:
            os.remove(file_list_path)
        except:
            pass
        try:
            os.remove(metadata_path)
        except:
            pass


def add_audiobook_metadata(m4b_path, source_files):
    """
    Add audiobook-specific metadata to an M4B file based on source file metadata.
    This complements the chapter information already added by ffmpeg.

    Args:
        m4b_path: Path to the M4B file
        source_files: List of source audio file paths
    """
    try:
        from mutagen.mp4 import MP4, MP4Tags
    except ImportError:
        print("Warning: mutagen MP4 support not available, skipping metadata addition")
        return

    # Load the M4B file
    audio = MP4(m4b_path)
    if audio.tags is None:
        audio.tags = MP4Tags()

    # Copy metadata and images from the first file that has them
    if source_files:
        try:
            # Try to find a source file with picture data
            source_with_picture = None
            for source_file in source_files:
                try:
                    # Check for picture data directly
                    test_audio = MutagenFile(source_file)
                    if test_audio and hasattr(test_audio, 'tags') and test_audio.tags:
                        # Check for any tag containing 'APIC' or 'PIC'
                        has_picture = False
                        for tag_name in test_audio.tags:
                            if 'APIC' in tag_name or 'PIC' in tag_name:
                                has_picture = True
                                break
                        if has_picture:
                            source_with_picture = source_file
                            break
                except Exception as e:
                    print("Error checking {}: {}".format(source_file, e))
                    continue

            # Use the first file for basic metadata
            first_file = source_files[0]
            first_audio = MutagenFile(first_file)
            if first_audio and hasattr(first_audio, 'tags') and first_audio.tags:
                # Copy text metadata directly from MP3 tags
                if 'TALB' in first_audio.tags:
                    album_value = str(first_audio.tags['TALB'])
                    # Use album as the main title for the audiobook
                    audio.tags['\xa9nam'] = [album_value]
                    audio.tags['\xa9alb'] = [album_value]
                if 'TPE1' in first_audio.tags:
                    artist_value = str(first_audio.tags['TPE1'])
                    audio.tags['\xa9ART'] = [artist_value]
                    # Set album artist to same as artist for consistency
                    audio.tags['aART'] = [artist_value]
                if 'TCON' in first_audio.tags:
                    genre_value = str(first_audio.tags['TCON'])
                    audio.tags['\xa9gen'] = [genre_value]
                
                # Set critical audiobook-specific metadata
                audio.tags['stik'] = [2]  # Media Kind: 2 = Audiobook (critical for iTunes recognition)
                audio.tags['pgap'] = [1]  # Gapless playback for seamless listening
                audio.tags['\xa9too'] = ['audiobook-p']  # Encoding tool identification
                
                # Optional: Set content rating to clean by default
                audio.tags['rtng'] = [0]  # 0 = No rating, 2 = Clean, 4 = Explicit
                
            else:
                print("Warning: First file has no tags or could not be loaded")

            # Copy picture data if available
            if source_with_picture:
                source_audio = MutagenFile(source_with_picture)
                if source_audio and hasattr(source_audio, 'tags') and source_audio.tags:
                    # Look for picture data in the source file
                    for tag_name in source_audio.tags:
                        if 'APIC' in tag_name or 'PIC' in tag_name:
                            picture_data = source_audio.tags[tag_name]
                            # Convert to MP4 format - MP4 uses 'covr' tag
                            if isinstance(picture_data, list) and len(picture_data) > 0:
                                pic = picture_data[0]
                                # Extract the image data
                                if hasattr(pic, 'data'):
                                    # Store as MP4 cover art
                                    audio.tags['covr'] = [pic.data]
                                    break
                            elif hasattr(picture_data, 'data'):
                                # Single picture object
                                audio.tags['covr'] = [picture_data.data]
                                break

        except Exception as e:
            print("Warning: Failed to copy metadata to M4B: {}".format(e))
            pass  # Skip metadata if extraction fails

        audio.save()


def move_to_destination(source_path, destination_path, folder_type):
    """
    Move a folder to the destination, creating subdirectories as needed.
    
    Args:
        source_path: Path to the source folder
        destination_path: Path to the destination directory
        folder_type: "novel" or "series" (affects folder structure)
    
    Returns:
        Path to the final destination
    """
    source_path = source_path
    destination_path = destination_path
    
    # Ensure destination directory exists
    if not os.path.exists(destination_path):
        os.makedirs(destination_path)
    
    # For series, create a subdirectory based on the folder name
    if folder_type == "series":
        # Get the parent folder name for series organization
        parent_name = os.path.basename(os.path.dirname(source_path))
        series_dest = os.path.join(destination_path, parent_name)
        if not os.path.exists(series_dest):
            os.makedirs(series_dest)
        destination_path = series_dest
    
    # Move the folder
    folder_name = os.path.basename(source_path)
    final_dest = os.path.join(destination_path, folder_name)
    
    # If destination already exists, remove it first
    if os.path.exists(final_dest):
        shutil.rmtree(final_dest)
    
    shutil.move(source_path, final_dest)
    
    return final_dest


def cmd_convert(args):
    """Convert a folder of audio files to a single M4B file with chapters"""
    import os  # Ensure os is available for this function
    
    # Import our new enhancement modules
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.validation import check_dependencies, validate_folder_structure, validate_output_path, estimate_processing_time
            from audiobook_p.progress_simple import Logger, safe_operation, ask_user_confirmation, display_operation_summary, show_processing_estimate
            from audiobook_p.config import get_config
        except ImportError:
            # Fallback for when running as script
            import sys
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from validation import check_dependencies, validate_folder_structure, validate_output_path, estimate_processing_time
            from progress_simple import Logger, safe_operation, ask_user_confirmation, display_operation_summary, show_processing_estimate
            from config import get_config
        
        logger = Logger()
        config = get_config()
        
    except ImportError:
        # Fallback to basic operation if enhancement modules not available
        logger = None
        config = None
    
    source_path = args.source
    output_path = args.output

    try:
        # Enhanced validation if available
        if logger:
            logger.info("Validating input and dependencies...")
        
        # Check dependencies first
        try:
            if config:
                check_dependencies()
            if logger:
                logger.info("Dependencies check passed")
        except Exception as e:
            if logger:
                logger.error("Dependency check failed: {}".format(e))
            else:
                print("Warning: {}".format(e))
        
        # Validate source path
        if not os.path.isdir(source_path):
            error_msg = "Error: Source must be a directory: {}".format(source_path)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return
        
        # Enhanced folder validation if available
        try:
            if config:
                audio_files = validate_folder_structure(source_path)
                if logger:
                    logger.info("Found {} valid audio files".format(len(audio_files)))
            else:
                # Basic validation fallback
                audio_extensions = ['*.m4a', '*.mp3']
                audio_files = []
                for ext in audio_extensions:
                    audio_files.extend(list(glob.glob(os.path.join(source_path, ext))))
                audio_files.sort()
                
                if not audio_files:
                    raise ValueError("No audio files found")
                    
        except Exception as e:
            error_msg = "Source validation failed: {}".format(e)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return

        # If output_path is a directory, generate filename from source folder name
        if os.path.isdir(output_path):
            source_folder_name = os.path.basename(source_path.rstrip('/\\'))
            output_filename = "{}.m4b".format(source_folder_name)
            final_output_path = os.path.join(output_path, output_filename)
        else:
            final_output_path = output_path

        # Enhanced output validation if available
        try:
            if config:
                final_output_path = validate_output_path(final_output_path)
        except Exception as e:
            error_msg = "Output validation failed: {}".format(e)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return

        # Show processing estimate if available
        if config and logger:
            try:
                estimate = estimate_processing_time(audio_files)
                show_processing_estimate(estimate['file_count'], estimate['total_size_mb'])
                
                # Ask for confirmation for large operations
                if estimate['estimated_minutes'] > 5:
                    confirmation_msg = "This operation may take {:.1f} minutes. Continue?".format(estimate['estimated_minutes'])
                    if not ask_user_confirmation(confirmation_msg, True):
                        logger.info("Operation cancelled by user")
                        return
                        
            except Exception:
                pass  # Continue without estimate if it fails

        # Convert to M4B with enhanced progress tracking
        def convert_operation():
            return convert_folder_to_m4b(str(source_path), str(final_output_path), config)
        
        if logger:
            m4b_path = safe_operation("M4B Conversion", convert_operation)
            if m4b_path is None:
                return  # Operation failed
        else:
            m4b_path = convert_folder_to_m4b(str(source_path), str(final_output_path), config)

        # Display results
        result = {
            "operation": "convert",
            "source_folder": str(source_path),
            "output_file": m4b_path,
            "format": "M4B"
        }
        
        # Enhanced summary if available
        if logger and os.path.exists(m4b_path):
            try:
                output_size = os.path.getsize(m4b_path)
                stats = {
                    'source_files': len(audio_files),
                    'output_file': os.path.basename(m4b_path),
                    'output_size': output_size,
                    'compression_ratio': "{}:1 files".format(len(audio_files))
                }
                display_operation_summary("M4B Conversion", stats)
            except Exception:
                pass
        
        print(json.dumps(result, indent=2))

    except Exception as e:
        error_msg = "Error: {}".format(e)
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)


def cmd_extract(args):
    """Extract metadata from audio files"""
    source_path = args.source

    try:
        if os.path.isfile(source_path):
            # Process single file
            if os.path.splitext(source_path)[1].lower() not in ['.m4a', '.mp3']:
                print("File is not an audio file: {}".format(source_path))
                return

            metadata = extract_metadata_from_file(str(source_path))
            # Convert all values to strings to ensure JSON serializability
            serializable_metadata = {}
            for key, value in metadata.items():
                try:
                    # Try to encode as UTF-8 string
                    if hasattr(value, 'encode'):
                        serializable_metadata[key] = value.encode('utf-8')
                    else:
                        serializable_metadata[key] = str(value)
                except:
                    # Fallback to string representation
                    serializable_metadata[key] = repr(value)
            result = {
                "file": str(source_path),
                "metadata": serializable_metadata
            }
            print(json.dumps(result, indent=2))

        elif os.path.isdir(source_path):
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(glob.glob(os.path.join(source_path, ext))):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(os.path.isdir(os.path.join(source_path, child)) for child in os.listdir(source_path) if os.path.isdir(os.path.join(source_path, child)))

            if has_individual_files and not has_subfolders:
                # Simple novel folder
                results = extract_metadata_from_folder(str(source_path), "novel")
                print(json.dumps(results, indent=2))
            elif has_subfolders:
                # Could be series or batch - use batch_verify to analyze
                if batch_verify:
                    try:
                        batch_result = batch_verify(str(source_path))
                        if batch_result and isinstance(batch_result, list):
                            # Extract each folder individually
                            all_results = []
                            for item in batch_result:
                                folder_type = item.get('folder_type')
                                folder_path = item.get('folder')
                                if folder_type and folder_path:
                                    try:
                                        folder_result = extract_metadata_from_folder(folder_path, folder_type)
                                        all_results.append(folder_result)
                                    except Exception as e:
                                        all_results.append({
                                            "folder_type": folder_type,
                                            "folder": folder_path,
                                            "error": str(e)
                                        })

                            print(json.dumps(all_results, indent=2))
                            return
                    except Exception as e:
                        pass

                # Fallback: try series_verify
                if series_verify:
                    try:
                        series_result = series_verify(str(source_path))
                        if series_result and isinstance(series_result, list) and len(series_result) > 0:
                            # Extract series folders
                            all_results = []
                            for item in series_result:
                                if item.get('type') == 'series' and item.get('paths'):
                                    for path in item['paths']:
                                        try:
                                            folder_result = extract_metadata_from_folder(path, "series")
                                            all_results.append(folder_result)
                                        except Exception as e:
                                            all_results.append({
                                                "folder_type": "series",
                                                "folder": path,
                                                "error": str(e)
                                            })
                            if all_results:
                                print(json.dumps(all_results, indent=2))
                                return
                    except Exception:
                        pass

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        print("Error: {}".format(e))


def cmd_mutate(args):
    """Mutate metadata and move files"""
    source_path = args.source
    destination_path = args.destination

    try:
        if os.path.isfile(source_path):
            print("Mutate operation requires a folder. Use extract for single files.")
            return

        elif os.path.isdir(source_path):
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(glob.glob(os.path.join(source_path, ext))):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(os.path.isdir(os.path.join(source_path, child)) for child in os.listdir(source_path) if os.path.isdir(os.path.join(source_path, child)))

            if has_individual_files and not has_subfolders:
                # Simple novel folder
                # Extract metadata first, then mutate
                metadata_dict = extract_metadata_from_folder(str(source_path), "novel")
                mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix)
                final_path = move_to_destination(mutated_path, str(destination_path), "novel")
                result = {
                    "operation": "mutate",
                    "original_folder": str(source_path),
                    "mutated_folder": mutated_path,
                    "final_destination": final_path,
                    "folder_type": "novel"
                }
                print(json.dumps(result, indent=2))
            elif has_subfolders:
                # Could be series or batch - use batch_verify to analyze
                if batch_verify:
                    try:
                        batch_result = batch_verify(str(source_path))
                        if batch_result and isinstance(batch_result, list):
                            # Mutate each folder individually
                            mutated_results = []
                            for item in batch_result:
                                folder_type = item.get('folder_type')
                                folder_path = item.get('folder')
                                if folder_type and folder_path:
                                    try:
                                        # Extract metadata first
                                        metadata_dict = extract_metadata_from_folder(folder_path, folder_type)
                                        # Then mutate
                                        mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix)
                                        # Move to destination
                                        final_path = move_to_destination(mutated_path, str(destination_path), folder_type)
                                        mutated_results.append({
                                            "folder_type": folder_type,
                                            "original_folder": folder_path,
                                            "mutated_folder": mutated_path,
                                            "final_destination": final_path
                                        })
                                    except Exception as e:
                                        mutated_results.append({
                                            "folder_type": folder_type,
                                            "folder": folder_path,
                                            "error": str(e)
                                        })

                            result = {
                                "operation": "mutate_batch",
                                "results": mutated_results
                            }
                            print(json.dumps(result, indent=2))
                            return
                    except Exception as e:
                        pass

                # Fallback: try series_verify
                if series_verify:
                    try:
                        series_result = series_verify(str(source_path))
                        if series_result and isinstance(series_result, list) and len(series_result) > 0:
                            # Mutate series folders
                            mutated_results = []
                            for item in series_result:
                                if item.get('type') == 'series' and item.get('paths'):
                                    for path in item['paths']:
                                        try:
                                            metadata_dict = extract_metadata_from_folder(path, "series")
                                            mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix)
                                            final_path = move_to_destination(mutated_path, str(destination_path), "series")
                                            mutated_results.append({
                                                "folder_type": "series",
                                                "original_folder": path,
                                                "mutated_folder": mutated_path,
                                                "final_destination": final_path
                                            })
                                        except Exception as e:
                                            mutated_results.append({
                                                "folder_type": "series",
                                                "folder": path,
                                                "error": str(e)
                                            })
                            if mutated_results:
                                result = {
                                    "operation": "mutate_series",
                                    "results": mutated_results
                                }
                                print(json.dumps(result, indent=2))
                                return
                    except Exception:
                        pass

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        print("Error: {}".format(e))


def cmd_config(args):
    """Manage configuration settings"""
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.config import get_config, create_default_config_file
        except ImportError:
            # Fallback for when running as script
            import sys
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from config import get_config, create_default_config_file
        
        config = get_config()
        
        if args.show:
            config.show_config()
        elif args.reset:
            config.reset_to_defaults()
            config.save()
            print("Configuration reset to defaults and saved.")
        elif args.create_default:
            create_default_config_file(args.create_default if args.create_default != True else None)
        elif args.set:
            try:
                key, value = args.set.split('=', 1)
                # Try to parse value as JSON for proper type handling
                try:
                    import json
                    parsed_value = json.loads(value)
                except ValueError:  # json.JSONDecodeError doesn't exist in Python 2.7
                    # If not valid JSON, treat as string
                    parsed_value = value
                
                config.set(key, parsed_value)
                config.save()
                print("Set {} = {}".format(key, parsed_value))
            except ValueError:
                print("Error: --set requires format key=value")
        elif args.get:
            value = config.get(args.get)
            print("{} = {}".format(args.get, value))
        else:
            print("Configuration file location: {}".format(config.config_path or "Not found"))
            print("Use --help for configuration options")
            
    except ImportError:
        print("Configuration management not available")


def cmd_info(args):
    print('audiobook-p v1.0.0')
    
    # Show additional info if available
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.config import get_config
        except ImportError:
            import sys
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from config import get_config
        config = get_config()
        print('Configuration: {}'.format(config.config_path or "Using defaults"))
    except ImportError:
        pass

def cli(argv=None):
    parser = argparse.ArgumentParser(prog='audiobook-p', description='Audiobook processing utility')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show package info')
    info_parser.set_defaults(func=cmd_info)

    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract metadata from audio files')
    extract_parser.add_argument('source', help='Path to audio file or folder')
    extract_parser.set_defaults(func=cmd_extract)

    # Mutate command
    mutate_parser = subparsers.add_parser('mutate', help='Mutate metadata and move files')
    mutate_parser.add_argument('source', help='Path to audio folder')
    mutate_parser.add_argument('destination', help='Destination path for mutated files')
    mutate_parser.add_argument('--album-sort-prefix', help='String to prefix album_sort with " : " separator')
    mutate_parser.add_argument('--album-suffix', help='String to suffix album with " - " separator')
    mutate_parser.set_defaults(func=cmd_mutate)

    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert folder of audio files to M4B with chapters')
    convert_parser.add_argument('source', help='Path to folder containing audio files')
    convert_parser.add_argument('output', help='Output directory or M4B file path')
    convert_parser.set_defaults(func=cmd_convert)

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration settings')
    config_group = config_parser.add_mutually_exclusive_group()
    config_group.add_argument('--show', action='store_true', help='Show current configuration')
    config_group.add_argument('--reset', action='store_true', help='Reset to default configuration')
    config_group.add_argument('--create-default', nargs='?', const=True, help='Create default config file (optionally specify path)')
    config_group.add_argument('--set', help='Set configuration value (format: key=value)')
    config_group.add_argument('--get', help='Get configuration value')
    config_parser.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    cli()
