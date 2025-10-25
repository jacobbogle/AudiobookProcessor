# Minimal stub for legacy test compatibility
def cmd_change(args):
    """Apply metadata changes to a single file."""
    from audiobook_p.main import apply_metadata_to_file
    from audiobook_p.utils import book_title_logic
    
    # Extract current metadata
    meta = extract_metadata_from_file(args.path)
    
    # Apply changes from args
    if hasattr(args, 'author') and args.author:
        meta['artist'] = args.author
    if hasattr(args, 'author_name') and args.author_name:
        meta['artist'] = args.author_name
    if hasattr(args, 'author_fix') and args.author_fix and meta.get('artist'):
        # Apply author fix logic (last, first -> first last)
        author = meta['artist']
        if ',' in author:
            parts = [p.strip() for p in author.split(',') if p.strip()]
            if len(parts) >= 2:
                last = parts[0]
                first = ' '.join(parts[1:])
                meta['artist'] = f"{first} {last}".strip()
                meta['artist'] = book_title_logic(meta['artist'])
    if hasattr(args, 'narrator') and args.narrator:
        meta['composer'] = book_title_logic(args.narrator)
    if hasattr(args, 'album') and args.album:
        meta['album'] = args.album
    if hasattr(args, 'album_sort') and args.album_sort:
        meta['album_sort'] = args.album_sort
    if hasattr(args, 'series') and args.series:
        meta['grouping'] = args.series
        meta['series'] = args.series
    if hasattr(args, 'genre') and args.genre:
        meta['genre'] = args.genre
    if hasattr(args, 'year') and args.year:
        meta['date'] = str(args.year)
    if hasattr(args, 'title') and args.title:
        meta['title'] = args.title
    
    # Handle chapter_titles if provided as a list
    if hasattr(args, 'chapter_titles') and args.chapter_titles and isinstance(args.chapter_titles, list):
        # Create chapters dividing the file duration equally
        from mutagen.mp4 import MP4
        audio = MP4(args.path)
        if audio.info and audio.info.length:
            duration = audio.info.length
            num_chapters = len(args.chapter_titles)
            chapter_duration = duration / num_chapters
            chapters_info = []
            for i, title in enumerate(args.chapter_titles):
                start_time = i * chapter_duration * 1000  # in milliseconds
                chapters_info.append({
                    'start': int(start_time),
                    'title': title
                })
            from audiobook_p.mutation import add_chapters_to_m4b
            add_chapters_to_m4b(args.path, chapters_info)
    
    # Apply the metadata
    apply_metadata_to_file(args.path, meta)
# Legacy CLI-style orchestration for test compatibility
def cmd_mutate_convert(args):
    """
    Orchestrate metadata extraction, mutation, and conversion for CLI/test usage.
    Args:
        args: Namespace-like object with attributes: source, destination, folder_type, album_sort_prefix, album_suffix, sort_by, chapter_titles, series_name, part_titles, author_name, narrator_name, author_fix
    """
    meta = extract_metadata_from_folder(args.source, getattr(args, 'folder_type', 'auto'))
    mutated = mutate_metadata(
        meta,
        album_sort_prefix=getattr(args, 'album_sort_prefix', None),
        album_suffix=getattr(args, 'album_suffix', None),
        sort_by=getattr(args, 'sort_by', 'filename'),
        chapter_titles=getattr(args, 'chapter_titles', False),
        series_name=getattr(args, 'series_name', None),
        part_titles=getattr(args, 'part_titles', False),
        author_name=getattr(args, 'author_name', None),
        narrator_name=getattr(args, 'narrator_name', None),
        author_fix=getattr(args, 'author_fix', False),
        in_place=True
    )
    # Use mutated['folder'] for conversion
    return convert_folder_to_m4b(
        mutated['folder'],
        args.destination,
        sort_by=getattr(args, 'sort_by', 'filename'),
        chapter_titles=getattr(args, 'chapter_titles', False),
        series_name=getattr(args, 'series_name', None),
        author_fix=getattr(args, 'author_fix', False),
        cli_author=getattr(args, 'author_name', None),
        album_names=False
    )


