import os

from audiobook_p import main as mainmod


def test_regression_helper_trkn_preserved(tmp_path):
    """Regression test: when the first source file has an ID3 TRCK (e.g. '5/12'),
    the final add_audiobook_metadata should preserve that parsed value and not
    overwrite it with a default (1,N) during post-processing.

    The assertions below include the captured MP4 tag dump in their messages so
    failures are easier to read without running a debugger.
    """
    first_src = str(tmp_path / "01 - Chapter One.m4a")
    second_src = str(tmp_path / "02 - Chapter Two.m4a")

    # Create fake ID3-like object
    class ID3Like:
        def __init__(self, tags):
            self.tags = tags

    def fake_mutagen_file(path):
        if path == first_src:
            return ID3Like({'TRCK': ['5/12']})
        if path == second_src:
            return ID3Like({})
        return ID3Like({})

    # Capture MP4 instance and persist tags across instances (like FakeMP4 in the suite)
    STORE = {}
    created = {}

    class CaptureMP4:
        def __init__(self, path=None):
            self.path = path
            # restore persisted tags if available
            if path in STORE:
                self.tags = dict(STORE[path])
            else:
                self.tags = {}
            created['instance'] = self

        def save(self):
            # persist tags to STORE keyed by path
            if self.path:
                STORE[self.path] = dict(self.tags)

    out = str(tmp_path / 'out_regression.m4b')

    # Call the function under test with injected fakes
    mainmod.add_audiobook_metadata(out, [first_src, second_src], original_source_files=[first_src, second_src], series_name=None, mp4_class=CaptureMP4, mutagen_file_func=fake_mutagen_file)

    inst = created.get('instance')
    assert inst is not None, "No MP4 instance was created (test harness problem)"

    # Helpful failure messages that include the full tag dump
    assert 'trkn' in inst.tags, f"Expected 'trkn' present on final M4B tags, found: {inst.tags!r}"
    tr = inst.tags['trkn'][0]
    assert isinstance(tr, tuple), f"Expected trkn tuple, got {type(tr)!r}, tags={inst.tags!r}"
    assert tr[0] == 5, f"Expected preserved track 5, found {tr[0]} (tags={inst.tags!r})"
