#!/usr/bin/env python3
import shutil
import subprocess
import tempfile
from pathlib import Path
from mutagen.mp4 import MP4
from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, convert_folder_to_m4b, clean_album_name


def write_short_mp3(path, duration=0.1):
    cmd = ['ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', str(duration), '-q:a', '9', path]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def show_tags(m4b_path):
    mp4 = MP4(m4b_path)
    print(f"Tags for {m4b_path}:")
    if mp4.tags:
        for k, v in mp4.tags.items():
            print(f"  {k}: {v}")
    else:
        print("  <no tags>")


def run_novel(tmp_dir):
    src = tmp_dir / 'My Novel'
    src.mkdir()
    a = src / '01 - track.mp3'
    b = src / '02 - track.mp3'
    write_short_mp3(str(a))
    write_short_mp3(str(b))
    metadata = extract_metadata_from_folder(str(src), 'novel')
    mutated = mutate_metadata(metadata, in_place=False)
    out = tmp_dir / 'novel_out.m4b'
    convert_folder_to_m4b(mutated, str(out), chapter_titles=False, album_names=True, original_source_path=str(src))
    show_tags(str(out))
    shutil.rmtree(mutated, ignore_errors=True)


def run_series(tmp_dir):
    parent = tmp_dir / 'Series Parent'
    child = parent / '01 - Child Book'
    child.mkdir(parents=True, exist_ok=True)
    a = child / '01 - track.mp3'
    write_short_mp3(str(a))
    metadata = extract_metadata_from_folder(str(child), 'series')
    mutated = mutate_metadata(metadata, in_place=False, series_name=None)
    out = tmp_dir / 'series_out.m4b'
    convert_folder_to_m4b(mutated, str(out), chapter_titles=False, album_names=True, original_source_path=str(child))
    show_tags(str(out))
    shutil.rmtree(mutated, ignore_errors=True)


def main():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        print('\n--- Novel run ---')
        run_novel(td)
        print('\n--- Series run ---')
        run_series(td)

if __name__ == '__main__':
    main()
