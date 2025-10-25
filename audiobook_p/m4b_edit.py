"""
Module for editing M4B files after conversion.
Provides functions to update metadata, chapters, and tags in-place.
"""
import os
import mutagen
from mutagen.mp4 import MP4

def edit_m4b_metadata(m4b_path, metadata_dict):
    """
    Edit metadata tags of an M4B file in-place.
    Args:
        m4b_path: Path to the M4B file.
        metadata_dict: Dict of tags to update (e.g. title, artist, album, etc.)
    """
    audio = MP4(m4b_path)
    for key, value in metadata_dict.items():
        audio.tags[key] = value
    audio.save()
    return m4b_path


def edit_tags_and_cover(m4b_path, tags, cover_path=None):
    """
    Edit tags and optionally cover art of an M4B file in-place.
    Args:
        m4b_path: Path to the M4B file.
        tags: Dict of tags to update (e.g. title, artist, album, etc.)
        cover_path: Path to cover image file (optional)
    """
    from mutagen.mp4 import MP4, MP4Cover
    audio = MP4(m4b_path)
    for key, value in tags.items():
        audio.tags[key] = value
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, 'rb') as cf:
            cover_data = cf.read()
        fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
        audio['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
    audio.save()
    return m4b_path
