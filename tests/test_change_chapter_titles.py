import os
import json
import tempfile
from types import SimpleNamespace
import pytest

from audiobook_p import main as mainmod


class FakeChapter:
    def __init__(self, start, title):
        self.start = start
        self.title = title


class FakeMP4:
    def __init__(self, chapters):
        # chapters: list of FakeChapter
        self._chapters = list(chapters)
        self.chapters = self._chapters
        self.saved = False

    def save(self):
        self.saved = True


def run_cmd_change_with_mock(mp4_obj, tmp_m4b_path, titles):
    # Monkeypatch MP4 in the module to return our fake object
    def fake_mp4(path):
        assert path == tmp_m4b_path
        return mp4_obj

    # Prepare args namespace
    args = SimpleNamespace()
    args.path = tmp_m4b_path
    args.album = None
    args.album_sort = None
    args.author = None
    args.narrator = None
    args.series = None
    args.genre = None
    args.year = None
    args.title = None
    args.chapter_titles = titles

    # Patch MP4 class used in mainmod
    mainmod_mut = mainmod
    orig_MP4 = None
    try:
        import mutagen.mp4 as mp4mod
        # Save original if exists
        if hasattr(mp4mod, 'MP4'):
            orig_MP4 = mp4mod.MP4
        mp4mod.MP4 = fake_mp4
    except Exception:
        # If mutagen not available in test env, patch at import path used in mainmod
        mainmod.MP4 = fake_mp4

    # Run cmd_change
    try:
        mainmod.cmd_change(args)
    finally:
        # Restore
        try:
            if orig_MP4 is not None:
                mp4mod.MP4 = orig_MP4
        except Exception:
            pass


def test_change_chapter_titles_success(tmp_path, capsys):
    # Create fake m4b file placeholder
    tmp_m4b = tmp_path / "book.m4b"
    tmp_m4b.write_text("placeholder")

    # Two existing chapters
    chs = [FakeChapter(0, "Old 1"), FakeChapter(60, "Old 2")]
    fake = FakeMP4(chs)

    # Run change with shorthand titles
    run_cmd_change_with_mock(fake, str(tmp_m4b), ["ch1", "ch2"])

    # After running, ensure save was called (fake.saved True)
    assert fake.saved is True


def test_change_chapter_titles_mismatch(tmp_path, capsys):
    tmp_m4b = tmp_path / "book.m4b"
    tmp_m4b.write_text("placeholder")

    # Three existing chapters
    chs = [FakeChapter(0, "Old 1"), FakeChapter(60, "Old 2"), FakeChapter(120, "Old 3")]
    fake = FakeMP4(chs)

    # Run change with only two new titles (should error)
    run_cmd_change_with_mock(fake, str(tmp_m4b), ["ch1", "ch2"])

    # save should not be called because of mismatch
    assert fake.saved is False
