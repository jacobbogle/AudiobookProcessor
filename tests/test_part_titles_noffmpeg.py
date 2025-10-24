import os
import sys
import types
import shutil

import pytest

from audiobook_p import main as mainmod


def test_part_titles_no_ffmpeg(monkeypatch, tmp_path):
    """Unit test: verify mutate_metadata writes TIT2 frames deterministically without running ffmpeg."""
    src = tmp_path / "PartTitlesNoFF" 
    src.mkdir()

    # Create a few empty .mp3 files (mutate_metadata checks only for existence here)
    filenames = [f"{i:02d} - Track {i}.mp3" for i in range(1, 6)]
    filepaths = []
    for name in filenames:
        p = src / name
        p.write_bytes(b"")
        filepaths.append(str(p))

    # Build a metadata_dict compatible with mutate_metadata (minimal)
    files_map = {fp: {} for fp in filepaths}
    meta = {
        'folder_type': 'novel',
        'folder': str(src),
        'files': files_map
    }

    # Replace apply_metadata_to_file with a no-op recorder so mutate_metadata can call it
    calls = []

    def fake_apply(path, md):
        calls.append((path, dict(md)))

    monkeypatch.setattr(mainmod, 'apply_metadata_to_file', fake_apply)

    # Create a fake mutagen.id3 module to intercept ID3/TIT2 operations
    fake_mod = types.ModuleType('mutagen.id3')

    class FakeID3NoHeaderError(Exception):
        pass

    saved_titles = {}

    class FakeTIT2:
        def __init__(self, encoding=3, text=None):
            self.encoding = encoding
            self.text = [text]

    class FakeID3:
        def __init__(self, path=None):
            # If path is provided but file is empty, simulate missing header by raising
            # let mutate_metadata handle creating a new ID3() instance
            if path is not None and os.path.getsize(path) == 0:
                # Simulate ID3 header absence
                raise FakeID3NoHeaderError()
            self._tit2 = None

        def delall(self, key):
            if key.upper() == 'TIT2':
                self._tit2 = None

        def add(self, frame):
            # frame.text is expected to be a list-like
            try:
                txt = frame.text[0]
            except Exception:
                txt = str(frame)
            self._tit2 = txt

        def save(self, path):
            # record the saved title for the given path
            saved_titles[path] = self._tit2

        def getall(self, key):
            if key.upper() == 'TIT2' and self._tit2 is not None:
                # Return a fake frame-like object
                return [types.SimpleNamespace(text=[self._tit2])]
            return []

    fake_mod.ID3 = FakeID3
    fake_mod.TIT2 = FakeTIT2
    fake_mod.ID3NoHeaderError = FakeID3NoHeaderError

    monkeypatch.setitem(sys.modules, 'mutagen.id3', fake_mod)

    # Run mutate_metadata without in_place so a temp copy is created and mutated path is returned
    mutated = mainmod.mutate_metadata(meta, part_titles=True, in_place=False)

    # Validate TIT2 values we recorded via FakeID3.save for each file present in the mutated folder
    import glob
    files = sorted(glob.glob(os.path.join(mutated, '*.mp3')), key=lambda p: __import__('re').split(r'(\d+)', os.path.basename(p)))
    assert files, "No mutated files found"

    cleaned_folder_name = mainmod.clean_album_name(os.path.basename(str(src)))
    for idx, fp in enumerate(files, 1):
        expected = f"{cleaned_folder_name} - Part {1 + ((idx - 1) // 10)} - {idx}"
        got = saved_titles.get(fp)
        assert got == expected, f"Expected TIT2 {expected!r} for {fp}, got {got!r}"
