import os
import json
import mutagen
from mutagen.mp3 import MP3

def extract_metadata_from_file(file_path):
    """
    Extract metadata from a single file using the combined-metadata-mapping.json.
    Returns a dict with descriptive keys and their values.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
    audio = mutagen.File(file_path)
    if audio is None:
        raise ValueError(f"Could not load audio file: {file_path}")
    extracted = {}
    expected_fields = [
        'title', 'sort_title', 'album', 'album_sort', 'track', 'track_number',
        'grouping', 'series', 'series_index', 'media_kind', 'genre',
        'picture', 'cover_art', 'comment', 'artist', 'album_artist', 'composer', 'publisher'
    ]
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])
    # Extraction logic unchanged...
    # ...existing code...
    # Ensure all expected fields are present and types are normalized
    for k in expected_fields:
        v = extracted.get(k, '')
        if k in ['track', 'track_number', 'series_index']:
            try:
                v = int(v) if v not in ('', None) else 0
            except Exception:
                v = 0
        elif v is None:
            v = ''
        extracted[k] = v
    return extracted
        # ...existing extraction logic, properly indented...

    # Ensure all expected fields are present and normalized
    # Use defaults or infer from filename/folder if missing
    # Ensure 'os' is not shadowed and always available
    file_stem = os.path.splitext(os.path.basename(file_path))[0]
    folder_name = os.path.basename(os.path.dirname(file_path))
    # Title: cleaned filename
    if not extracted.get('title'):
        from audiobook_p.utils import book_title_logic
        extracted['title'] = book_title_logic(file_stem)
    # sort_title: raw filename stem
    if not extracted.get('sort_title'):
        extracted['sort_title'] = file_stem
    # album: cleaned folder name
    if not extracted.get('album'):
        from audiobook_p.utils import clean_album_name
        extracted['album'] = clean_album_name(folder_name)
    # album_sort: same as album by default
    if not extracted.get('album_sort'):
        extracted['album_sort'] = extracted['album']
    # track: fallback to 1 (will be reassigned in mutation)
    if not extracted.get('track'):
        extracted['track'] = '1'
    # track_number: fallback to 1 (will be reassigned in mutation)
    if not extracted.get('track_number'):
        extracted['track_number'] = '1'
    # grouping/series: fallback to empty
    if not extracted.get('grouping'):
        extracted['grouping'] = ''
    if not extracted.get('series'):
        extracted['series'] = ''
    # series_index: try to infer from folder name
    if not extracted.get('series_index'):
        from audiobook_p.utils import parse_series_index_from_folder_name
        idx = parse_series_index_from_folder_name(folder_name)
        extracted['series_index'] = idx if idx is not None else ''
    # media_kind: always 2 (Audiobook)
    if not extracted.get('media_kind'):
        extracted['media_kind'] = 2
    # genre: always Audiobook
    if not extracted.get('genre'):
        extracted['genre'] = 'Audiobook'
    # picture/cover_art: fallback to ''
    if not extracted.get('picture'):
        extracted['picture'] = ''
    if not extracted.get('cover_art'):
        extracted['cover_art'] = ''
    # comment: fallback to ''
    if not extracted.get('comment'):
        extracted['comment'] = ''
    # artist/album_artist/composer/publisher: fallback to ''
    for k in ['artist', 'album_artist', 'composer', 'publisher']:
        if not extracted.get(k):
            extracted[k] = ''
    # Ensure all expected fields are present
    for k in expected_fields:
        if k not in extracted:
            extracted[k] = ''
    return extracted

def parse_metadata_to_python_safe(metadata_dict):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])
    result = {}
    for desc_key, value in metadata_dict.items():
        if desc_key in all_fields:
            info = all_fields[desc_key]
            mutagen_keys = info.get('mutagen_keys', {})
            mp3_key = mutagen_keys.get('id3', '')
            mp4_key = mutagen_keys.get('mp4', '')
            python_value = value
            if isinstance(value, list) and len(value) > 0:
                python_value = value[0]
            if hasattr(python_value, 'text'):
                python_value = python_value.text
            if isinstance(python_value, str):
                pass
            elif isinstance(python_value, bytes):
                try:
                    python_value = python_value.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        python_value = python_value.decode('latin-1')
                    except UnicodeDecodeError:
                        python_value = str(python_value)
            else:
                python_value = str(python_value)
            result[desc_key] = {
                'mp3': mp3_key,
                'mp4': mp4_key,
                'value': python_value
            }
    return result

def extract_metadata_from_folder(folder_path, folder_type, sort_by='filename'):
    import glob
    if not os.path.isdir(folder_path):
        raise ValueError(f"Path is not a directory: {folder_path}")
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))
    if not audio_files:
        raise ValueError(f"No audio files found in: {folder_path}")
    def natural_sort_key(filename):
        import re
        parts = re.split(r'(\d+)', filename)
        return [int(part) if part.isdigit() else part.lower() for part in parts]
    def track_number_sort_key(file_path, metadata_dict):
        track_number = metadata_dict.get('track_number')
        if track_number:
            if isinstance(track_number, tuple) and len(track_number) >= 1:
                return (0, track_number[0])
            elif isinstance(track_number, str):
                track_str = track_number.split('/')[0]
                try:
                    return (0, int(track_str))
                except ValueError:
                    pass
        filename = os.path.basename(file_path)
        return (1, natural_sort_key(filename))
    if sort_by == 'track':
        file_metadata = {}
        for audio_file in audio_files:
            try:
                metadata = extract_metadata_from_file(str(audio_file))
                file_metadata[str(audio_file)] = metadata
            except Exception as e:
                file_metadata[str(audio_file)] = {"error": str(e)}
        audio_files.sort(key=lambda f: track_number_sort_key(f, file_metadata.get(str(f), {})))
    else:
        audio_files.sort(key=natural_sort_key)
    results = {}
    for audio_file in audio_files:
        try:
            metadata = extract_metadata_from_file(str(audio_file))
            # Ensure all expected fields are present and types are normalized
            expected_fields = [
                'title', 'sort_title', 'album', 'album_sort', 'track', 'track_number',
                'grouping', 'series', 'series_index', 'media_kind', 'genre',
                'picture', 'cover_art', 'comment', 'artist', 'album_artist', 'composer', 'publisher'
            ]
            for k in expected_fields:
                v = metadata.get(k, '')
                if k in ['track', 'track_number', 'series_index']:
                    try:
                        v = int(v) if v not in ('', None) else 0
                    except Exception:
                        v = 0
                elif v is None:
                    v = ''
                metadata[k] = v
            results[str(audio_file)] = metadata
        except Exception as e:
            results[str(audio_file)] = {"error": str(e)}
    return {
        "folder_type": folder_type,
        "folder": str(folder_path),
        "files": results
    }
