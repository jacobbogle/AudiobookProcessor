"""Audiobook P - Main CLI entrypoint for audiobook processing"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

# Auto-install required packages
try:
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TXXX
except ImportError:
    print("mutagen not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    from mutagen import File as MutagenFile
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TXXX

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
    script_dir = Path(__file__).parent
    mapping_path = script_dir / 'combined-metadata-mapping.json'

    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = MutagenFile(file_path)
    if audio is None:
        raise ValueError(f"Could not load audio file: {file_path}")

    extracted = {}

    for desc_key, info in mapping.items():
        tags = info['tags']
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

        # If no value found, use the default from mapping or empty
        if value is None:
            value = info.get('value', '')

        extracted[desc_key] = value

    return extracted


def extract_metadata_from_folder(folder_path, folder_type):
    """
    Extract metadata from all audio files in a folder.
    Returns a dict with folder type, folder path, and file paths as keys with their metadata as values.
    """
    folder_path = Path(folder_path)
    if not folder_path.is_dir():
        raise ValueError(f"Path is not a directory: {folder_path}")

    # Find all audio files in the folder
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(folder_path.glob(ext)))

    if not audio_files:
        raise ValueError(f"No audio files found in: {folder_path}")

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
    source_path = Path(source_path)

    # Validate source path
    if not source_path.exists() or not source_path.is_dir():
        return None

    for attempt in range(max_attempts):
        try:
            # Create a temporary directory
            temp_dir = tempfile.mkdtemp(prefix="audiobook_copy_")
            temp_path = Path(temp_dir)

            # Copy the entire folder
            shutil.copytree(source_path, temp_path / source_path.name, dirs_exist_ok=True)

            # Return the path to the copied folder
            return str(temp_path / source_path.name)

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
    script_dir = Path(__file__).parent
    mapping_path = script_dir / 'combined-metadata-mapping.json'    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = MutagenFile(file_path)
    if audio is None:
        raise ValueError(f"Could not load audio file: {file_path}")

    # Check if this is an MP3 file
    is_mp3 = isinstance(audio, MP3)

    # Apply each metadata field
    for desc_key, value in metadata_dict.items():
        if desc_key not in mapping:
            continue

        info = mapping[desc_key]
        tags = info['tags']

        # Skip if value is None or empty (except for picture which we preserve)
        if value is None or (isinstance(value, str) and not value.strip()):
            if desc_key != 'picture':  # Always preserve picture
                continue

        # Apply to each tag
        for tag in tags:
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
                    elif tag == 'TSOA':
                        audio.tags.add(TSOA(encoding=3, text=value))
                    elif tag == 'TSOT':
                        audio.tags.add(TSOT(encoding=3, text=value))
                    elif tag == 'TRCK':
                        audio.tags.add(TRCK(encoding=3, text=value))
                    elif tag == 'TMED':
                        audio.tags.add(TMED(encoding=3, text=value))
                    elif tag == 'soal':  # album_sort
                        audio.tags.add(TXXX(desc='ALBUMSORT', text=value))
                    elif tag == 'sonm':  # sort_title
                        audio.tags.add(TXXX(desc='TITLESORT', text=value))
                    # Skip other tags for now
                elif hasattr(audio, 'tags') and audio.tags is not None:
                    # Handle different tag types for other formats
                    if desc_key == 'picture':
                        # Preserve existing picture data
                        if tag in audio.tags:
                            continue  # Don't overwrite existing pictures
                    elif desc_key in ['track', 'media_kind']:
                        # Integer fields
                        if isinstance(value, (int, str)) and str(value).isdigit():
                            audio.tags[tag] = str(int(value))
                    else:
                        # String fields
                        audio.tags[tag] = str(value)
                elif hasattr(audio, tag):
                    # Direct attribute (for some formats)
                    if desc_key in ['track', 'media_kind']:
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
        raise ValueError(f"Failed to copy folder: {source_folder}")

    temp_path = Path(temp_folder)

    # Get folder names for processing
    source_path = Path(source_folder)
    folder_name = source_path.name
    cleaned_folder_name = book_title_logic(folder_name)

    # For series, get parent folder name
    parent_name = ""
    cleaned_parent_name = ""
    if folder_type == "series":
        parent_name = source_path.parent.name
        cleaned_parent_name = book_title_logic(parent_name)

    # Process each file
    sorted_files = sorted(files_dict.keys())
    for index, source_file_path in enumerate(sorted_files, 1):
        metadata = files_dict[source_file_path]

        # Get corresponding temp file path
        source_file = Path(source_file_path)
        temp_file = temp_path / source_file.name

        if not temp_file.exists():
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
            updated_metadata['album_sort'] = f"{cleaned_parent_name} - {cleaned_folder_name}"
        elif folder_type == "novel":
            # Add cleaned folder name to album and album_sort
            updated_metadata['album'] = cleaned_folder_name
            updated_metadata['album_sort'] = cleaned_folder_name

        # Apply album_sort prefix if provided
        if album_sort_prefix:
            current_album_sort = updated_metadata.get('album_sort', '')
            updated_metadata['album_sort'] = f"{album_sort_prefix} : {current_album_sort}"

        # Apply album suffix if provided
        if album_suffix:
            current_album = updated_metadata.get('album', '')
            updated_metadata['album'] = f"{current_album} - {album_suffix}"

        # Set title to cleaned file name (without extension)
        file_stem = source_file.stem
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
            print(f"Warning: Failed to update metadata for {temp_file}: {e}")

    # Clean up the folder name in temp directory
    cleaned_temp_folder_name = book_title_logic(temp_path.name)
    new_temp_path = temp_path.parent / cleaned_temp_folder_name

    # Rename the folder if name changed
    if cleaned_temp_folder_name != temp_path.name:
        temp_path.rename(new_temp_path)
        temp_folder = str(new_temp_path)

    return temp_folder


def move_to_destination(mutated_folder_path, destination_path, folder_type):
    """
    Move the mutated folder to the destination path.

    Args:
        mutated_folder_path: Path to the mutated temp folder
        destination_path: Destination directory or full path
        folder_type: "novel" or "series" for context

    Returns:
        Final destination path of the moved folder
    """
    mutated_path = Path(mutated_folder_path)
    dest_path = Path(destination_path)

    # Ensure destination directory exists
    if dest_path.suffix:  # If destination has an extension, it's a file path
        dest_dir = dest_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_dest = dest_path
    else:  # It's a directory
        dest_path.mkdir(parents=True, exist_ok=True)
        final_dest = dest_path / mutated_path.name

    # Move the folder
    try:
        if final_dest.exists():
            # If destination exists, remove it first
            import shutil
            if final_dest.is_dir():
                shutil.rmtree(final_dest)
            else:
                final_dest.unlink()

        mutated_path.rename(final_dest)
        return str(final_dest)
    except Exception as e:
        raise ValueError(f"Failed to move folder to {final_dest}: {e}")


def cmd_extract(args):
    """Extract metadata from audio files"""
    source_path = Path(args.source)

    try:
        if source_path.is_file():
            # Process single file
            if source_path.suffix.lower() not in ['.m4a', '.mp3']:
                print(f"File is not an audio file: {source_path}")
                return

            metadata = extract_metadata_from_file(str(source_path))
            result = {
                "file": str(source_path),
                "metadata": metadata
            }
            print(json.dumps(result, indent=2))

        elif source_path.is_dir():
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(source_path.glob(ext)):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(child.is_dir() for child in source_path.iterdir())

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

                raise ValueError(f"Could not process folder structure: {source_path}")
            else:
                raise ValueError(f"Folder {source_path} contains no audio files")

    except Exception as e:
        print(f"Error: {e}")


def cmd_mutate(args):
    """Mutate metadata and move files"""
    source_path = Path(args.source)
    destination_path = Path(args.destination)

    try:
        if source_path.is_file():
            print("Mutate operation requires a folder. Use extract for single files.")
            return

        elif source_path.is_dir():
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(source_path.glob(ext)):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(child.is_dir() for child in source_path.iterdir())

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

                raise ValueError(f"Could not process folder structure: {source_path}")
            else:
                raise ValueError(f"Folder {source_path} contains no audio files")

    except Exception as e:
        print(f"Error: {e}")


def cli(argv=None):
    parser = argparse.ArgumentParser(prog='audiobook-p', description='Audiobook processing utility')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show package info')
    info_parser.set_defaults(func=lambda args: print('audiobook-p v0.0.0'))

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

    args = parser.parse_args(argv)
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    cli()
