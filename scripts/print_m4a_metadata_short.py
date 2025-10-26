import sys
from mutagen.mp4 import MP4

def print_short_metadata(m4a_path):
    audio = MP4(m4a_path)
    print(f"Metadata for: {m4a_path}")
    for k, v in audio.tags.items():
        # Shorten long values (e.g., cover art)
        if isinstance(v, list) and len(v) > 0 and hasattr(v[0], '__len__') and not isinstance(v[0], str):
            print(f"{k}: <{len(v[0])} bytes>")
        else:
            val = v[0] if isinstance(v, list) and len(v) == 1 else v
            s = str(val)
            if len(s) > 80:
                s = s[:77] + '...'
            print(f"{k}: {s}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python print_m4a_metadata_short.py <file.m4a>")
        sys.exit(1)
    print_short_metadata(sys.argv[1])
