def create_dummy_audio_with_meta(folder, fname, title=None, extra_meta=None):
    """Create a real 1-second silent audio file with minimal metadata for testing, using ffmpeg for compatibility."""
    import subprocess
    fpath = os.path.join(folder, fname)
    ext = os.path.splitext(fname)[1].lower()
    # Use ffmpeg to generate a 1-second silent audio file in the correct format
    if ext in ['.mp3', '.m4a', '.m4b']:
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'lavfi',
            '-i', 'anullsrc=r=44100:cl=mono',
            '-t', '1',
            '-acodec', 'aac' if ext in ['.m4a', '.m4b'] else 'libmp3lame',
            fpath
        ]
        # For .m4a/.m4b, force output format
        if ext in ['.m4a', '.m4b']:
            cmd.extend(['-f', 'mp4'])
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except Exception as e:
            raise RuntimeError(f"Failed to create dummy audio file with ffmpeg: {e}\nCommand: {' '.join(cmd)}")
    else:
        # Unknown extension, just create an empty file
        with open(fpath, 'wb') as f:
            f.write(b'')
    meta = {
        'title': title or os.path.splitext(fname)[0],
        'album': 'Test Album Folder',
        'album_sort': 'Test Album Folder',
        'sort_title': fname,
        'media_kind': 2,
        'gapless_playback': None,
        'tvsn': None,
        'track': '1',
        'track_number': '1',
        'track_tuple': (1, 2),
        'artist': 'Test Artist',
        'genre': 'Audiobook',
        'extra': 'preserve_me',
        'grouping': '',
        'series': '',
        'series_index': '',
        'title_sort': os.path.splitext(fname)[0],
    }
    if extra_meta:
        meta.update(extra_meta)
    return fpath, meta
import mutagen
import os
import tempfile

# Move check_m4b_metadata to module level so all tests can use it
def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title, expected_grouping=None, expected_tvsn=None):
    audio = mutagen.File(m4b_path)
    tags = getattr(audio, 'tags', {})
    album = tags.get('\u00a9alb') or tags.get('album')
    if isinstance(album, (list, tuple)):
        album = album[0]
    assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
    soal = tags.get('soal') or tags.get('ALBUMSORT')
    if isinstance(soal, (list, tuple)):
        soal = soal[0]
    assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
    title = tags.get('\u00a9nam') or tags.get('title')
    if isinstance(title, (list, tuple)):
        title = title[0]
    assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"
    if expected_grouping is not None:
        grouping = tags.get('\u00a9grp') or tags.get('grouping')
        if isinstance(grouping, (list, tuple)):
            grouping = grouping[0]
        assert grouping == expected_grouping, f"M4B grouping tag: {grouping!r} != {expected_grouping!r}"
    if expected_tvsn is not None:
        tvsn = tags.get('tvsn') or tags.get('TVSN')
        if isinstance(tvsn, (list, tuple)):
            tvsn = tvsn[0]
        assert tvsn == expected_tvsn, f"M4B tvsn tag: {tvsn!r} != {expected_tvsn!r}"
import pytest

# ...existing code...

# Additional test cases for the series index parser
@pytest.mark.parametrize("series_folder_name,expected_index", [
    ("Book 1", 1),
    ("Book 01", 1),
    ("Book 10", 10),
    ("Volume 2", 2),
    ("Vol 03", 3),
    ("Part 4", 4),
    ("4", 4),
    ("The Book 5", 5),
    ("Book One", 1),  # Written number should parse as 1
    ("Book", None),      # No index
    ("Book 1A", None),   # Not a pure number
    ("Book 001", 1),
    ("Book 0002", 2),
    ("Book 1 - Special", 1),
    ("Book 2: The Sequel", 2),
    ("Book 3 (Unabridged)", 3),
    ("Book 4.5", 4),  # Should parse as 4
    ("Book 5 Extra", 5),
    ("Book Six", 6),  # Written number should parse as 6
])
def test_series_index_parser_cases(series_folder_name, expected_index):
    from audiobook_p.utils import parse_series_index_from_folder
    idx = parse_series_index_from_folder(series_folder_name)
    assert idx == expected_index, f"For '{series_folder_name}', expected {expected_index}, got {idx}"


@pytest.mark.parametrize("ext", [".m4a"])
def test_m4a_to_m4b_metadata_assignment(ext):
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = file_stem  # Expect full filename as title when no explicit title is provided
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = file_stem  # Expect full filename as title when no explicit title is provided
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'
        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
    s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
    assert isinstance(s_result, dict)
    s_parent_dir = os.path.basename(os.path.dirname(book_folder))
    s_folder_name = os.path.basename(book_folder)
    s_expected_album = clean_album_name(s_folder_name)
    s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
    from audiobook_p.utils import clean_folder_name
    expected_grouping = clean_folder_name("Test Series")
    expected_series_index = 1  # Parsed from "Book 1"
    for f, m in s_result['files'].items():
        fname = os.path.basename(f)
        file_stem = os.path.splitext(fname)[0]
        if fname == s_fname1:
            expected_title = file_stem  # Expect full filename as title when no explicit title is provided
            assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
        elif fname == s_fname2:
            assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
                assert m['album'] == s_expected_album
                assert m['album_sort'] == s_expected_album_sort
                assert m['title_sort'] == file_stem
                assert m['media_kind'] == 2
                assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
                assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
                assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
                assert m['track_number'] == m['track']
                assert m['extra'] == 'preserve_me'

        s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)


