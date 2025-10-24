#!/usr/bin/env python3
"""
Simple runner to invoke mutate/convert on a folder and print resulting M4B tag values.
Usage (from repo root):
  python3 scripts/run_mutate_convert_inspect.py /path/to/source /path/to/output.m4b

If output path is a directory, the script will place M4B files there (batch-mode behavior).
"""
import sys
import os
import json
from mutagen.mp4 import MP4

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from audiobook_p.main import extract_metadata_from_folder, mutate_metadata, convert_folder_to_m4b, clean_album_name


def print_tags(m4b_path):
    try:
        a = MP4(str(m4b_path))
    except Exception as e:
        print(f"Failed to open {m4b_path}: {e}")
        return
    print(f"Tags for {m4b_path}:")
    for k, v in (a.tags or {}).items():
        print(f"  {k}: {v}")


def process_folder(source, output):
    if not os.path.isdir(source):
        print(f'Source must be a directory: {source}')
        return

    has_subfolders = any(os.path.isdir(os.path.join(source, p)) for p in os.listdir(source))

    if has_subfolders:
        if not os.path.exists(output):
            os.makedirs(output, exist_ok=True)
        for child in sorted(os.listdir(source)):
            child_path = os.path.join(source, child)
            if not os.path.isdir(child_path):
                continue
            child_output = os.path.join(output, child)
            process_folder(child_path, child_output)
    else:
        # Check if has audio files
        has_audio = False
        for ext in ('*.m4a', '*.mp3'):
            import glob as _glob
            if _glob.glob(os.path.join(source, ext)):
                has_audio = True
                break
        if not has_audio:
            print(f"Skipping {source}: no audio files found")
            return
        try:
            meta = extract_metadata_from_folder(source, 'novel')
            mutate_metadata(meta, in_place=True)
            outfile = os.path.join(output, f"{clean_album_name(os.path.basename(source)) or os.path.basename(source)}.m4b")
            convert_folder_to_m4b(source, outfile)
            print_tags(outfile)
        except Exception as e:
            print(f"Error processing {source}: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: run_mutate_convert_inspect.py <source_folder> <output_dir> [--recursive]')
        sys.exit(2)
    source = sys.argv[1]
    output = sys.argv[2]
    recursive = '--recursive' in sys.argv

    if recursive:
        process_folder(source, output)
    else:
        # Original logic for non-recursive
        if not os.path.isdir(source):
            print('Source must be a directory')
            sys.exit(2)

        has_subfolders = any(os.path.isdir(os.path.join(source, p)) for p in os.listdir(source))

        if has_subfolders:
            if not os.path.exists(output):
                os.makedirs(output, exist_ok=True)
            for child in sorted(os.listdir(source)):
                child_path = os.path.join(source, child)
                if not os.path.isdir(child_path):
                    continue
                has_audio = False
                for ext in ('*.m4a', '*.mp3'):
                    import glob as _glob
                    if _glob.glob(os.path.join(child_path, ext)):
                        has_audio = True
                        break
                if not has_audio:
                    print(f"Skipping {child_path}: no audio files found")
                    continue
                try:
                    meta = extract_metadata_from_folder(child_path, 'novel')
                    mutate_metadata(meta, in_place=True)
                    outfile = os.path.join(output, f"{clean_album_name(child) or child}.m4b")
                    convert_folder_to_m4b(child_path, outfile)
                    print_tags(outfile)
                except Exception as e:
                    print(f"Error processing {child_path}: {e}")
        else:
            try:
                meta = extract_metadata_from_folder(source, 'novel')
                mutate_metadata(meta, in_place=True)
                convert_folder_to_m4b(source, output)
                print_tags(output)
            except Exception as e:
                print(f"Error: {e}")
