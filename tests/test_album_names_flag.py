import os
import json
from audiobook_p.main import add_audiobook_metadata, clean_album_name


class DummyMP4Tags(dict):
    pass


class DummyMP4:
    _instances = {}

    def __new__(cls, path):
        # Return same instance per path so tests can inspect tags after function returns
        if path in cls._instances:
            return cls._instances[path]
        inst = super(DummyMP4, cls).__new__(cls)
        cls._instances[path] = inst
        return inst

    def __init__(self, path):
        # Simulate an MP4 object with tags attribute
        if not hasattr(self, 'initialized'):
            self.path = path
            self.tags = DummyMP4Tags()
            self.initialized = True

    def save(self):
        # No-op save to satisfy add_audiobook_metadata
        return


def dummy_mutagen_file(path):
    # Return a fake source audio object with tags similar to mutagen.File
    class FakeSource:
        def __init__(self):
            self.tags = {
                'title': ['Chapter 1'],
                'artist': ['Author Name']
            }
    return FakeSource()


def test_album_names_forces_album_to_cleaned_folder(tmp_path):
    # Prepare a fake m4b path and fake source files list
    m4b_path = str(tmp_path / "test.m4b")
    # Create a dummy file to satisfy MP4 constructor if needed
    open(m4b_path, 'wb').close()

    raw_folder_name = "Seventh Son"
    cleaned = clean_album_name(raw_folder_name)

    # Call add_audiobook_metadata with mp4_class and mutagen_file_func injections
    # Prepare a fake source file inside a folder named 'Seventh Son' so
    # add_audiobook_metadata infers the cleaned album name from the folder.
    source_folder = tmp_path / raw_folder_name
    source_folder.mkdir()
    fake_source = source_folder / "audio1.m4a"
    fake_source.write_bytes(b"")
    source_files = [str(fake_source)]
    add_audiobook_metadata(
        m4b_path,
        source_files,
        original_source_files=source_files,
        series_name=None,
        mp4_class=DummyMP4,
        mutagen_file_func=dummy_mutagen_file,
        chapters_info=None,
        chapter_titles=False,
        author_fix=False,
        cli_author=None,
        album_names=True,
    )

    # Load the MP4 object created by DummyMP4 and inspect tags
    mp4_obj = DummyMP4(m4b_path)
    # Inspect the DummyMP4 instance used inside add_audiobook_metadata
    mp4_instance = DummyMP4(m4b_path)
    # When album_names=True, the function should set the \xa9alb tag to cleaned folder name
    assert '\xa9alb' in mp4_instance.tags or '\u00A9alb' in mp4_instance.tags
    # Normalize key lookup for either escaped or actual char
    val = None
    if '\xa9alb' in mp4_instance.tags:
        val = mp4_instance.tags['\xa9alb']
    elif '\u00A9alb' in mp4_instance.tags:
        val = mp4_instance.tags['\u00A9alb']

    # Expect the tag to be a list containing the cleaned album name
    assert isinstance(val, list)
    assert val[0] == cleaned