@pytest.mark.parametrize("ext", [".mp3"])
def test_mp3_to_m4b_metadata_assignment(ext):
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    # ...existing code...

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = file_stem  # Expect full filename as title when no explicit title is provided
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2, meta2 = create_dummy_audio_with_meta(folder, fname2, title="My Real Title")
        files_map = {fpath1: meta1, fpath2: meta2}
        meta_dict = {
            'folder_type': 'novel',
            'folder': folder,
            'files': files_map
        }
        result = mutate_metadata(meta_dict)
        assert isinstance(result, dict)
        assert 'files' in result
        from audiobook_p.utils import book_title_logic, clean_album_name
        parent_dir = os.path.basename(os.path.dirname(folder))
        folder_name = os.path.basename(folder)
        expected_album = clean_album_name(folder_name)
        expected_album_sort = clean_album_name(folder_name)  # For standalone/novel, album_sort is just the folder name
        for f, m in result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"Expected title to be '{expected_title}' for {fname}"
            elif fname == fname2:
                assert m['title'] == "My Real Title", f"Expected title to be preserved for {fname}"
            assert m['album'] == expected_album
            assert m['album_sort'] == expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m.get('tvsn') is None or m.get('tvsn') == ''
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

        m4b_out = os.path.join(tmpdir, f"test_novel_out_{ext[1:]}.m4b")
        convert_folder_to_m4b(folder, m4b_out, sort_by='filename')
        check_m4b_metadata(m4b_out, expected_album, expected_album_sort, expected_album)

        # --- Series example ---
        series_folder = os.path.join(tmpdir, "Test Series")
        os.makedirs(series_folder)
        book_folder = os.path.join(series_folder, "Book 1")
        os.makedirs(book_folder)
        s_fname1 = f"01 - SeriesNoTitle{ext}"
        s_fpath1, s_meta1 = create_dummy_audio_with_meta(book_folder, s_fname1, title=None)
        s_fname2 = f"02 - SeriesHasTitle{ext}"
        s_fpath2, s_meta2 = create_dummy_audio_with_meta(book_folder, s_fname2, title="Series Real Title")
        s_files_map = {s_fpath1: s_meta1, s_fpath2: s_meta2}
        s_meta_dict = {
            'folder_type': 'series',
            'folder': book_folder,
            'files': s_files_map,
            'series_name': "Test Series"
        }
        s_result = mutate_metadata(s_meta_dict, series_name="Test Series")
        assert isinstance(s_result, dict)
        assert 'files' in s_result
        s_parent_dir = os.path.basename(os.path.dirname(book_folder))
        s_folder_name = os.path.basename(book_folder)
        s_expected_album = clean_album_name(s_folder_name)
        s_expected_album_sort = f"{clean_album_name(s_parent_dir)} - {s_expected_album}"
        from audiobook_p.utils import clean_folder_name
        expected_grouping = clean_folder_name("Test Series")
        expected_series_index = 1  # Parsed from "Book 1"
        for f, m in s_result['files'].items():
            fname = os.path.basename(f)
            file_stem = os.path.splitext(fname)[0]
            if fname == s_fname1:
                expected_title = book_title_logic(file_stem)
                assert m['title'] == expected_title, f"[Series] Expected title to be '{expected_title}' for {fname}"
            elif fname == s_fname2:
                assert m['title'] == "Series Real Title", f"[Series] Expected title to be preserved for {fname}"
            assert m['album'] == s_expected_album
            assert m['album_sort'] == s_expected_album_sort
            assert m['title_sort'] == file_stem
            assert m['media_kind'] == 2
            assert m.get('gapless_playback') in (True, 1, '1', 'true', 'True', None)
            assert m['series_index'] == expected_series_index, f"Expected series_index to be {expected_series_index}, got {m.get('series_index')}"
            assert m['grouping'] == expected_grouping, f"Expected grouping to be {expected_grouping!r}, got {m.get('grouping')!r}"
            assert m['track_number'] == m['track']
            assert m['extra'] == 'preserve_me'

            s_m4b_out = os.path.join(tmpdir, f"test_series_out_{ext[1:]}.m4b")
            convert_folder_to_m4b(book_folder, s_m4b_out, sort_by='filename', series_name="Test Series", original_source_path=book_folder, grouping="Test Series", series_index=1)
        check_m4b_metadata(s_m4b_out, s_expected_album, s_expected_album_sort, s_expected_album, expected_grouping, expected_series_index)
    import shutil
    from audiobook_p.mutation import mutate_metadata, convert_folder_to_m4b
    import mutagen
    def check_m4b_metadata(m4b_path, expected_album, expected_album_sort, expected_title):
        audio = mutagen.File(m4b_path)
        tags = getattr(audio, 'tags', {})
        album = tags.get('\u00a9alb') or tags.get('album')
        if isinstance(album, (list, tuple)):
            album = album[0]
        assert album == expected_album, f"M4B album tag: {album!r} != {expected_album!r}"
        soal = tags.get('soal') or tags.get('ALBUMSORT')
        if isinstance(soal, (list, tuple)):
            soal = soal[0]
        assert soal == expected_album_sort, f"M4B album_sort tag: {soal!r} != {expected_album_sort!r}"
        title = tags.get('\u00a9nam') or tags.get('title')
        if isinstance(title, (list, tuple)):
            title = title[0]
        assert title == expected_title, f"M4B title tag: {title!r} != {expected_title!r}"

    with tempfile.TemporaryDirectory() as tmpdir:
        # --- Novel/standalone example ---
        folder = os.path.join(tmpdir, "Test Album Folder")
        os.makedirs(folder)
        fname1 = f"01 - NoTitle{ext}"
        fpath1, meta1 = create_dummy_audio_with_meta(folder, fname1, title=None)
        fname2 = f"02 - HasTitle{ext}"
        fpath2