# This script generates small valid MP3, M4A, and M4B files with metadata for testing.
# It uses ffmpeg to create 1-second silent audio files and sets tags for each format.
import os
import subprocess

test_audio_dir = os.path.join(os.path.dirname(__file__), '..', 'test_audio')
os.makedirs(test_audio_dir, exist_ok=True)

files = [
    ("test_sample.mp3", "mp3"),
    ("test_sample.m4a", "m4a"),
    ("test_sample.m4b", "m4b"),
]

tags = {
    "title": "TestTitle",
    "artist": "TestArtist",
    "album": "TestAlbum",
    "genre": "TestGenre",
    "date": "2025",
    "comment": "TestComment",
}

def make_audio(filename, ext):
    path = os.path.join(test_audio_dir, filename)
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", "1",
        "-metadata", f"title={tags['title']}",
        "-metadata", f"artist={tags['artist']}",
        "-metadata", f"album={tags['album']}",
        "-metadata", f"genre={tags['genre']}",
        "-metadata", f"date={tags['date']}",
        "-metadata", f"comment={tags['comment']}",
        path
    ]
    if ext == "mp3":
        cmd.extend(["-c:a", "libmp3lame"])
    elif ext in ("m4a", "m4b"):
        cmd.extend(["-c:a", "aac"])
    subprocess.run(cmd, check=True)

for fname, ext in files:
    make_audio(fname, ext)

print("Test audio files created in", test_audio_dir)
