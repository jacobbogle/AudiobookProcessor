import os
import shutil
import subprocess

import pytest
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2

from audiobook_p import main as mainmod


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
    audio.save()

    # Run mutate-convert (use cmd_mutate_convert) with chapter_titles True
    out_m4b = tmp_path / 'seventh_out.m4b'

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
    mc_args.author_name = None
    mc_args.author_fix = False
    mc_args.narrator_name = None

    mainmod.cmd_mutate_convert(mc_args)

    assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"

    # Inspect with mutagen (MP4) to find chapters
    from mutagen.mp4 import MP4
    m4a = MP4(str(out_m4b))
    chapters = getattr(m4a.chapters, '_chapters', []) if m4a.chapters else []
    assert len(chapters) >= 1

    first = chapters[0]
    title = None
    try:
        title = getattr(first, 'title', None)
    except Exception:
        title = None
    if not title:
        try:
            title = first[1]
        except Exception:
            title = None

    assert title, "Chapter title missing"
    t = str(title)
    # Should not contain newline characters or raw underscores
    assert '\n' not in t and '\r' not in t
    assert '_' not in t
    # Chapter atom should be 'Chapter N' (no underscores/newlines). The
    # cleaned book/folder name will be written to the main ©nam atom; verify
    # that the chapter atom itself contains 'Chapter' and no underscores/newlines.
    assert 'Chapter' in t

    # Check that the file-level main title (©nam) includes the cleaned folder name
    from mutagen.mp4 import MP4
    m = MP4(str(out_m4b))
    main_title = None
    try:
        main_title = m.tags.get('\xa9nam', [None])[0]
    except Exception:
        main_title = None
    from audiobook_p.main import clean_album_name
    expected_prefix = clean_album_name(os.path.basename(str(src)))
    assert main_title and expected_prefix in main_title, f"Expected main title to contain {expected_prefix!r}: {main_title!r}"
    # Ensure it is not a concatenated duplicate like '... Chapter 1 Chapter 2'
    assert t.count('Chapter') == 1, f"Duplicate 'Chapter' tokens in title: {t}"
