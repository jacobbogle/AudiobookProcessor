import os
import sys
import shutil
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC
import subprocess

def create_silent_mp3(output_path, duration=1.0):
    """Create a silent mp3 file using ffmpeg."""
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono',
        '-t', str(duration), '-q:a', '9', output_path
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def copy_mp3_metadata(src_path, dst_path):
    """Copy all ID3 tags and cover art from src_path to dst_path."""
    src = MP3(src_path)
    dst = MP3(dst_path)
    # Copy all ID3 tags
    if src.tags:
        dst.tags = ID3()
        for tag in src.tags.values():
            dst.tags.add(tag)
        dst.save()

def main():
    if len(sys.argv) != 3:
        print("Usage: python create_sample_mp3_with_metadata.py <source.mp3> <output.mp3>")
        sys.exit(1)
    src_path = sys.argv[1]
    dst_path = sys.argv[2]
    if not os.path.exists(src_path):
        print(f"Source file does not exist: {src_path}")
        sys.exit(1)
    # Create silent mp3
    create_silent_mp3(dst_path)
    # Copy metadata
    copy_mp3_metadata(src_path, dst_path)
    print(f"Created {dst_path} with metadata from {src_path}")

if __name__ == "__main__":
    main()
