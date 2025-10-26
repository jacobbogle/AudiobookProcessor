import sys
import os
from mutagen.mp4 import MP4, MP4Cover

def clean_folder_name(folder):
    # Implement your folder cleaning/sanitizing logic here
    return folder.replace('_', ' ').replace('-', ' ').strip().title()

def get_folder_name_from_path(path):
    return os.path.basename(os.path.dirname(path))

def main(m4b_path):
    import glob
    import json
    import subprocess
    # Step 1: Gather source audio files in the same folder as the M4B
    m4b_dir = os.path.dirname(m4b_path)
    audio_files = sorted(glob.glob(os.path.join(m4b_dir, '*.m4a')) + glob.glob(os.path.join(m4b_dir, '*.mp3')))
    chapters = []
    start = 0
    for f in audio_files:
        # Get duration
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', f
            ], capture_output=True, text=True)
            duration = float(result.stdout.strip())
        except Exception:
            duration = None
        # Get title
        try:
            result = subprocess.run([
                'ffprobe', '-v', 'error', '-show_entries', 'format_tags=title',
                '-of', 'default=noprint_wrappers=1:nokey=1', f
            ], capture_output=True, text=True)
            title = result.stdout.strip() or os.path.basename(f)
        except Exception:
            title = os.path.basename(f)
        end = start + (duration if duration else 0)
        chapters.append({'start': int(start * 1000), 'end': int(end * 1000), 'title': title})
        start = end

    # Step 2: Write ffmetadata file
    ffmeta_path = os.path.join(m4b_dir, 'chapter_metadata.ffmeta')
    with open(ffmeta_path, 'w', encoding='utf-8') as ffmeta:
        ffmeta.write(';FFMETADATA1\n')
        for ch in chapters:
            ffmeta.write('[CHAPTER]\n')
            ffmeta.write('TIMEBASE=1/1000\n')
            ffmeta.write(f'START={ch["start"]}\n')
            ffmeta.write(f'END={ch["end"]}\n')
            ffmeta.write(f'TITLE={ch["title"]}\n')

    # Step 3: Inject chapters and tags using ffmpeg
    output_path = os.path.splitext(m4b_path)[0] + '.chapters.m4b'
    ffmpeg_cmd = [
        'ffmpeg', '-i', m4b_path, '-i', ffmeta_path, '-map_metadata', '1', '-codec', 'copy', output_path, '-y'
    ]
    print('Running:', ' '.join(ffmpeg_cmd))
    subprocess.run(ffmpeg_cmd, check=True)
    print(f'Chapters and tags injected into {output_path}')

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python fix_m4b_tags.py <path_to_m4b>")
        sys.exit(1)
    main(sys.argv[1])
