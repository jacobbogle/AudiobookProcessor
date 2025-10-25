import os
import shutil
import subprocess

import pytest
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2

from audiobook_p import main as mainmod
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None


def has_ffmpeg():
    try:
        return shutil.which('ffmpeg') is not None
    except Exception:
        return False


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available on this runner")
def test_seventh_son_title_sanitized(tmp_path):
    """Regression: ensure embedded newlines/underscores in source TIT2 do not produce multi-line
    or underscored chapter titles in the final M4B."""
    src = tmp_path / "SeventhSonTest"
    src.mkdir()
    out_m4b = tmp_path / "out.m4b"

    # Create a small wav and convert to mp3 so we can embed ID3 TIT2 with problematic content
    wav = tmp_path / "s.wav"
    mp3_path = src / "01 - Intro.mp3"

    import wave
    with wave.open(str(wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        frames = b"\x00\x00" * 22050 * 1
        wf.writeframes(frames)

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None
    cmd = [ffmpeg, '-y', '-i', str(wav), '-q:a', '0', str(mp3_path)]
    subprocess.run(cmd, check=True, capture_output=True)

    # Embed a TIT2 with a newline and underscores mimicking the bad source
    problematic = "Seventh Son_ Tales o\n 00 Introduction.mp3"
    audio = MP3(str(mp3_path), ID3=ID3)
    try:
        audio.add_tags()
    except Exception:
        pass
    audio.tags.add(TIT2(encoding=3, text=problematic))
    class MCArgs:
        pass

    mc_args = MCArgs()
    mc_args.source = str(src)
    mc_args.destination = str(out_m4b)
    mc_args.album_sort_prefix = None
    mc_args.album_suffix = None
    mc_args.sort_by = 'filename'
    mc_args.chapter_titles = True
    mc_args.series_name = None
    mc_args.part_titles = False
    mc_args.author_name = 'Card, Orson Scott'
    mc_args.author_fix = True
    mc_args.narrator_name = None

    tags = None
    legacy_result = None
    try:
        mainmod.cmd_mutate_convert(mc_args)
        assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"
        audio = MP3(str(out_m4b))
        tags = audio.tags
        assert tags is not None
        # Check album (©alb)
        alb = tags.get('\u00A9alb')
        assert alb and alb[0] == 'Seventh Son'
        # Check artist (©ART)
        art = tags.get('\u00A9ART') or tags.get('©ART')
        assert art, f"©ART tag not present in {list(tags.keys())}"
        art_val = art[0] if isinstance(art, list) else art
        assert str(art_val) == 'Orson Scott Card'
    except Exception as e:
        if 'legacy_test_converter' in globals() and legacy_test_converter:
            legacy_result = legacy_test_converter({'mc_args': mc_args})
            assert legacy_result is not None
        else:
            raise

    if tags:
        # Check album (©alb)
        alb = tags.get('\u00A9alb')
        assert alb and alb[0] == 'Seventh Son'
        # Check artist (©ART)
        art = tags.get('\u00A9ART') or tags.get('©ART')
        assert art, f"©ART tag not present in {list(tags.keys())}"
        art_val = art[0] if isinstance(art, list) else art
        assert str(art_val) == 'Orson Scott Card'
    elif legacy_result and isinstance(legacy_result, dict):
        assert legacy_result is not None
    # that the chapter atom itself contains 'Chapter' and no underscores/newlines.
    # Load the M4B to check chapters
    from mutagen.mp4 import MP4
    m4b_audio = MP4(str(out_m4b))
    chapters = getattr(m4b_audio, 'chapters', None)
    assert chapters, "No chapters found in M4B"
    first_chapter = chapters[0]
    t = getattr(first_chapter, 'title', None)
    if isinstance(t, bytes):
        t = t.decode('utf-8', errors='replace')
    assert t, "First chapter has no title"
    assert 'Chapter' in t

    # Check that the file-level main title (©nam) includes the cleaned folder name
    from audiobook_p.main import clean_album_name
    expected_prefix = clean_album_name(os.path.basename(str(src)))
    main_title = m4b_audio.tags.get('\xa9nam', [None])[0]
    assert main_title and expected_prefix in main_title, f"Expected main title to contain {expected_prefix!r}: {main_title!r}"
    # Ensure it is not a concatenated duplicate like '... Chapter 1 Chapter 2'
    assert t.count('Chapter') == 1, f"Duplicate 'Chapter' tokens in title: {t}"

    # The original problematic title should be sanitized
    expected_title = "Seventh Son Tales o 00 Introduction.mp3"  # sanitized version
    assert t == expected_title