# --- Re-export and stub legacy functions for test compatibility ---
from .utils import (
    sanitize_string, book_title_logic, clean_album_name, sanitize_series_name,
    natural_sort_key, track_number_sort_key, parse_series_index_from_folder_name
)
from audiobook_p.metadata_normalization import reformat_tag_for_file_type
from audiobook_p.mutation import (
    convert_folder_to_m4b, add_chapters_to_m4b, ffmpeg_inject_chapters,
    add_audiobook_metadata
)

# Patch: legacy-compatible mutate_metadata for tests
def mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=None, narrator_name=None, author_fix=False, in_place=False, apply_metadata_to_file=None):
    from audiobook_p.mutation import mutate_metadata as _mutate_metadata
    # Apply author_fix logic to author_name before passing to mutation
    if author_fix and author_name:
        author_name = _author_last_first_to_first_last(author_name)
    result = _mutate_metadata(metadata_dict, album_sort_prefix, album_suffix, sort_by, chapter_titles, series_name, part_titles, author_name, narrator_name, author_fix, in_place, apply_metadata_to_file=apply_metadata_to_file)
    # Always return the full dict for test compatibility
    return result
from audiobook_p.metadata_extraction import (
    extract_metadata_from_folder, extract_metadata_from_file, parse_metadata_to_python_safe
)

# --- Legacy function stubs/exports for tests ---
_apply_metadata_to_file_impl = None
def apply_metadata_to_file(file_path, metadata_dict):
    """Stub for legacy test compatibility. Allows monkeypatching in tests."""
    # Delegate to mutation.apply_metadata_to_file for legacy/test compatibility
    from audiobook_p.mutation import apply_metadata_to_file as _apply_metadata_to_file
    return _apply_metadata_to_file(file_path, metadata_dict)

def move_to_destination(path, dest, folder_type):
    """Stub for legacy test compatibility. Not implemented in modular refactor."""
    raise NotImplementedError("move_to_destination is not implemented in the modular refactor.")

def _author_last_first_to_first_last(name):
    """Convert 'Last, First' to 'First Last'."""
    if not name or not isinstance(name, str):
        return name
    parts = [p.strip() for p in name.split(',')]
    if len(parts) >= 2:
        last = parts[0]
        first = ' '.join(parts[1:])
        return f"{first} {last}".strip()
    return name

def _maybe_fix_author(name, flag=None):
    """Fix author name format if flag is set, matching mutation.py logic."""
    if not name:
        return name
    try:
        val = name
        if isinstance(val, list) and len(val) > 0:
            val = val[0]
        if isinstance(val, (bytes, bytearray)):
            try:
                val = val.decode('utf-8')
            except Exception:
                try:
                    val = val.decode('latin-1')
                except Exception:
                    val = str(val)
        if hasattr(val, 'text'):
            try:
                t = val.text
                if isinstance(t, list) and len(t) > 0:
                    val = t[0]
                else:
                    val = t
            except Exception:
                try:
                    val = str(val)
                except Exception:
                    pass
        if hasattr(val, 'data') and not isinstance(val, (str, bytes, bytearray)):
            try:
                val = val.data
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode('utf-8')
                    except Exception:
                        val = val.decode('latin-1', errors='ignore')
            except Exception:
                pass
        name_str = str(val).strip()
    except Exception:
        try:
            name_str = str(name).strip()
        except Exception:
            return name
    if flag:
        try:
            return _author_last_first_to_first_last(name_str)
        except Exception:
            return name_str
    return name_str

def sanitize_metadata_value(value):
    """Sanitize metadata values from various formats (stringified lists, bytes, etc.)"""
    if value is None:
        return value
    
    # Handle bytes
    if isinstance(value, bytes):
        return value
    
    # Handle lists
    if isinstance(value, list):
        if len(value) == 1:
            return value[0]
        return value
    
    # Handle string representations of lists
    if isinstance(value, str):
        import ast
        try:
            # Try to parse as a Python literal (list, etc.)
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                if len(parsed) == 1:
                    return parsed[0]
                return parsed
        except (ValueError, SyntaxError):
            pass
    
    # Handle mutagen-like objects with data attribute
    if hasattr(value, 'data'):
        return value.data
    
    # Return as-is for other types
    return value

# Export cli symbol for compatibility with tests and __init__.py
from .cli import main as cli

"""Audiobook P - Main CLI entrypoint for audiobook processing"""

if __name__ == "__main__":
    cli()
