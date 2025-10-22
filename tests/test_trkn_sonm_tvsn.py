import os
import types
import pytest

from audiobook_p import main as mainmod


STORE = {}


class FakeMP4:
    def __init__(self, path=None):
        self.path = path
        # persist tags across instances by storing in STORE keyed by path
        if path in STORE:
            self.tags = dict(STORE[path])
        else:
            self.tags = {}

    def save(self):
        # persist tags to store
        if self.path:
            STORE[self.path] = dict(self.tags)
        self._saved = True


class FakeSourceFile:
    def __init__(self, tags):
        self.tags = tags


def test_trkn_and_sonm_from_first_source(monkeypatch, tmp_path):
    # Prepare fake first source with an MP4 trkn value
    first_src = str(tmp_path / "01 - Chapter One.m4a")

    def fake_mutagen_file(path):
        if path == first_src:
            return FakeSourceFile({'trkn': [(5, 12)]})
        return FakeSourceFile({})

    # Monkeypatch mutagen.mp4.MP4 and related symbols plus MutagenFile used by main module
    created = {}

    class CaptureMP4(FakeMP4):
        def __init__(self, path=None):
            super().__init__(path)
            created['instance'] = self


    out = str(tmp_path / 'out.m4b')

    # Call the function under test, injecting our fake MP4 class and Mutagen.File
    mainmod.add_audiobook_metadata(out, [first_src], original_source_files=[first_src], series_name='Series Test', mp4_class=CaptureMP4, mutagen_file_func=fake_mutagen_file)

    # Inspect created instance
    inst = created.get('instance')
    assert inst is not None
    # trkn should reflect original track (5)
    assert 'trkn' in inst.tags
    tr = inst.tags['trkn'][0]
    assert isinstance(tr, tuple) and tr[0] == 5
    # sonm should equal uncleaned filename stem
    assert 'sonm' in inst.tags and inst.tags['sonm'][0] == '01 - Chapter One'


def test_tvsn_inference_from_original_folder(monkeypatch, tmp_path):
    # Prepare path where parent folder includes numeric index "Book 03"
    first_src = str(tmp_path / "Book 03" / "01 - Chapter One.m4a")
    os.makedirs(os.path.dirname(first_src), exist_ok=True)

    # Fake MutagenFile to return no trkn so trkn derivation uses index
    def fake_mutagen_file(path):
        return FakeSourceFile({})

    # Capture the MP4 instance created by add_audiobook_metadata
    created = {}

    class CaptureMP4(FakeMP4):
        def __init__(self, path=None):
            super().__init__(path)
            created['instance'] = self


    out = str(tmp_path / 'out2.m4b')
    # Call with original_source_files containing a parent folder 'Book 03'
    mainmod.add_audiobook_metadata(out, [first_src], original_source_files=[first_src], series_name=None, mp4_class=CaptureMP4, mutagen_file_func=fake_mutagen_file)

    inst = created.get('instance')
    assert inst is not None
    # tvsn should be inferred as 3 from 'Book 03'
    assert 'tvsn' in inst.tags and inst.tags['tvsn'][0] == 3


def test_id3_trck_parsing_and_index_fallback(monkeypatch, tmp_path):
    # Test parsing of ID3-style TRCK strings and fallback to index
    # Prepare two source files where the first has ID3 TRCK='5/12' and second has none
    first_src = str(tmp_path / "01 - Chapter One.m4a")
    second_src = str(tmp_path / "02 - Chapter Two.m4a")

    # Fake MutagenFile that returns an object whose tags mimic ID3 frames
    class ID3Like:
        def __init__(self, tags):
            self.tags = tags

    def fake_mutagen_file(path):
        if path == first_src:
            # TRCK as string '5/12'
            return ID3Like({'TRCK': ['5/12']})
        if path == second_src:
            return ID3Like({})
        return ID3Like({})

    # Capture MP4 instance
    created = {}

    class CaptureMP4(FakeMP4):
        def __init__(self, path=None):
            super().__init__(path)
            created['instance'] = self

    out = str(tmp_path / 'out3.m4b')
    # Call with both sources - expect trkn to come from parsed TRCK -> 5
    mainmod.add_audiobook_metadata(out, [first_src, second_src], original_source_files=[first_src, second_src], series_name=None, mp4_class=CaptureMP4, mutagen_file_func=fake_mutagen_file)

    inst = created.get('instance')
    assert inst is not None
    assert 'trkn' in inst.tags
    tr = inst.tags['trkn'][0]
    assert isinstance(tr, tuple) and tr[0] == 5

    # Now test fallback: no tags at all, expect index-derived track=1
    created2 = {}

    class CaptureMP4B(FakeMP4):
        def __init__(self, path=None):
            super().__init__(path)
            created2['instance'] = self

    def fake_none(path):
        return ID3Like({})

    outb = str(tmp_path / 'out4.m4b')
    mainmod.add_audiobook_metadata(outb, [first_src, second_src], original_source_files=[first_src, second_src], series_name=None, mp4_class=CaptureMP4B, mutagen_file_func=fake_none)
    inst2 = created2.get('instance')
    assert inst2 is not None
    assert 'trkn' in inst2.tags
    tr2 = inst2.tags['trkn'][0]
    assert isinstance(tr2, tuple) and tr2[0] == 1
