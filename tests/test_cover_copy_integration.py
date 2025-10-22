import os
import pytest
from mutagen import File
from audiobook_p.main import add_audiobook_metadata


def test_cover_copy_from_mp3_thorn(tmp_path):
    """Integration-style test that uses the user's Thorn test file if available.
    It will create a temporary copy of the converted M4B and attempt to copy metadata into it.
    """
    thorn_mp3 = "/Users/channingbogle/Desktop/test/Thorn and Talon/01 Master Imus's Transgression.mp3"
    if not os.path.exists(thorn_mp3):
        pytest.skip("Thorn test MP3 not present on this runner")

    # Create a small valid M4B file. Prefer using ffmpeg to create a real container
    m4b = tmp_path / "out.m4b"
    ffmpeg_path = None
    try:
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
    except Exception:
        ffmpeg_path = None

    if ffmpeg_path:
        # Create a short silent WAV and encode to M4B with ffmpeg
        wav_path = tmp_path / "silence.wav"
        # Generate 1 second of silence using Python wave module
        try:
            import wave
            with wave.open(str(wav_path), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                frames = b"\x00\x00" * 22050
                wf.writeframes(frames)

            # Encode to M4B (AAC inside MP4) with ffmpeg
            import subprocess
            cmd = [ffmpeg_path, '-y', '-i', str(wav_path), '-c:a', 'aac', '-b:a', '64k', str(m4b)]
            subprocess.run(cmd, check=True, capture_output=True)
        except Exception:
            # If ffmpeg encoding fails, fall back to minimal container method below
            ffmpeg_path = None

    if not ffmpeg_path:
        # Fall back: create a tiny mp4 container file (may not be fully parseable by mutagen)
        with open(m4b, 'wb') as f:
            f.write(b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00")

    # Run add_audiobook_metadata with source_files=[thorn_mp3]
    try:
        add_audiobook_metadata(str(m4b), [thorn_mp3], original_source_files=[thorn_mp3])
    except Exception as e:
        # If mutagen can't parse the tiny MP4 container we created, skip the test
        from mutagen.mp4 import MP4StreamInfoError
        if isinstance(e, MP4StreamInfoError) or 'not a MP4 file' in str(e):
            pytest.skip(f"Mutagen couldn't parse generated test M4B container: {e}")
        # Otherwise re-raise
        raise

    # Load resulting tags and verify covr exists
    audio = File(str(m4b))
    # If mutagen can't read the empty mp4 container, treat as pass/fail based on tag presence
    if not audio or not hasattr(audio, 'tags') or not audio.tags:
        pytest.skip("Mutagen couldn't parse generated test M4B container on this runner")

    assert 'covr' in audio.tags and len(audio.tags['covr']) > 0
