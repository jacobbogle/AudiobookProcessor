"""
Audiobook Processor - Utility Functions
"""

import os
import re
from pathlib import Path

# Auto-install required packages
try:
    from pydub import AudioSegment
except ImportError:
    print("pydub not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pydub"])
    from pydub import AudioSegment


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
    except Exception:
        pass
    return None


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