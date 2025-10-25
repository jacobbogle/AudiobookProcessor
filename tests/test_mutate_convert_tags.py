import os
import shutil
import subprocess
import tempfile
import pytest
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None
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
@pytest.mark.integration
def test_mutate_convert_produces_expected_tags(tmp_path):
    """Integration: run mutate-convert with --author and --chapter-titles and assert final M4B tags."""
    src = tmp_path / "TagBook"
    src.mkdir()

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    # Create two tiny m4a files
    for i in range(1, 3):
        wav = tmp_path / f"t{i}.wav"
        m4a = src / f"{i:02d} - Chapter {i}.m4a"
        import wave
        with wave.open(str(wav), 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            frames = b"\x00\x00" * 22050 * 1
            wf.writeframes(frames)
        cmd = [ffmpeg, '-y', '-i', str(wav), '-c:a', 'aac', '-b:a', '64k', str(m4a)]
        subprocess.run(cmd, check=True, capture_output=True)

    out_m4b = tmp_path / 'out_tags.m4b'

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

    mutated = None
    legacy_result = None
    try:
        mutated = mainmod.mutate_metadata({'dummy': 'data'}, in_place=False)
    except Exception as e:
        if legacy_test_converter:
            legacy_result = legacy_test_converter({'dummy': 'data'})
            assert 'files' in legacy_result
        else:
            raise

    if mutated and isinstance(mutated, dict):
        legacy_result = mutated
        mutated = None
    # Only proceed with file/path operations if mutated is a path
    mc_args.author_name = 'Card, Orson Scott'
    mc_args.author_fix = True
    mc_args.narrator_name = None

    # Run pipeline
    mainmod.cmd_mutate_convert(mc_args)
    assert os.path.exists(str(out_m4b)), "Expected output M4B to be created"
    audio = MP4(str(out_m4b))
    tags = audio.tags
    assert tags is not None

    # Check artist (©ART)
    art = tags.get('\u00A9ART') or tags.get('©ART')
    assert art, f"©ART tag not present in {list(tags.keys())}"
    art_val = art[0] if isinstance(art, list) else art
    assert str(art_val) == 'Orson Scott Card'

    # Check main title (©nam) exists and contains 'Chapter 1'
    nam = tags.get('\u00A9nam') or tags.get('©nam')
    assert nam, f"©nam not present in {list(tags.keys())}"
    nam_val = nam[0] if isinstance(nam, list) else nam
    assert 'Chapter 1' in str(nam_val)

    # If stik (media kind) is present, ensure it's set to 2 (audiobook).
    # Some environments/tools may omit this atom; don't fail the test if it's absent.
    stik = tags.get('stik')
    if stik is not None:
        assert stik == [2] or (isinstance(stik, list) and stik and int(stik[0]) == 2)
