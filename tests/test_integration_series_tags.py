import os
import shutil
import subprocess
import tempfile

import pytest

try:
    from mutagen.mp4 import MP4
except Exception:
    MP4 = None


@pytest.mark.skipif(MP4 is None, reason="mutagen.mp4 not available")
def test_write_and_read_series_tags():
    """Create a tiny m4a, write series tags (tvsn and freeform VOLUME), and verify them."""
    # Check ffmpeg availability
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path is None:
        pytest.skip('ffmpeg not available on PATH')

    tmpdir = tempfile.mkdtemp(prefix='abp-int-test-')
    try:
        src = os.path.join(tmpdir, 'silence.wav')
        out = os.path.join(tmpdir, 'test.m4a')

        # Create 1 second of silence WAV using ffmpeg
        # Use -f lavfi to synthesize silence to avoid needing source files
        cmd = [ffmpeg_path, '-y', '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=44100', '-t', '1', src]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Convert to m4a (AAC in M4A container)
        cmd2 = [ffmpeg_path, '-y', '-i', src, '-c:a', 'aac', '-b:a', '64k', out]
        subprocess.check_call(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Open file and write tags
        audio = MP4(out)
        if audio.tags is None:
            audio.add_tags()

        # Standard grouping atom
        audio.tags['\xa9grp'] = ['Series Name']
        # Freeform iTunes series key -- store as bytes for mutagen freeform
        audio.tags['----:com.apple.iTunes:SERIES'] = [b'Series Name']
        # Numeric series index (tvsn expects an integer list)
        audio.tags['tvsn'] = [3]
        # Freeform volume key for visibility
        audio.tags['----:com.apple.iTunes:VOLUME'] = [b'3']

        audio.save()

        # Re-open and verify
        audio2 = MP4(out)
        tags = audio2.tags

        assert '\xa9grp' in tags
        assert tags['\xa9grp'][0] == 'Series Name'

        # Freeform series key should be present
        assert '----:com.apple.iTunes:SERIES' in tags
        sf_series = tags['----:com.apple.iTunes:SERIES'][0]
        # freeform data is bytes; decode for comparison
        if isinstance(sf_series, (bytes, bytearray)):
            sf_series = sf_series.decode('utf-8')
        assert sf_series == 'Series Name'

        # tvsn should be present and numeric
        assert 'tvsn' in tags
        # Mutagen stores tvsn as [(3,)] or similar tuple; check first element contains 3
        tvsn_val = tags['tvsn'][0]
        # If it's a tuple or list, check for int 3 inside
        if isinstance(tvsn_val, (list, tuple)):
            assert 3 in tvsn_val or tvsn_val[0] == 3
        else:
            # Fallback: integer or string
            assert int(tvsn_val) == 3

        # Freeform VOLUME present
        assert '----:com.apple.iTunes:VOLUME' in tags
        sf_vol = tags['----:com.apple.iTunes:VOLUME'][0]
        if isinstance(sf_vol, (bytes, bytearray)):
            sf_vol = sf_vol.decode('utf-8')
        assert str(sf_vol) == '3'

    finally:
        shutil.rmtree(tmpdir)
