import os
from audiobook_p.main import (
    clean_album_name,
    extract_metadata_from_file,
    parse_metadata_to_python_safe,
    book_title_logic,
)


def get_cleaned_chapter_title_from_path(file_path, index=1):
    """
    Compute and print a cleaned chapter title for a single audio file path.

    This re-uses the same heuristics as `mutate_metadata` when `--chapter-titles`
    is requested: prefers parent folder name, album/grouping, cleaned folder
    name, filename, and falls back to "Chapter N".

    Args:
        file_path: Path to the audio file
        index: Chapter index (1-based) to include in the title

    Returns:
        The cleaned title string (also printed to stdout).
    """
    try:
        file_path = str(file_path)
    except Exception:
        raise ValueError("file_path must be a string or convertible to string")

    # Filename stem fallback
    file_stem = os.path.splitext(os.path.basename(file_path))[0]

    # Source folder (parent folder of the file)
    source_path = os.path.dirname(file_path) or os.path.basename(file_path)
    folder_name = os.path.basename(source_path)
    cleaned_folder_name = clean_album_name(folder_name) if folder_name else ''

    # Try to extract metadata from the file to prefer explicit album/grouping
    processed_metadata = {}
    try:
        src_meta = extract_metadata_from_file(file_path)
        normalized = parse_metadata_to_python_safe(src_meta)
        for desc_key, info in normalized.items():
            if isinstance(info, dict) and 'value' in info:
                processed_metadata[desc_key] = info['value']
            else:
                processed_metadata[desc_key] = info
    except Exception:
        # If metadata extraction fails, continue with best-effort fallbacks
        processed_metadata = {}

    # Parent folder (the folder that contains the file) may be meaningful
    try:
        parent_folder = os.path.basename(os.path.dirname(file_path))
    except Exception:
        parent_folder = ''
    cleaned_parent = clean_album_name(parent_folder) if parent_folder else ''

    # Choose the best book name for chapter title prefix
    book_name_for_title = (cleaned_parent or
                           processed_metadata.get('album') or
                           processed_metadata.get('grouping') or
                           cleaned_folder_name or
                           book_title_logic(os.path.basename(source_path)) or
                           file_stem)

    try:
        book_name_for_title = book_name_for_title.strip()
    except Exception:
        book_name_for_title = str(book_name_for_title).strip()

    if book_name_for_title:
        cleaned_title = f"{book_name_for_title} - Chapter {int(index)}"
    else:
        cleaned_title = f"Chapter {int(index)}"

    # Print and return for convenience
    try:
        print(cleaned_title)
    except Exception:
        # printing is best-effort; ignore failures
        pass
    return cleaned_title

get_cleaned_chapter_title_from_path('/Users/channingbogle/Desktop/Audiobooks/library/Alvin Maker Series/1 Seventh Son/Seventh Son (10).mp3', index=68)