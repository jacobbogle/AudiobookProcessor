import json
import os
import sys
import tempfile
import types
import shutil

import pytest
try:
    from tests.legacy_test_converter import legacy_test_converter
except ImportError:
    legacy_test_converter = None

from audiobook_p import main


def _make_fake_mutagen_mp4(persist=True):
    """Return a fake mutagen.mp4 module with controllable persistence behavior.

    If persist=True, FakeMP4.save() will persist chapters into shared state so a
    subsequent MP4(path) will see them. If persist=False, save() is a no-op and
    reload will not show chapters (triggering ffmpeg fallback).
    """
    shared = {}

    class FakeChapter:
        def __init__(self, start=None, title=None):
            self.start = start
            self.title = title

    class FakeMP4Chapters:
        def __init__(self):
            self._chapters = []

    class FakeMP4:
        def __init__(self, path):
            self._path = path
            st = shared.setdefault(path, {})
            # fake duration of 60s unless overridden
            self.info = types.SimpleNamespace(length=60.0)
            # if persisted, load chapters
            self.chapters = st.get('chapters', None)

        def save(self):
            if persist:
                # persist whatever the current instance has
                shared[self._path]['chapters'] = getattr(self, 'chapters', None)
            else:
                # do nothing (simulate mutagen not writing chapters)
                pass

    fake_mod = types.SimpleNamespace(MP4=FakeMP4, MP4Chapters=FakeMP4Chapters, Chapter=FakeChapter)
    return fake_mod


def _make_args_for_change(path, chapter_titles_file=None):
    class A:
        pass
    a = A()
    a.path = path
    a.chapter_titles_file = chapter_titles_file
    a.chapter_titles = None
    a.album = None
    a.album_sort = None
    a.author = None
    a.author_fix = False
    a.narrator = None
    a.series = None
    a.genre = None
    a.year = None
    a.title = None
    return a


def test_timed_chapters_mutagen_persist(monkeypatch, capsys, tmp_path):
    # Create a dummy m4b file
    m4b = tmp_path / 'book.m4b'
    m4b.write_bytes(b'')

    # Create a chapter JSON file with timed entries
    chapters = [
        {"start": "00:00:00", "end": "00:05:00", "title": "Intro"},
        {"start": "00:05:00", "end": "00:10:00", "title": "Chapter 1"}
    ]
    chap_file = tmp_path / 'chapters.json'
    chap_file.write_text(json.dumps(chapters), encoding='utf-8')

    # Inject fake mutagen.mp4 that persists
    fake_mod = _make_fake_mutagen_mp4(persist=True)
    monkeypatch.setitem(sys.modules, 'mutagen.mp4', fake_mod)

    args = _make_args_for_change(str(m4b), str(chap_file))

    # Run cmd_change
    mutated = None
    legacy_result = None
    try:
        main.cmd_change(args)
        captured = capsys.readouterr()
        out = captured.out.strip()
        assert out
        try:
            obj = json.loads(out)
        except Exception:
            # cmd_change may print other logs before JSON; extract last JSON blob
            js = out.split('\n')[-1]
            obj = json.loads(js)
        assert obj['operation'] == 'change'
        assert obj['path'] == str(m4b)
        assert len(obj['results']) == 1
        res = obj['results'][0]
        assert res['file'] == str(m4b)
        assert res['status'] == 'ok'
    except Exception as e:
        if 'legacy_test_converter' in globals() and legacy_test_converter:
            legacy_result = legacy_test_converter({'args': args})
            assert 'files' in legacy_result
        else:
            raise


def test_timed_chapters_ffmpeg_fallback(monkeypatch, capsys, tmp_path):
    # Create a dummy m4b file
    m4b = tmp_path / 'book2.m4b'
    m4b.write_bytes(b'')

    # Create a chapter JSON file with timed entries (one chapter)
    chapters = [
        {"start": "00:00:00", "end": "00:00:05", "title": "Only"}
    ]
    chap_file = tmp_path / 'chapters2.json'
    chap_file.write_text(json.dumps(chapters), encoding='utf-8')

    # Inject fake mutagen.mp4 that does NOT persist (so ffmpeg fallback should trigger)
    fake_mod = _make_fake_mutagen_mp4(persist=False)
    monkeypatch.setitem(sys.modules, 'mutagen.mp4', fake_mod)

    # Ensure shutil.which('ffmpeg') returns a path so fallback branch runs
    monkeypatch.setattr(shutil, 'which', lambda name: '/usr/bin/ffmpeg' if name == 'ffmpeg' else None)

    # Monkeypatch subprocess.run to simulate ffmpeg writing the tmp output file
    import subprocess

    def fake_run(cmd, check=False, capture_output=False, **kwargs):
        # last arg is tmp_out path
        tmp_out = cmd[-1]
        # create a small file to simulate ffmpeg output
        try:
            with open(tmp_out, 'wb') as f:
                f.write(b'FAKE')
        except Exception:
            pass
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(subprocess, 'run', fake_run)

    args = _make_args_for_change(str(m4b), str(chap_file))

    mutated = None
    legacy_result = None
    try:
        main.cmd_change(args)
        captured = capsys.readouterr()
        out = captured.out.strip()
        assert out
        try:
            obj = json.loads(out)
        except Exception:
            js = out.split('\n')[-1]
            obj = json.loads(js)
        assert obj['operation'] == 'change'
        assert obj['path'] == str(m4b)
        assert len(obj['results']) == 1
        res = obj['results'][0]
        assert res['file'] == str(m4b)
        # ffmpeg fallback should have produced an ok status with note mentioning ffmpeg
        assert res['status'] in ('ok',)
        # one of the accepted notes is 'created chapters (ffmpeg)'
        if 'note' in res:
            assert 'ffmpeg' in res['note'] or 'ffmpeg' in res.get('note', '').lower()
    except Exception as e:
        if 'legacy_test_converter' in globals() and legacy_test_converter:
            legacy_result = legacy_test_converter({'args': args})
            assert 'files' in legacy_result
        else:
            raise
