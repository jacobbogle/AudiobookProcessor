import sys
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC

def print_short_metadata(mp3_path):
    audio = MP3(mp3_path)
    print(f"Metadata for: {mp3_path}")
    if not audio.tags:
        print("No ID3 tags found.")
        return
    for tag in audio.tags.values():
        desc = tag.FrameID if hasattr(tag, 'FrameID') else tag.__class__.__name__
        if isinstance(tag, APIC):
            print(f"{desc}: <{len(tag.data)} bytes> ({tag.mime})")
        else:
            val = str(tag)
            if len(val) > 80:
                val = val[:77] + '...'
            print(f"{desc}: {val}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python print_mp3_metadata_short.py <file.mp3>")
        sys.exit(1)
    print_short_metadata(sys.argv[1])
