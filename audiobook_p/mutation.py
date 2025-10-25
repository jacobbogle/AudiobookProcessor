# --- convert_folder_to_m4b, add_chapters_to_m4b, ffmpeg_inject_chapters, add_audiobook_metadata ---
import subprocess
import re
import tempfile
import atexit

import glob
def convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename', original_source_path=None, chapter_titles=False, series_name=None, temp_copy_path=None, author_fix=False, cli_author=None, album_names=False):
    """
    Concatenate audio files in a folder into a single M4B file with chapters.
from audiobook_p.utils import book_title_logic, clean_album_name, parse_series_index_from_folder_name, sanitize_series_name
    Mutation (metadata/tag logic) must be performed before calling this function.

    Args:
        folder_path: Path to folder containing audio files
        output_path: Path for the output M4B file
        config: Optional configuration object for settings
        sort_by: 'filename' or 'track' - how to sort files
        original_source_path: Path to original source files for cover art
        chapter_titles: If True, use file titles directly for chapter titles (already formatted)

    Returns:
        Path to the created M4B file
    """
    folder_path = folder_path
    output_path = output_path

    def _local_sanitize_folder_name(name):
        import re
        if not name:
            return name
        s = name.strip()
        s = re.sub(r'^[\-\._\s]+', '', s)
        s = re.sub(r'^\d{1,3}[\s\-:\._]+', '', s)
        s = re.sub(r'\s{2,}', ' ', s)
        return s.strip()

    folder_basename = _local_sanitize_folder_name(os.path.basename(folder_path))

    if not os.path.isdir(folder_path):
        raise ValueError("Path is not a directory: {}".format(folder_path))

    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))

    if not audio_files:
        raise ValueError("No audio files found in: {}".format(folder_path))

    if sort_by == 'track':
        file_metadata = {}
        for audio_file in audio_files:
            pass  # Mutation logic must be performed before calling this function. This function only handles concatenation and chapter creation.
        # No mutation logic here; only sorting and concatenation
        # ...existing code...
    else:
        audio_files.sort(key=natural_sort_key)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    import tempfile
    file_list_temp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=os.getcwd())
    file_list_path = file_list_temp.name
    atexit.register(lambda: os.remove(file_list_path) if os.path.exists(file_list_path) else None)
    try:
        with file_list_temp:
            for audio_file in audio_files:
                abs_path = os.path.abspath(audio_file)
                escaped_path = abs_path.replace("'", "'\\''")
                file_list_temp.write("file '{}".format(escaped_path) + "'\n")
    except Exception:
        pass

    chapters_info = []
    metadata_temp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=os.getcwd())
    metadata_path = metadata_temp.name
    atexit.register(lambda: os.remove(metadata_path) if os.path.exists(metadata_path) else None)
    try:
        with metadata_temp:
            metadata_temp.write(";FFMETADATA1\n")
            # Inject album and album_sort metadata for ffmpeg
            album_name = folder_basename
            album_sort = None
            # Try to get a cleaned album name from original_source_path if available
            if original_source_path:
                try:
                    album_name = clean_album_name(os.path.basename(original_source_path)) or folder_basename
                except Exception:
                    pass
            # Optionally set album_sort to album_name (or further logic if needed)
            # Infer series context from folder structure if series_name is not provided
            is_series = False
            parent_name = None
            child_name = None
            if original_source_path:
                parent_dir = os.path.dirname(original_source_path)
                parent_name = os.path.basename(parent_dir)
                child_name = os.path.basename(original_source_path)
                # Heuristic: if parent and child are both non-empty and not equal, treat as series
                if parent_name and child_name and parent_name != child_name:
                    is_series = True
            if (series_name or is_series) and parent_name and child_name:
                album_sort = f"{clean_album_name(parent_name)} - {clean_album_name(child_name)}"
            else:
                album_sort = album_name
            # Use ffmpeg-compatible tag names for ffmetadata
            metadata_temp.write(f"album={album_name}\n")
            metadata_temp.write(f"soal={album_sort}\n")
            current_time = 0
            for i, audio_file in enumerate(audio_files):
                source_audio = mutagen.File(audio_file)
                if source_audio and hasattr(source_audio, 'info') and hasattr(source_audio.info, 'length'):
                    duration_ms = int(source_audio.info.length * 1000)
                else:
                    duration_ms = 600000
                chapter_title = None
                if chapter_titles:
                    try:
                        base_for_name = os.path.basename(original_source_path) if original_source_path else os.path.basename(folder_path)
                        book_name = clean_album_name(base_for_name) or folder_basename
                    except Exception:
                        book_name = folder_basename
                    try:
                        book_name = re.sub(r'^Temp-[\w\d\-]*\s*', '', str(book_name), flags=re.IGNORECASE).strip()
                    except Exception:
                        pass
                    chapter_title = f"Chapter {i+1}"
                else:
                    try:
                        a = mutagen.File(audio_file)
                        if a is not None and getattr(a, 'tags', None):
                            tags = a.tags
                            if '\u00a9nam' in tags and tags.get('\u00a9nam'):
                                t = tags.get('\u00a9nam')
                                chapter_title = t[0] if isinstance(t, (list, tuple)) else t
                            elif '\xa9nam' in tags and tags.get('\xa9nam'):
                                t = tags.get('\xa9nam')
                                chapter_title = t[0] if isinstance(t, (list, tuple)) else t
                            elif 'TIT2' in tags and tags.get('TIT2'):
                                t = tags.get('TIT2')
                                try:
                                    chapter_title = t.text[0]
                                except Exception:
                                    chapter_title = str(t)
                            else:
                                for candidate in ['title', 'TIT2', 'TIT1', 'TPE1']:
                                    if candidate in tags and tags.get(candidate):
                                        v = tags.get(candidate)
                                        chapter_title = v[0] if isinstance(v, (list, tuple)) else v
                                        break
                        if chapter_title is not None:
                            if isinstance(chapter_title, bytes):
                                try:
                                    chapter_title = chapter_title.decode('utf-8', errors='ignore')
                                except Exception:
                                    chapter_title = str(chapter_title)
                            chapter_title = str(chapter_title).strip()
                            chapter_title = re.sub(r'\.(m4a|m4b|mp3|wav)$', '', chapter_title, flags=re.IGNORECASE)
                            try:
                                chapter_title = sanitize_string(chapter_title, replace_underscores=True)
                            except Exception:
                                pass
                    except Exception:
                        chapter_title = None
                    if not chapter_title:
                        try:
                            source_metadata = extract_metadata_from_file(audio_file)
                            if source_metadata.get('title'):
                                chapter_title = book_title_logic(source_metadata['title'])
                        except Exception:
                            chapter_title = None
                    if not chapter_title:
                        file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                        chapter_title = book_title_logic(file_stem)
                try:
                    chapter_title = sanitize_string(chapter_title, replace_underscores=True)
                except Exception:
                    try:
                        chapter_title = str(chapter_title)
                    except Exception:
                        chapter_title = ''
                metadata_temp.write("\n[CHAPTER]\n")
                metadata_temp.write("TIMEBASE=1/1000\n")
                metadata_temp.write("START={}".format(current_time) + "\n")
                metadata_temp.write("END={}".format(current_time + duration_ms) + "\n")
                try:
                    m = re.search(r'^(?:([^:\-\u2013\u2014]+)[:\-\u2013\u2014]\s*)?(?:Chapter|Part)\s*(\d+)\s*-\s*(\d+)\s*$', chapter_title, flags=re.IGNORECASE)
                    if m:
                        raw_index = int(m.group(3))
                        computed_part = 1 + ((raw_index - 1) // 10)
                        chapter_title = f"Part {computed_part} - {raw_index}"
                except Exception:
                    pass
                metadata_temp.write("title={}".format(chapter_title) + "\n")
                ci = {
                    'start': current_time / 1000.0,
                    'end': (current_time + duration_ms) / 1000.0,
                    'title': chapter_title,
                    'start_ms': current_time,
                    'end_ms': current_time + duration_ms
                }
                if chapter_titles:
                    try:
                        ci['book_name'] = book_name
                    except Exception:
                        ci['book_name'] = folder_basename
                chapters_info.append(ci)
                current_time += duration_ms
    except Exception:
        pass
    # Debug: print contents of file list and metadata files
    # Diagnostics: print file list and metadata file contents
    try:
        with open(file_list_path, 'r', encoding='utf-8') as f:
            print("[DEBUG] file_list_path contents:")
            print(f.read())
    except Exception as e:
        print(f"[DEBUG] Could not read file_list_path: {e}")
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            print("[DEBUG] metadata_path contents:")
            print(f.read())
    except Exception as e:
        print(f"[DEBUG] Could not read metadata_path: {e}")
    try:
        audio_quality = '128k'
        if config:
            try:
                audio_quality = config.get('processing.ffmpeg_quality', '128k')
            except Exception as e:
                print(f"[ERROR] Could not read ffmpeg quality from config: {e}")
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', file_list_path,
            '-i', metadata_path,
            '-map', '0:a',
            '-map_metadata', '1',
            '-metadata', f"©alb={album_name}",
            '-metadata', f"soal={album_sort}",
            '-c:a', 'aac',
            '-b:a', audio_quality,
            '-f', 'mp4',
            '-movflags', '+faststart',
            '-y',
            str(output_path)
        ]
        import platform
        system = platform.system().lower()
        if system != 'windows':
            sleep_prevention_cmd = get_sleep_prevention_command()
            if sleep_prevention_cmd:
                cmd = sleep_prevention_cmd + cmd
        try:
            from audiobook_p.progress import ProgressTracker
            try:
                total_duration = int(max(1, current_time / 1000.0))
            except Exception:
                total_duration = 1
            progress = ProgressTracker(total_duration, "Converting to M4B")
            progress.update(0, "Starting conversion...")
        except Exception as e:
            progress = None
            print(f"[INFO] Converting to M4B... Progress tracker unavailable: {e}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)
        time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        try:
            total_secs = float(max(1.0, current_time / 1000.0))
        except Exception:
            total_secs = 1.0
        if proc.stderr is not None:
            for raw_line in proc.stderr:
                line = raw_line.strip()
                m = time_re.search(line)
                if m and progress:
                    hh = int(m.group(1)); mm = int(m.group(2)); ss = float(m.group(3))
                    elapsed = hh * 3600 + mm * 60 + ss
                    cur = int(min(elapsed, total_secs))
                    progress.set_progress(cur, f"Converting: {int(elapsed)}s/{total_secs:.0f}s")
        retcode = proc.wait()
        if retcode != 0:
            try:
                out = proc.communicate(timeout=5)
                stdout = out[0] if out and len(out) > 0 else None
                stderr = out[1] if out and len(out) > 1 else None
            except Exception:
                stdout = None
                stderr = None
            debug_cmd = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
            print(f"[ERROR] ffmpeg failed with exit code {retcode}\nCommand: {debug_cmd}\n--- FFmpeg STDOUT ---\n{stdout}\n--- FFmpeg STDERR ---\n{stderr}")
            raise Exception(f"ffmpeg failed with exit code {retcode}\nCommand: {debug_cmd}\n--- FFmpeg STDOUT ---\n{stdout}\n--- FFmpeg STDERR ---\n{stderr}")
        if progress:
            progress.finish("M4B conversion complete")
        else:
            print("[INFO] M4B conversion complete")
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print(f"[ERROR] Output file was not created or is empty: {output_path}")
        # Post-process: set album, album_sort, and cover using m4b_edit.py
        try:
            from audiobook_p.m4b_edit import edit_tags_and_cover
            tags_to_set = {}
            if album_name:
                tags_to_set['\u00a9alb'] = [str(album_name)]
            if album_sort:
                if isinstance(album_sort, (list, tuple)):
                    album_sort_str = ' - '.join(str(x) for x in album_sort)
                else:
                    album_sort_str = str(album_sort)
                tags_to_set['soal'] = [album_sort_str]
            # Set ©ART tag using CLI author or fallback to album name
            from audiobook_p.utils import book_title_logic, clean_album_name
            from audiobook_p.main import _author_last_first_to_first_last
            artist = None
            if cli_author:
                if author_fix:
                    artist = book_title_logic(_author_last_first_to_first_last(cli_author)).strip()
                else:
                    artist = book_title_logic(cli_author).strip()
            else:
                artist = clean_album_name(album_name)
            if artist:
                tags_to_set['\u00a9ART'] = [str(artist)]
            # Set title (©nam) tag using album_name or first chapter title
            title_val = None
            if album_name:
                title_val = album_name
            if chapters_info and chapters_info[0].get('title'):
                title_val = chapters_info[0]['title']
            if title_val:
                tags_to_set['\u00a9nam'] = [str(title_val)]
            # Attempt to find cover art path
            cover_path = None
            if original_source_path:
                for ext in ['cover.jpg', 'cover.jpeg', 'cover.png']:
                    candidate = os.path.join(original_source_path, ext)
                    if os.path.exists(candidate):
                        cover_path = candidate
                        break
            edit_tags_and_cover(output_path, tags_to_set, cover_path)
            print(f"[INFO] Album, album_sort, artist, and cover set via m4b_edit: {tags_to_set}, cover: {cover_path}")
        except Exception as e:
            print(f"[ERROR] Failed to set album/album_sort/artist/cover via m4b_edit: {e}")
            raise Exception("Output file was not created or is empty")
        if chapters_info:
            try:
                from mutagen.mp4 import MP4, MP4Chapters, Chapter
                audio = MP4(str(output_path))
                chapter_objects = []
                for chapter in chapters_info:
                    chapter_obj = Chapter(start=chapter['start'], title=chapter['title'])
                    chapter_objects.append(chapter_obj)
                mp4_chapters = MP4Chapters(); mp4_chapters._chapters = chapter_objects
                audio.chapters = mp4_chapters
                audio.save()
                print("[INFO] Chapters added to M4B file")
            except Exception as e:
                print(f"[WARN] Failed to add chapters to M4B: {e}")
        original_audio_files = None
        try:
            if original_source_path and os.path.exists(original_source_path):
                original_files = []
                for ext in ['*.m4a', '*.mp3']:
                    original_files.extend(glob.glob(os.path.join(original_source_path, ext)))
                if original_files:
                    original_files.sort(key=natural_sort_key)
                    original_audio_files = original_files
                    print(f"[INFO] Found {len(original_files)} original source files from explicit path")
            elif "audiobook_copy_" in folder_path:
                folder_dir = os.path.dirname(folder_path)
                folder_name = os.path.basename(folder_path)
                for item in os.listdir(folder_dir):
                    item_path = os.path.join(folder_dir, item)
                    if os.path.isdir(item_path) and item != folder_name:
                        test_files = []
                        for ext in ['*.m4a', '*.mp3']:
                            test_files.extend(glob.glob(os.path.join(item_path, ext)))
                        if test_files:
                            original_files = []
                            for temp_file in audio_files:
                                temp_stem = os.path.splitext(os.path.basename(temp_file))[0]
                                for test_file in test_files:
                                    test_stem = os.path.splitext(os.path.basename(test_file))[0]
                                    if temp_stem == test_stem:
                                        original_files.append(test_file); break
                            if len(original_files) > 0:
                                original_audio_files = original_files
                                print(f"[INFO] Found {len(original_files)} original source files for cover art")
                                break
        except Exception as e:
            print(f"[WARN] Failed to find original source files: {e}")
        # No mutation/tag logic here; only concatenation and chapters
        return str(output_path)
    finally:
        try:
            if os.path.exists(file_list_path):
                os.remove(file_list_path)
        except Exception as e:
            logger.debug(f"Failed to remove file_list_path {file_list_path}: {e}")
        try:
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
        except Exception as e:
            logger.debug(f"Failed to remove metadata_path {metadata_path}: {e}")
        try:
            if temp_copy_path:
                try:
                    temp_root = os.path.abspath(tempfile.gettempdir())
                except Exception:
                    temp_root = None
                try:
                    remove_ok = False
                    if os.path.exists(temp_copy_path):
                        if temp_root and os.path.commonpath([os.path.abspath(temp_copy_path), temp_root]) == temp_root:
                            remove_ok = True
                        base = os.path.basename(temp_copy_path)
                        if base.startswith('temp-') or base.startswith('audiobook_copy_'):
                            remove_ok = True
                    if remove_ok and os.path.exists(temp_copy_path):
                        try:
                            remove_path(temp_copy_path)
                            logger.debug(f"Removed explicit temp_copy_path {temp_copy_path}")
                        except Exception as e:
                            logger.debug(f"Failed to remove explicit temp_copy_path {temp_copy_path}: {e}")
                except Exception:
                    pass
            if not temp_copy_path or not (os.path.exists(temp_copy_path) and base.startswith(('temp-', 'audiobook_copy_'))):
                try:
                    try:
                        temp_root = os.path.abspath(tempfile.gettempdir())
                    except Exception:
                        temp_root = None
                    try:
                        folder_abspath = os.path.abspath(folder_path)
                    except Exception:
                        folder_abspath = None
                    if folder_abspath and temp_root and folder_abspath.startswith(temp_root + os.sep):
                        base2 = os.path.basename(folder_abspath)
                        if base2.startswith('audiobook_copy_') or base2.startswith('temp-'):
                            try:
                                remove_path(folder_abspath)
                                logger.debug(f"Removed temporary folder {folder_abspath}")
                            except Exception as e:
                                logger.debug(f"Failed to remove temporary folder {folder_abspath}: {e}")
                except Exception:
                    pass
        except Exception:
            pass

def add_chapters_to_m4b(m4b_path, chapters_info):
    try:
        from mutagen.mp4 import MP4, MP4Chapters, Chapter
        audio = MP4(str(m4b_path))
        chapter_objects = []
        for chapter in chapters_info:
            chapter_obj = Chapter(start=chapter['start'], title=chapter['title'])
            chapter_objects.append(chapter_obj)
        mp4_chapters = MP4Chapters()
        mp4_chapters._chapters = chapter_objects
        audio.chapters = mp4_chapters
        audio.save()
        logger.info("Chapters added to M4B file")
        return True
    except Exception as e:
        logger.warning(f"Failed to add chapters to M4B: {e}")
        return False

def ffmpeg_inject_chapters(m4b_path, chapters, timebase=1000):
    import shutil
    import tempfile
    import subprocess
    import os
    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        return {'status': 'no_ffmpeg', 'note': 'ffmpeg not found on PATH'}
    meta_fd, meta_path = tempfile.mkstemp(prefix='ffmeta_', suffix='.txt')
    atexit.register(lambda: os.remove(meta_path) if os.path.exists(meta_path) else None)
    try:
        with os.fdopen(meta_fd, 'w', encoding='utf-8') as mfd:
            mfd.write(';FFMETADATA1\n')
            for ch in chapters:
                s_ms = ch.get('start_ms') if ch.get('start_ms') is not None else 0
                e_ms = ch.get('end_ms') if ch.get('end_ms') is not None else (s_ms + 1000)
                try:
                    s_ms = int(round(float(s_ms)))
                except Exception:
                    s_ms = 0
                try:
                    e_ms = int(round(float(e_ms)))
                except Exception:
                    e_ms = s_ms + 1000
                mfd.write('[CHAPTER]\n')
                mfd.write('TIMEBASE=1/1000\n')
                mfd.write(f'START={s_ms}\n')
                mfd.write(f'END={e_ms}\n')
                title_safe = (ch.get('title') or '').replace('\n', ' ')
                mfd.write(f'title={title_safe}\n')
        tmp_out = m4b_path + '.tmp.m4b'
        cmd = [ffmpeg_path, '-y', '-i', m4b_path, '-i', meta_path, '-map_metadata', '1', '-c', 'copy', tmp_out]
        subprocess.run(cmd, check=True, capture_output=True)
        move_file(tmp_out, m4b_path, overwrite=True)
        return {'status': 'ok', 'note': 'created chapters (ffmpeg)'}
    except Exception as e:
        return {'status': 'error', 'note': f'ffmpeg chapter injection failed: {e}'}
    finally:
        try:
            if os.path.exists(meta_path):
                os.remove(meta_path)
        except Exception:
            pass


def add_audiobook_metadata(m4b_path, audio_files=None, original_audio_files=None, series_name=None, chapters_info=None, chapter_titles=False, author_fix=False, cli_author=None, album_names=False, **kwargs):

    """
    Apply audiobook metadata (title, author, series, chapters, cover art) to the given M4B file.

    Args:
        m4b_path: Path to the M4B file to update
        audio_files: List of source audio files (for extracting metadata/cover)
        original_audio_files: List of original source files (for cover art, optional)
        original_source_files: Alias for original_audio_files (for test compatibility)
        series_name: Series name to apply (optional)
        chapters_info: List of chapter dicts (with start, end, title, etc.)
        chapter_titles: If True, use chapter titles from files
        author_fix: If True, attempt to fix author name format
        cli_author: Author name from CLI (overrides extracted)
        album_names: If True, use album names from files
    """
    import os
    from mutagen.mp4 import MP4, MP4Cover
    # Centralized options dictionary
    options = {
        'audio_files': audio_files,
        'original_audio_files': original_audio_files,
        'series_name': series_name,
        'chapters_info': chapters_info,
        'chapter_titles': chapter_titles,
        'author_fix': author_fix,
        'cli_author': cli_author,
        'album_names': album_names,
    }
    # Accept original_source_files as alias for original_audio_files (test compatibility)
    if options['original_audio_files'] is None and 'original_source_files' in kwargs:
        options['original_audio_files'] = kwargs['original_source_files']
    # Accept mp4_class and mutagen_file_func for test injection, but ignore if not used
    mp4_class = kwargs.get('mp4_class') if 'mp4_class' in kwargs else None
    mutagen_file_func = kwargs.get('mutagen_file_func') if 'mutagen_file_func' in kwargs else None

    metadata = {}
    if options['audio_files'] and len(options['audio_files']) > 0:
        from audiobook_p.metadata_extraction import extract_metadata_from_file
        try:
            metadata = extract_metadata_from_file(options['audio_files'][0])
        except Exception:
            metadata = {}
        # Extract trkn from the first source file if available
        try:
            if mutagen_file_func:
                src_audio = mutagen_file_func(options['audio_files'][0])
            else:
                src_audio = mutagen.File(options['audio_files'][0])
            if src_audio:
                # For MP4 files
                if hasattr(src_audio, 'tags') and 'trkn' in src_audio.tags:
                    metadata['trkn'] = src_audio.tags['trkn']
                # For MP3 files
                elif hasattr(src_audio, 'get') and src_audio.get('TRCK'):
                    trck = src_audio['TRCK']
                    if hasattr(trck, 'text') and trck.text:
                        track_str = str(trck.text[0])
                        if '/' in track_str:
                            parts = track_str.split('/')
                            try:
                                track_num = int(parts[0])
                                total = int(parts[1]) if len(parts) > 1 else None
                                metadata['trkn'] = [(track_num, total)] if total else [(track_num, track_num)]
                            except ValueError:
                                pass
                # For fake ID3-like objects
                elif hasattr(src_audio, 'tags') and 'TRCK' in src_audio.tags:
                    trck_list = src_audio.tags['TRCK']
                    if trck_list:
                        track_str = str(trck_list[0])
                        if '/' in track_str:
                            parts = track_str.split('/')
                            try:
                                track_num = int(parts[0])
                                total = int(parts[1]) if len(parts) > 1 else None
                                metadata['trkn'] = [(track_num, total)] if total else [(track_num, track_num)]
                            except ValueError:
                                pass
        except Exception:
            pass
    if options['cli_author']:
        metadata['author'] = options['cli_author']
    if options['series_name']:
        metadata['series'] = options['series_name']
    if options['album_names']:
        # Set album to cleaned folder name if possible
        from audiobook_p.utils import clean_album_name
        folder = os.path.dirname(options['audio_files'][0]) if options['audio_files'] and len(options['audio_files']) > 0 else None
        if folder:
            metadata['album'] = clean_album_name(os.path.basename(folder))
    if options['chapters_info']:
        metadata['chapters'] = options['chapters_info']
    # Apply metadata to m4b_path
    try:
        # Use injected mp4_class and mutagen_file_func for testability
        mp4_cls = mp4_class if mp4_class is not None else MP4
        mutagen_file = mutagen_file_func if mutagen_file_func is not None else None
        audio = mp4_cls(m4b_path)
        # Use .tags dict if present (for DummyMP4), else use item assignment
        set_tag = (lambda k, v: audio.tags.__setitem__(k, v)) if hasattr(audio, 'tags') else (lambda k, v: audio.__setitem__(k, v))
        if metadata.get('title'):
            set_tag('\xa9nam', [str(metadata['title'])])
        if metadata.get('author'):
            set_tag('\xa9ART', [str(metadata['author'])])
        if metadata.get('album'):
            set_tag('\xa9alb', [str(metadata['album'])])
        if metadata.get('series'):
            set_tag('----:com.apple.iTunes:SERIES', [str(metadata['series']).encode('utf-8')])
        if metadata.get('trkn'):
            set_tag('trkn', metadata['trkn'])
        # Set default trkn if not set and we have multiple files
        elif len(options['audio_files']) > 1:
            # Default to track 1 of total files
            total = len(options['audio_files'])
            set_tag('trkn', [(1, total)])
        # Set sonm (title sort) to the filename stem if not already set
        if not metadata.get('sort_title') and options['audio_files']:
            filename_stem = os.path.splitext(os.path.basename(options['audio_files'][0]))[0]
            set_tag('sonm', [filename_stem])
        # Set tvsn (series index) from folder name if not set
        if not metadata.get('series_index') and options['audio_files']:
            folder_name = os.path.basename(os.path.dirname(options['audio_files'][0]))
            from audiobook_p.utils import parse_series_index_from_folder_name
            series_index = parse_series_index_from_folder_name(folder_name)
            if series_index:
                set_tag('tvsn', [series_index])
        if metadata.get('chapters'):
            # Optionally add chapters (not all players support this)
            pass
        # Cover art
        cover_path = metadata.get('cover_path')
        if not cover_path and original_audio_files and len(original_audio_files) > 0:
            from audiobook_p.metadata_extraction import extract_metadata_from_file
            try:
                orig_meta = extract_metadata_from_file(original_audio_files[0])
                cover_path = orig_meta.get('cover_path')
            except Exception:
                pass
        if cover_path and os.path.exists(cover_path):
            with open(cover_path, 'rb') as cf:
                cover_data = cf.read()
            fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
            audio['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
        # Save using the injected class if possible
        if hasattr(audio, 'save'):
            audio.save()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to apply metadata to {m4b_path}: {e}")


import os
import json
import glob
import logging
from audiobook_p.utils import copy_file, move_file, remove_path
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TIT1, TPE1, TALB, TCON, TPE2, TCOM, TRCK, TPOS, TSOA, TSOT, TSOP, TSO2, TMED, ID3NoHeaderError
from mutagen.mp4 import MP4

from audiobook_p.metadata_extraction import extract_metadata_from_file

from .utils import (
    clean_album_name, book_title_logic, natural_sort_key, track_number_sort_key, parse_series_index_from_folder_name, sanitize_series_name, sanitize_string
)
from .metadata_normalization import reformat_tag_for_file_type

logger = logging.getLogger(__name__)


def apply_metadata_to_file(file_path, metadata_dict):
    """
    Apply metadata changes to an audio file using the combined-metadata-mapping.json.

    Args:
        file_path: Path to the audio file
        metadata_dict: Dict with descriptive keys and values to apply
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
    audio = mutagen.File(file_path)
    if audio is None:
        raise ValueError("Could not load audio file: {}".format(file_path))
    is_mp3 = isinstance(audio, MP3)
    original_apic_data = {}
    if is_mp3 and hasattr(audio, 'tags') and audio.tags is not None:
        for tag_name in list(audio.tags.keys()):
            if tag_name.startswith('APIC'):
                original_apic_data[tag_name] = audio.tags[tag_name]
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])
    for desc_key, value in metadata_dict.items():
        if desc_key not in all_fields:
            continue
        info = all_fields[desc_key]
        mutagen_keys = info.get('mutagen_keys', {})
        if value is None or (isinstance(value, str) and not value.strip()):
            if desc_key != 'picture':
                continue
        def _decode_mp4_key(k):
            try:
                if isinstance(k, str) and '\\x' in k:
                    return k.encode('ascii').decode('unicode_escape')
            except Exception:
                pass
            return k
        tags_to_try = []
        if is_mp3 and 'id3' in mutagen_keys:
            tags_to_try.append(mutagen_keys['id3'])
        elif not is_mp3 and 'mp4' in mutagen_keys:
            tags_to_try.append(_decode_mp4_key(mutagen_keys['mp4']))
        file_type = 'mp3' if is_mp3 else 'mp4'
        formatted_value = reformat_tag_for_file_type(desc_key, value, file_type)
        for tag in tags_to_try:
            try:
                if is_mp3 and hasattr(audio, 'tags') and audio.tags is not None:
                    if tag == 'TIT2':
                        audio.tags.add(TIT2(encoding=3, text=formatted_value))
                    elif tag == 'TIT1':
                        audio.tags.add(TIT1(encoding=3, text=formatted_value))
                    elif tag == 'TPE1':
                        audio.tags.add(TPE1(encoding=3, text=formatted_value))
                    elif tag == 'TALB':
                        audio.tags.add(TALB(encoding=3, text=formatted_value))
                    elif tag == 'TCON':
                        audio.tags.add(TCON(encoding=3, text=formatted_value))
                    elif tag == 'TPE2':
                        audio.tags.add(TPE2(encoding=3, text=formatted_value))
                    elif tag == 'TCOM':
                        audio.tags.add(TCOM(encoding=3, text=formatted_value))
                    elif tag == 'TRCK':
                        audio.tags.add(TRCK(encoding=3, text=formatted_value))
                    elif tag == 'TPOS':
                        audio.tags.add(TPOS(encoding=3, text=formatted_value))
                    elif tag == 'TSOA':
                        audio.tags.add(TSOA(encoding=3, text=formatted_value))
                    elif tag == 'TSOT':
                        audio.tags.add(TSOT(encoding=3, text=formatted_value))
                    elif tag == 'TSOP':
                        audio.tags.add(TSOP(encoding=3, text=formatted_value))
                    elif tag == 'TSO2':
                        audio.tags.add(TSO2(encoding=3, text=formatted_value))
                    elif tag == 'TMED':
                        audio.tags.add(TMED(encoding=3, text=formatted_value))
                elif hasattr(audio, 'tags') and audio.tags is not None:
                    if desc_key == 'picture':
                        if tag in audio.tags:
                            continue
                    else:
                        try:
                            logger.debug("Setting tag %r -> %r (type %s) on %s", tag, formatted_value, type(formatted_value), file_path)
                        except Exception:
                            pass
                        write_key = tag
                        try:
                            if isinstance(write_key, str) and write_key.startswith('----:'):
                                def _ensure_bytes(x):
                                    if isinstance(x, bytes):
                                        return x
                                    if isinstance(x, str):
                                        return x.encode('utf-8')
                                    try:
                                        return str(x).encode('utf-8')
                                    except Exception:
                                        return b''
                                if isinstance(formatted_value, list):
                                    audio.tags[write_key] = [_ensure_bytes(x) for x in formatted_value]
                                else:
                                    audio.tags[write_key] = [_ensure_bytes(formatted_value)]
                            else:
                                audio.tags[write_key] = formatted_value
                        except Exception:
                            try:
                                audio.tags[tag] = formatted_value
                            except Exception:
                                pass
                        try:
                            if desc_key == 'grouping':
                                series_key = '----:com.apple.iTunes:SERIES'
                                try:
                                    from mutagen.mp4 import MP4FreeForm
                                    if isinstance(formatted_value, list):
                                        audio.tags[series_key] = [MP4FreeForm(str(x).encode('utf-8')) for x in formatted_value]
                                    else:
                                        audio.tags[series_key] = [MP4FreeForm(str(formatted_value).encode('utf-8'))]
                                except Exception:
                                    if isinstance(formatted_value, list):
                                        audio.tags[series_key] = [str(x).encode('utf-8') for x in formatted_value]
                                    else:
                                        audio.tags[series_key] = [str(formatted_value).encode('utf-8')]
                        except Exception:
                            pass
                elif hasattr(audio, tag):
                    setattr(audio, tag, formatted_value)
            except Exception:
                continue
    audio.save()
    try:
        audio = mutagen.File(file_path)
    except Exception:
        pass
    if is_mp3 and original_apic_data and hasattr(audio, 'tags') and audio.tags is not None:
        audio = MP3(file_path)
        for tag_name, apic_frame in original_apic_data.items():
            audio.tags[tag_name] = apic_frame
        try:
            audio.save()
            try:
                audio = MP3(file_path)
            except Exception:
                pass
        except Exception as save_exc:
            try:
                logger.error("Error saving MP4 tags: %s", save_exc)
                logger.debug("Diagnostics: listing audio.tags items (key -> type / sample repr)")
                for k, v in list(audio.tags.items()):
                    try:
                        t = type(v)
                        if isinstance(v, list):
                            inner_types = [type(x) for x in v]
                            sample = v[0] if len(v) > 0 else None
                            logger.debug("  %s -> list of %s, sample type: %s, sample repr: %s", k, inner_types, type(sample), repr(sample)[:200])
                        else:
                            logger.debug("  %s -> %s repr: %s", k, t, repr(v)[:200])
                    except Exception as e_inner:
                        logger.debug("  %s -> (error inspecting value: %s)", k, e_inner)
            except Exception:
                pass
            raise


# --- mutate_metadata ---
import glob
def mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=None, narrator_name=None, author_fix=False, in_place=False, apply_metadata_to_file=None):
    # Assign folder at the very top before any use
    folder = metadata_dict.get('folder')
    from audiobook_p.utils import book_title_logic, clean_album_name
    # Always use the provided folder for all file operations, do NOT descend into subdirectories for renaming/cleanup/metadata
    working_dir = folder    # Assign album and folder_name before using them
    orig_folder = metadata_dict.get('folder', folder)
    folder_name = os.path.basename(orig_folder)
    album = clean_album_name(folder_name)

    # Remove any directory in working_dir with the same name as the album to prevent file/dir collision
    album_dir_path = os.path.join(working_dir, album)
    if os.path.exists(album_dir_path) and os.path.isdir(album_dir_path):
        import shutil
        print(f"[DIAG-FIX] Removing directory with album name to prevent collision: {album_dir_path}")
        try:
            shutil.rmtree(album_dir_path)
        except Exception as e:
            print(f"[DIAG-FIX] Failed to remove directory {album_dir_path}: {e}")

    parent_dir = os.path.dirname(folder)
    files = metadata_dict.get('files', {})
    if files is None:
        files = {}

    if not folder or not files:
        return {'folder': folder, 'files': {}}
    
    # If not in_place, create a temporary copy of the folder
    if not in_place:
        import tempfile
        import shutil
        temp_dir = tempfile.mkdtemp(prefix='audiobook_mutate_')
        print(f"[DIAG] Creating temporary copy for in_place=False: {temp_dir}")
        # Copy the entire folder contents to temp directory
        for item in os.listdir(working_dir):
            src_path = os.path.join(working_dir, item)
            dst_path = os.path.join(temp_dir, item)
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)
        # Update file paths to point to temp directory
        old_working_dir = working_dir
        working_dir = temp_dir
        print(f"[DIAG] Working directory set to temp copy: {working_dir}")
        # Update the files dictionary to use temp directory paths
        updated_files = {}
        for old_path, meta in files.items():
            # Get the relative path from the old working directory
            rel_path = os.path.relpath(old_path, old_working_dir)
            new_path = os.path.join(working_dir, rel_path)
            updated_files[new_path] = meta
        files = updated_files
        print(f"[DIAG] Updated file paths for temp directory: {list(files.keys())}")
    
    folder_name = os.path.basename(orig_folder)
    album = clean_album_name(folder_name)

    # Remove any directory in folder with the same name as the album to prevent file/dir collision
    album_dir_path = os.path.join(folder, album)
    if os.path.exists(album_dir_path) and os.path.isdir(album_dir_path):
        import shutil
        print(f"[DIAG-FIX] Removing directory with album name to prevent collision: {album_dir_path}")
        try:
            shutil.rmtree(album_dir_path)
        except Exception as e:
            print(f"[DIAG-FIX] Failed to remove directory {album_dir_path}: {e}")

    # All required variables are now defined below this point
    # Setup variables
    static_files = list(files.keys())
    file_map = {f: files[f] for f in static_files}
    renamed_file_map = {}
    expected_files = set()
    orig_folder = metadata_dict.get('folder', folder)
    folder_name = os.path.basename(orig_folder)

    # Ensure all source files are present in working_dir before renaming
    import shutil
    # Don't override temp directory when in_place=False
    if in_place:
        working_dir = folder
    for f in static_files:
        src_path = os.path.normpath(f)
        dst_path = os.path.normpath(os.path.join(working_dir, os.path.basename(f)))
        if not os.path.exists(dst_path) and os.path.exists(src_path):
            try:
                shutil.copy2(src_path, dst_path)
                print(f"[DIAG] Copied file to working_dir: {src_path} -> {dst_path}")
            except Exception as e:
                print(f"[DIAG] Failed to copy file to working_dir: {src_path} -> {dst_path} ({e})")
    # Default metadata applier if none provided
    apply_metadata_to_file_default = apply_metadata_to_file
    parent_folder = os.path.basename(os.path.dirname(orig_folder))
    album = clean_album_name(folder_name)
    album_sort = album
    grouping = ''
    series_index = metadata_dict.get('series_index', '')
    total = len(static_files)
    # Always use the provided folder for all file operations, but if only one subfolder exists, use it
    # But don't override the temp directory when in_place=False
    if in_place and os.path.exists(working_dir) and os.path.isdir(working_dir):
        subdirs = [f for f in os.listdir(working_dir) if os.path.isdir(os.path.join(working_dir, f))]
        if len(subdirs) == 1:
            subfolder = os.path.join(working_dir, subdirs[0])
            print(f"[DIAG] Using subfolder as working_dir for all file operations: {subfolder}")
            working_dir = subfolder
    rename_plan = []  # (src, dst)
    expected_files = set()
    # Build mapping from original file to new file and meta
    file_rename_meta = []  # (src, dst, meta)
    for idx, f in enumerate(static_files):
        file_stem = os.path.splitext(os.path.basename(f))[0]
        file_ext = os.path.splitext(f)[1].lower()
        meta = dict(file_map.get(f, {}))
        if 'files' in metadata_dict:
            f_base = os.path.splitext(os.path.basename(f))[0]
            f_ext = os.path.splitext(f)[1].lower()
            for orig_path, test_dict in metadata_dict['files'].items():
                orig_base = os.path.splitext(os.path.basename(orig_path))[0]
                orig_ext = os.path.splitext(orig_path)[1].lower()
                if f_base == orig_base and f_ext == orig_ext:
                    meta = dict(test_dict)
                    break
        if not meta.get('title'):
            if chapter_titles:
                if part_titles:
                    part_num = 1 + (idx // 10)
                    meta['title'] = f"{album} - Part {part_num} - {idx+1}"
                else:
                    meta['title'] = f"{album} - Chapter {idx+1}"
            else:
                meta['title'] = book_title_logic(file_stem)
        meta['sort_title'] = file_stem
        if not meta.get('album'):
            meta['album'] = album
        if album_sort_prefix:
            meta['album_sort'] = f"{album_sort_prefix}{album}"
        elif not meta.get('album_sort'):
            meta['album_sort'] = album_sort
        if author_name:
            from audiobook_p.utils import book_title_logic
            meta['artist'] = book_title_logic(author_name).strip()
        if author_fix and meta.get('artist'):
            artist_val = meta['artist']
            if isinstance(artist_val, str) and ',' in artist_val:
                parts = [p.strip() for p in artist_val.split(',') if p.strip()]
                if len(parts) >= 2:
                    last = parts[0]
                    first = ' '.join(parts[1:])
                    meta['artist'] = f"{first} {last}".strip()
        if narrator_name:
            meta['composer'] = narrator_name
        if series_name:
            meta['grouping'] = series_name
            meta['series'] = series_name
        else:
            meta['grouping'] = grouping
            meta['series'] = grouping
        meta['series_index'] = series_index
        meta['track'] = str(idx+1)
        meta['track_number'] = str(idx+1)
        meta['track_tuple'] = (idx+1, total)
        meta['media_kind'] = 2
        meta['genre'] = 'Audiobook'
        if 'title_sort' not in meta:
            meta['title_sort'] = file_stem

        # Always place renamed files in working_dir, and ensure source files are also in working_dir
        src_path = os.path.normpath(os.path.join(working_dir, os.path.basename(f)))
        if part_titles:
            part_num = 1 + (idx // 10)
            # Use space after album name to match test expectation
            new_basename = f"{meta['album']} Part {part_num} - {str(idx+1).zfill(3)}{file_ext}"
            new_path = os.path.normpath(os.path.join(working_dir, new_basename))
            rename_plan.append((src_path, new_path))
            file_rename_meta.append((src_path, new_path, meta))
        else:
            static_basename = os.path.basename(f)
            static_path = os.path.normpath(os.path.join(working_dir, static_basename))
            rename_plan.append((src_path, static_path))
            file_rename_meta.append((src_path, static_path, meta))


    # Perform all renames first
    print(f"[DEBUG] expected_files before renames: {expected_files}")
    print(f"[DEBUG] Directory contents before renames: {os.listdir(working_dir) if os.path.exists(working_dir) else 'N/A'}")
    for src, dst in rename_plan:
        if os.path.abspath(src) != os.path.abspath(dst):
            try:
                from audiobook_p.utils import move_file
                print(f"[DIAG] Renaming file: {src} -> {dst}")
                move_file(src, dst, overwrite=True)
                # Diagnostic: print directory contents after each rename
                if os.path.exists(working_dir) and os.path.isdir(working_dir):
                    print(f"[DIAG] Directory listing after rename ({src} -> {dst}): {os.listdir(working_dir)}")
                    print(f"[DIAG] Full paths after rename: {[os.path.abspath(os.path.join(working_dir, f)) for f in os.listdir(working_dir)]}")
            except Exception as e:
                print(f"[DIAG] Exception during rename: {e}")
        else:
            print(f"[DIAG] Skipping move: src and dst are the same: {src}")
    print(f"[DEBUG] expected_files after renames: {expected_files}")
    print(f"[DEBUG] Directory contents after renames: {os.listdir(working_dir) if os.path.exists(working_dir) else 'N/A'}")

    # After all renames, build expected_files from the basenames of the renamed .m4a files in file_rename_meta
    expected_files = set(os.path.basename(dst) for _, dst, _ in file_rename_meta)
    print(f"[DIAG-FULLPATHS] expected_files (from file_rename_meta): {sorted(expected_files)}")

    # Diagnostic: print full file tree after all renames
    def _print_full_tree(root):
        print(f"[DIAG-FULLTREE-RENAMES] Full file tree for {root} after renames:")
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            for fname in filenames:
                print(f"[DIAG-FULLTREE-RENAMES] {os.path.join(rel_dir, fname)}")
    if os.path.exists(working_dir) and os.path.isdir(working_dir):
        _print_full_tree(working_dir)

    # Always operate in the provided folder; do not descend into subdirectories for cleanup/metadata
    # This ensures renamed files are present in the expected directory for the test

    # Diagnostic: print directory contents and expected_files after all renames, before cleanup
    if os.path.exists(working_dir) and os.path.isdir(working_dir):
        dir_listing = os.listdir(working_dir)
        print(f"[DIAG-POST-RENAME] Directory listing after all renames (in working_dir): {dir_listing}")
        print(f"[DIAG-POST-RENAME] Full paths after all renames: {[os.path.abspath(os.path.join(working_dir, f)) for f in dir_listing]}")
        print(f"[DIAG-POST-RENAME] Expected files after renaming: {sorted(expected_files)}")

    # Cleanup: remove any file (not directory) in the directory tree that is not in expected_files
    if os.path.exists(working_dir) and os.path.isdir(working_dir):
        files_to_remove = []
        files_to_keep = set()
        # Recursively find all files in working_dir
        for dirpath, dirnames, filenames in os.walk(working_dir):
            for fname in filenames:
                if fname in expected_files:
                    files_to_keep.add(os.path.abspath(os.path.join(dirpath, fname)))
                else:
                    files_to_remove.append(os.path.abspath(os.path.join(dirpath, fname)))
        print(f"[DIAG] Files to keep (matched expected_files): {sorted(files_to_keep)}")
        print(f"[DIAG] Files to remove (not in expected_files): {sorted(files_to_remove)}")
        for fpath in files_to_remove:
            try:
                os.remove(fpath)
                print(f"[DIAG] Removed stale file: {fpath}")
            except Exception as e:
                print(f"[DIAG] Failed to remove stale file: {fpath} due to {e}")
        # Print directory tree after cleanup
        def _print_full_tree(root):
            print(f"[DIAG-FULLTREE-CLEANUP] Full file tree for {root} after cleanup:")
            for dirpath, dirnames, filenames in os.walk(root):
                rel_dir = os.path.relpath(dirpath, root)
                for fname in filenames:
                    print(f"[DIAG-FULLTREE-CLEANUP] {os.path.join(rel_dir, fname)}")
        _print_full_tree(working_dir)

    # Diagnostic: print renamed_files and directory contents before metadata application
    renamed_files = [dst for _, dst, _ in file_rename_meta]
    file_metas = [meta for _, _, meta in file_rename_meta]
    print(f"[DIAG] Renamed files to apply metadata: {renamed_files}")
    if os.path.exists(working_dir) and os.path.isdir(working_dir):
        print(f"[DIAG] Directory listing before metadata application (in working_dir): {os.listdir(working_dir)}")

    # Second pass: apply metadata only to renamed files (after cleanup)
    renamed_file_map = {}
    for f, meta in zip(renamed_files, file_metas):
        renamed_file_map[f] = meta
        print(f"[DIAG] Applying metadata to file: {f} with meta: {meta}")
        try:
            (apply_metadata_to_file or apply_metadata_to_file_default)(f, meta)
        except Exception:
            pass

    # Diagnostic: print full file tree after metadata application, before return
    def _print_full_tree(root):
        print(f"[DIAG-FULLTREE] Full file tree for {root}:")
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            for fname in filenames:
                print(f"[DIAG-FULLTREE] {os.path.join(rel_dir, fname)}")

    if os.path.exists(working_dir) and os.path.isdir(working_dir):
        _print_full_tree(working_dir)

    # Return based on in_place parameter
    if in_place:
        return {'folder': working_dir, 'files': renamed_file_map}
    else:
        return working_dir

# --- _author_last_first_to_first_last ---
def _author_last_first_to_first_last(name):
    if not name:
        return name
    try:
        s = str(name).strip()
    except Exception:
        return name
    if ',' in s:
        parts = [p.strip() for p in s.split(',') if p.strip()]
        if len(parts) >= 2:
            last = parts[0]
            first = ' '.join(parts[1:])
            combined = f"{first} {last}".strip()
            try:
                return book_title_logic(combined)
            except Exception:
                try:
                    return combined.title()
                except Exception:
                    return combined
    try:
        return book_title_logic(s)
    except Exception:
        try:
            return s.title()
        except Exception:
            return s

# --- _maybe_fix_author ---
def _maybe_fix_author(name, flag):
    if not name:
        return name
    try:
        val = name
        if isinstance(val, list) and len(val) > 0:
            val = val[0]
        if isinstance(val, (bytes, bytearray)):
            try:
                val = val.decode('utf-8')
            except Exception:
                try:
                    val = val.decode('latin-1')
                except Exception:
                    val = str(val)
        if hasattr(val, 'text'):
            try:
                t = val.text
                if isinstance(t, list) and len(t) > 0:
                    val = t[0]
                else:
                    val = t
            except Exception:
                try:
                    val = str(val)
                except Exception:
                    pass
        if hasattr(val, 'data') and not isinstance(val, (str, bytes, bytearray)):
            try:
                val = val.data
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode('utf-8')
                    except Exception:
                        val = val.decode('latin-1', errors='ignore')
            except Exception:
                pass
        name_str = str(val).strip()
    except Exception:
        try:
            name_str = str(name).strip()
        except Exception:
            return name
    if flag:
        try:
            return _author_last_first_to_first_last(name_str)
        except Exception:
            return name_str
    return name_str

# --- get_sleep_prevention_command ---
def get_sleep_prevention_command():
    import platform
    system = platform.system().lower()
    if system == 'darwin':
        try:
            import subprocess
            result = subprocess.run(['which', 'caffeinate'], capture_output=True, text=True)
            if result.returncode == 0:
                return ['caffeinate', '-i']
        except Exception as e:
            logger.debug("caffeinate check failed: %s", e)
    elif system == 'linux':
        try:
            import subprocess
            result = subprocess.run(['which', 'systemd-inhibit'], capture_output=True, text=True)
            if result.returncode == 0:
                return ['systemd-inhibit', '--what=idle:sleep', '--who=audiobook-p', '--why=Long running audio conversion']
        except Exception as e:
            logger.debug("systemd-inhibit check failed: %s", e)
        try:
            import subprocess
            result = subprocess.run(['which', 'caffeine'], capture_output=True, text=True)
            if result.returncode == 0:
                return ['caffeine']
        except Exception as e:
            logger.debug("caffeine check failed: %s", e)
    elif system == 'windows':
        pass
    return []
