import os
import shutil
import subprocess
import pytest
from mutagen.mp4 import MP4
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
def test_chapter_titles_appear_in_m4b_chapters(tmp_path):
    """End-to-end: create a small folder of m4a files, run mutate-convert with --chapter-titles,
    and verify the resulting M4B container-level chapters include a readable chapter title.
    """
    src = tmp_path / "RenderBook"
    src.mkdir()

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    # Create three short m4a files by encoding silence
    for i in range(1, 4):
        wav = tmp_path / f"r{i}.wav"
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

    out_m4b = tmp_path / 'render_out.m4b'

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
    assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"
    audio = MP4(str(out_m4b))
    chapters = audio.chapters
    assert chapters is not None, "Expected chapters to be present in the M4B"

    # Mutagen stores chapter objects in ._chapters; ensure we have at least three
    ch_list = getattr(chapters, '_chapters', [])
    assert len(ch_list) >= 3, f"Expected >=3 chapters, found {len(ch_list)}"

    # Extract readable titles for the first three chapters
    titles = []
    for idx in range(3):
        ch = ch_list[idx]
        t = None
        try:
            t = getattr(ch, 'title', None)
        except Exception:
            t = None
        if not t:
            try:
                t = ch[1]
            except Exception:
                t = None
        assert t, f"Could not determine title for chapter index {idx} (obj={repr(ch)})"
        titles.append(str(t))

    # With the new chapter_titles behavior individual chapter atoms are
    # simplified to "Chapter N" while the main title (©nam) will contain
    # the book/folder prefix (e.g. "Renderbook - Chapter 1"). Ensure each
    # chapter title includes the expected Chapter substring.
    assert titles[0].startswith("Chapter 1"), f"unexpected first chapter title: {titles[0]}"
    assert titles[1].startswith("Chapter 2"), f"unexpected second chapter title: {titles[1]}"
    assert titles[2].startswith("Chapter 3"), f"unexpected third chapter title: {titles[2]}"

    # Ensure there are no duplicate titles among the first three chapters
    assert len(set(titles)) == 3, f"Duplicate chapter titles found: {titles}"
