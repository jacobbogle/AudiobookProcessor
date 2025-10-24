import os
import tempfile
import subprocess

import pytest

from audiobook_p.main import ffmpeg_inject_chapters


def test_ffmpeg_inject_chapters_writes_meta_and_remux(monkeypatch, tmp_path):
    # Create a dummy m4b file
    m4b = tmp_path / 'book.m4b'
    m4b.write_bytes(b'FAKE M4B')

    # Prepare sample chapters input (list of dicts)
    chapters = [
        {'start': 0.0, 'title': 'Intro'},
        {'start': 60.0, 'title': 'Chapter 1'}
    ]

    # Monkeypatch shutil.which to report ffmpeg present
    monkeypatch.setattr('shutil.which', lambda name: '/usr/bin/ffmpeg')

    # Monkeypatch subprocess.run to simulate ffmpeg: check metadata file and touch tmp_out
    def fake_run(cmd, check=False, capture_output=False):
        # cmd example: ['/usr/bin/ffmpeg', '-y', '-i', m4b_path, '-i', meta_path, '-map_metadata', '1', '-c', 'copy', tmp_out]
        # Find meta_path from cmd
        meta_path = None
        tmp_out = None
        for i, a in enumerate(cmd):
            if a == '-i' and i+1 < len(cmd):
                # skip the first -i (input file), take the second occurrence as meta
                if meta_path is None:
                    meta_path = cmd[i+1]
                else:
                    # second -i
                    meta_path = cmd[i+1]
            if isinstance(a, str) and a.endswith('.tmp.m4b'):
                tmp_out = a

        # Validate meta file contains header
        if meta_path and os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = f.read()
                if 'FFMETADATA1' not in data:
                    raise RuntimeError('metadata missing header')

        # Touch tmp_out to simulate ffmpeg output
        if tmp_out:
            open(tmp_out, 'wb').close()

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr('subprocess.run', fake_run)

    res = ffmpeg_inject_chapters(str(m4b), chapters, timebase=1000)

    # Expect success-ish structure
    assert isinstance(res, dict)
    assert 'status' in res
    # The helper should report success (it removes the temp meta file on exit)
    assert res.get('status') in ('ok', 'no_ffmpeg', 'error')
    assert res.get('status') == 'ok'
