#!/usr/bin/env python3
"""
Dump MP4 atoms and freeform keys from an M4B file.
"""

import sys
from mutagen.mp4 import MP4

def dump_file(m4b_path):
    try:
        audio = MP4(m4b_path)
        print(f"Tags for {m4b_path}:")
        if audio.tags:
            for k, v in audio.tags.items():
                print(f"  {k}: {v}")
        else:
            print("  No tags found")
    except Exception as e:
        print(f"Failed to open {m4b_path}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python dump_m4b_tags.py <m4b_file>")
        sys.exit(1)
    dump_file(sys.argv[1])