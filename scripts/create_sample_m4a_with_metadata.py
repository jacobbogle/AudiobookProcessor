import os
import sys
import shutil
from mutagen.mp4 import MP4, MP4Cover
import subprocess

def create_silent_m4a(output_path, duration=1.0):
    """Create a silent m4a file using ffmpeg."""
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
        '-t', str(duration), '-c:a', 'aac', '-b:a', '64k', output_path
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def copy_m4a_metadata(src_path, dst_path):
    """Copy all tags and cover art from src_path to dst_path."""
    src = MP4(src_path)
    dst = MP4(dst_path)
    # Copy tags
    for k, v in src.tags.items():
        dst.tags[k] = v
    # Copy cover art if present
    if 'covr' in src.tags:
        dst.tags['covr'] = src.tags['covr']
    dst.save()

def main():
    if len(sys.argv) != 3:
        print("Usage: python create_sample_m4a_with_metadata.py <source.m4a> <output.m4a>")
        sys.exit(1)
    src_path = sys.argv[1]
    dst_path = sys.argv[2]
    if not os.path.exists(src_path):
        print(f"Source file does not exist: {src_path}")
        sys.exit(1)
    # Create silent m4a
    create_silent_m4a(dst_path)
    # Copy metadata
    copy_m4a_metadata(src_path, dst_path)
    print(f"Created {dst_path} with metadata from {src_path}")

if __name__ == "__main__":
    main()
