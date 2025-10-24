import os
import shutil
import subprocess
import tempfile
import json

import pytest
from mutagen.mp4 import MP4

from audiobook_p import main as mainmod


def has_ffmpeg():
    try:
        return shutil.which('ffmpeg') is not None
    except Exception:
        return False


def has_ffprobe():
    try:
        return shutil.which('ffprobe') is not None
    except Exception:
        return False


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available on this runner")
@pytest.mark.integration
def test_author_fix_sets_mp4_atom(tmp_path):
    """End-to-end: encode a short WAV to M4B, run cmd_change with --author and --author-fix,
    and assert the resulting M4B has the ©ART atom set to the fixed author name."""
    # Generate a short silent WAV and convert to M4B
    wav = tmp_path / "silence.wav"
    m4b = tmp_path / "book.m4b"

    import wave
    with wave.open(str(wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        frames = b"\x00\x00" * 22050 * 1
        wf.writeframes(frames)

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    cmd = [ffmpeg, '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '64k', str(m4b)]
    subprocess.run(cmd, check=True, capture_output=True)

    # Run cmd_change to set the author with --author-fix
    class Args:
        pass

    args = Args()
    args.path = str(m4b)
    args.album = None
    args.album_sort = None
    args.author = 'Card, Orson Scott'
    args.author_fix = True
    args.narrator = None
    args.series = None
    args.genre = None
    args.year = None
    args.title = None
    args.chapter_titles = None
    args.chapter_titles_file = None

    mainmod.cmd_change(args)

    # Reload and verify ©ART atom
    mp4_after = MP4(str(m4b))
    tags = mp4_after.tags or {}
    # Mutagen stores atom keys as unicode; the mapping uses '©ART'
    art = tags.get('\u00A9ART') or tags.get('\xc2\xa9ART') or tags.get('©ART')
    # Normalize to first element string
    assert art, f"©ART tag not present in {tags.keys()}"
    if isinstance(art, list):
        art_val = art[0]
    else:
        art_val = art

    assert str(art_val) == 'Orson Scott Card'


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available on this runner")
@pytest.mark.integration
def test_chapter_titles_set_main_title_atom(tmp_path):
    """End-to-end: create a small folder of files, run mutate-convert with --chapter-titles,
    and verify the resulting M4B's ©nam atom equals the cleaned first chapter title."""
    # Create a small folder with two m4a files (empty content is fine for concat)
    src = tmp_path / "My Book"
    src.mkdir()

    # Create two short m4a files by encoding silence
    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    for i in range(1, 3):
        wav = tmp_path / f"s{i}.wav"
        m4a = src / f"{i:02d} - Chapter {i}.m4a"
        # Create tiny wav
        import wave
        with wave.open(str(wav), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = b"\x00\x00" * 22050 * 1
            wf.writeframes(frames)
        cmd = [ffmpeg, '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '64k', str(m4a)]
        subprocess.run(cmd, check=True, capture_output=True)

    # Destination m4b path
    out_m4b = tmp_path / 'outbook.m4b'

    # Run mutate-convert: we can call cmd_mutate_convert with args
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

    # Run the mutate-convert pipeline
    mainmod.cmd_mutate_convert(mc_args)

    # Verify output exists
    assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"

    mp4_after = MP4(str(out_m4b))
    tags = mp4_after.tags or {}
    nam = tags.get('\u00A9nam') or tags.get('©nam')
    assert nam, f"©nam not present in tags: {list(tags.keys())}"
    if isinstance(nam, list):
        nam_val = nam[0]
    else:
        nam_val = nam

    # The cleaned first title should be derived from folder/filename logic; in our case
    # first file name is '01 - Chapter 1' so cleaned title will likely be 'My Book - Chapter 1' or 'Chapter 1'
    # We assert that the main title contains 'Chapter 1'
    assert 'Chapter 1' in str(nam_val)


@pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg not available on this runner")
@pytest.mark.integration
def test_mutate_convert_sets_author_atom(tmp_path):
    """End-to-end: create a small folder of m4a files, run mutate-convert with --author and --author-fix,
    and assert the resulting M4B has the ©ART atom set to the fixed author name."""
    # Create a small folder with two m4a files
    src = tmp_path / "My Book"
    src.mkdir()

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    for i in range(1, 3):
        wav = tmp_path / f"s{i}.wav"
        m4a = src / f"{i:02d} - Chapter {i}.m4a"
        # Create tiny wav
        import wave
        with wave.open(str(wav), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = b"\x00\x00" * 22050 * 1
            wf.writeframes(frames)
        cmd = [ffmpeg, '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '64k', str(m4a)]
        subprocess.run(cmd, check=True, capture_output=True)

    out_m4b = tmp_path / 'outbook_mutate_author.m4b'

    # Run mutate-convert with author and author_fix
    class MCArgs:
        pass

    mc_args = MCArgs()
    mc_args.source = str(src)
    mc_args.destination = str(out_m4b)
    mc_args.album_sort_prefix = None
    mc_args.album_suffix = None
    mc_args.sort_by = 'filename'
    mc_args.chapter_titles = False
    mc_args.series_name = None
    mc_args.part_titles = False
    mc_args.author_name = 'Card, Orson Scott'
    mc_args.author_fix = True
    mc_args.narrator_name = None

    mainmod.cmd_mutate_convert(mc_args)

    assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"

    mp4_after = MP4(str(out_m4b))
    tags = mp4_after.tags or {}
    art = tags.get('\u00A9ART') or tags.get('©ART')
    assert art, f"©ART tag not present in {tags.keys()}"
    art_val = art[0] if isinstance(art, list) else art
    assert str(art_val) == 'Orson Scott Card'


@pytest.mark.skipif(not (has_ffmpeg() and has_ffprobe()), reason="ffmpeg/ffprobe not available on this runner")
@pytest.mark.integration
def test_chapters_persisted_with_ffprobe(tmp_path):
    """End-to-end: create files, run mutate-convert to produce M4B with chapters, and use ffprobe to assert
    container-level chapters include both start_time and end_time."""
    src = tmp_path / "BookForChapters"
    src.mkdir()

    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    assert ffmpeg is not None and ffprobe is not None

    # Create three short files with increasing durations so chapters have non-zero spans
    durations = [1.0, 1.0, 1.0]
    for i, dur in enumerate(durations, start=1):
        wav = tmp_path / f"c{i}.wav"
        m4a = src / f"{i:02d} - Chapter {i}.m4a"
        import wave
        with wave.open(str(wav), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = b"\x00\x00" * int(22050 * dur)
            wf.writeframes(frames)
        cmd = [ffmpeg, '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '64k', str(m4a)]
        subprocess.run(cmd, check=True, capture_output=True)

    out_m4b = tmp_path / 'outbook_chapters.m4b'

    class MCArgs2:
        pass

    mc_args = MCArgs2()
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

    # Run ffprobe to extract chapters as JSON
    proc = subprocess.run([ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_chapters', str(out_m4b)],
                          check=True, capture_output=True)
    data = json.loads(proc.stdout.decode('utf-8'))
    chapters = data.get('chapters') or []
    assert len(chapters) >= 1, "Expected at least one chapter from ffprobe"

    prev_end = -1.0
    for ch in chapters:
        assert 'start_time' in ch and 'end_time' in ch, f"Chapter missing start_time/end_time: {ch}"
        start = float(ch['start_time'])
        end = float(ch['end_time'])
        assert start >= 0.0
        assert end > start
        assert start >= prev_end - 1e-6
        prev_end = end
