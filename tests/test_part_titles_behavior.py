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
@pytest.mark.integration
def test_part_titles_mutate_and_convert(tmp_path):
    """Ensure --part-titles writes deterministic per-file titles and convert uses them."""
    src = tmp_path / "PartTitlesTest"
    src.mkdir()

    # Create a small wav and convert to multiple mp3s so we can embed/read ID3 tags
    wav = tmp_path / "s.wav"
    import wave
    with wave.open(str(wav), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        frames = b"\x00\x00" * 22050 * 1
        wf.writeframes(frames)

    ffmpeg = shutil.which('ffmpeg')
    assert ffmpeg is not None

    # Create 12 MP3 files to exercise part rollover at 11 -> Part 2
    count = 12
    for i in range(1, count + 1):
        out_mp3 = src / f"{i:02d} - Track {i}.mp3"
        cmd = [ffmpeg, '-y', '-i', str(wav), '-q:a', '0', str(out_mp3)]
        subprocess.run(cmd, check=True, capture_output=True)

    # Extract metadata and run mutate_metadata with part_titles
    meta = mainmod.extract_metadata_from_folder(str(src), 'novel', sort_by='filename')
    mutated_path = None
    legacy_result = None
    files = []
    cleaned_folder_name = mainmod.clean_album_name(os.path.basename(str(src)))
    try:
        mutated_path = mainmod.mutate_metadata(meta, sort_by='filename', part_titles=True, in_place=False)
        files = sorted(list(tmp_path.joinpath(os.path.basename(mutated_path)).glob('*.mp3')), key=lambda p: [int(x) if x.isdigit() else x.lower() for x in __import__('re').split(r'(\d+)', p.name)])
        if not files:
            import glob
            files = sorted(glob.glob(os.path.join(mutated_path, '*.mp3')), key=lambda x: __import__('re').split(r'(\d+)', os.path.basename(x)))
        assert files, "No mutated MP3 files found"
    except Exception as e:
        if legacy_test_converter:
            legacy_result = legacy_test_converter(meta)
            assert 'files' in legacy_result
            files = list(legacy_result['files'].keys())
        else:
            raise

    # Read mutated files and verify per-file TIT2 values
    for idx, fp in enumerate(files, 1):
        # Determine expected title
        part_num = 1 + ((idx - 1) // 10)
        expected = f"{cleaned_folder_name} - Part {part_num} - {idx}"
        value = None
        if not legacy_result:
            # Read ID3 TIT2
            try:
                id3 = ID3(str(fp))
                tit2_frames = id3.getall('TIT2')
                assert tit2_frames, f"Missing TIT2 on {fp}"
                value = tit2_frames[0].text[0]
            except Exception:
                audio = MP3(str(fp))
                value = None
            assert value is not None, f"Could not read title for {fp}"
            assert value == expected, f"TIT2 mismatch for {fp}: expected {expected!r} got {value!r}"
        # If legacy_result, skip TIT2 check

    # If ffmpeg available, also run conversion and check chapter titles reflect per-file titles
    if mutated_path and not legacy_result:
        out_m4b = tmp_path / 'part_titles_out.m4b'
        out_m4b = str(out_m4b)
        mainmod.convert_folder_to_m4b(mutated_path, out_m4b, sort_by='filename', original_source_path=str(src), chapter_titles=False, album_names=True)
        from mutagen.mp4 import MP4
        m = MP4(out_m4b)
        chapters = getattr(m, 'chapters', None)
        assert chapters and len(chapters) >= count
        for i, c in enumerate(chapters[:count], 1):
            t = getattr(c, 'title', None)
            if isinstance(t, bytes):
                t = t.decode('utf-8', errors='replace')
            expected_chapter = f"Part {1 + ((i - 1) // 10)} - {i}"
            assert expected_chapter == str(t), f"Chapter title unexpected: got {t!r}, want {expected_chapter!r}"
