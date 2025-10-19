"""
Audiobook Processor - Audio Conversion Operations
"""

import os
import re
import subprocess
import shutil
from pathlib import Path

# Auto-install required packages
try:
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.mp3 import MP3
    from mutagen import File as MutagenFile
except ImportError:
    print("mutagen not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.mp3 import MP3
    from mutagen import File as MutagenFile

try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm


def get_duration_seconds(input_file, ffprobe_path=None):
    """Get duration of audio file in seconds using format-specific parsers.

    Prioritizes format-specific parsers (MP3 for .mp3, MP4 for .m4a/.mp4/.m4b)
    to avoid cross-format parser errors. Falls back to generic mutagen.File,
    then ffprobe, then returns None if all methods fail.
    """
    file_ext = Path(input_file).suffix.lower()

    # Try format-specific parser first
    try:
        if file_ext in ['.m4a', '.mp4', '.m4b']:
            # Use mutagen.mp4 for M4A/MP4 files
            audio = MP4(input_file)
            if audio and hasattr(audio.info, 'length') and audio.info.length:
                return float(audio.info.length)
    except Exception:
        pass

    try:
        if file_ext in ['.mp3']:
            # Use mutagen.mp3 for MP3 files
            audio = MP3(input_file)
            if audio and hasattr(audio.info, 'length') and audio.info.length:
                return float(audio.info.length)
    except Exception:
        pass

    # Fall back to generic mutagen parser
    try:
        audio = MutagenFile(input_file)
        if audio and hasattr(audio.info, 'length') and audio.info.length:
            return float(audio.info.length)
    except Exception:
        pass

    # Last resort: try ffprobe
    try:
        probe = ffprobe_path or shutil.which('ffprobe')
        if probe:
            cmd = [probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', input_file]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            out = res.stdout.strip()
            if out:
                return float(out)
    except Exception:
        pass

    return None


def convert_to_m4a(input_file, output_file, bitrate='128k', metadata=None, ffmpeg_path='ffmpeg'):
    """Convert MP3 to M4A with metadata preservation."""
    if metadata is None:
        metadata = {}

    # Try to extract cover and chapters if not provided
    try:
        if not metadata.get('cover_path') or not metadata.get('chapters'):
            from .metadata import extract_all_metadata
            src_meta = extract_all_metadata(input_file)
            if src_meta and src_meta.get('cover_path') and not metadata.get('cover_path'):
                metadata['cover_path'] = src_meta.get('cover_path')
            if src_meta and src_meta.get('chapters') and not metadata.get('chapters'):
                metadata['chapters'] = src_meta.get('chapters')
    except Exception:
        pass

    cmd = [ffmpeg_path, '-y', '-i', input_file]
    input_index = 1
    cover = metadata.get('cover_path')
    md_file = None

    if cover:
        cmd += ['-i', cover]
        input_index += 1

    from .metadata import write_ffmetadata
    md_file = write_ffmetadata(metadata, output_file) if metadata.get('chapters') else None
    if md_file:
        cmd += ['-f', 'ffmetadata', '-i', md_file]
        md_input_index = input_index
        input_index += 1
    else:
        md_input_index = None

    if cover and md_file:
        cmd += [
            '-map', '0:a',
            '-map', '1',
            '-map_metadata', str(md_input_index),
            '-c:a', 'aac', '-b:a', bitrate,
            '-c:v', 'mjpeg',
            '-metadata:s:v', 'title=Cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-disposition:v:0', 'attached_pic'
        ]
    elif cover:
        cmd += [
            '-map', '0:a',
            '-map', '1',
            '-c:a', 'aac', '-b:a', bitrate,
            '-c:v', 'mjpeg',
            '-metadata:s:v', 'title=Cover',
            '-metadata:s:v', 'comment=Cover (front)',
            '-disposition:v:0', 'attached_pic'
        ]
    elif md_file:
        cmd += [
            '-map', '0:a',
            '-map_metadata', str(md_input_index),
            '-c:a', 'aac', '-b:a', bitrate,
            '-vn'
        ]
    else:
        cmd += ['-c:a', 'aac', '-b:a', bitrate, '-vn']

    for field, tag in (('title', 'title'), ('artist', 'artist'), ('album', 'album'), ('date', 'date')):
        val = metadata.get(field)
        if val:
            cmd += ['-metadata', f'{tag}={val}']

    cmd += ['-f', 'mp4', output_file]

    print('Running ffmpeg to convert to m4a...')
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, universal_newlines=True)
    pbar = None
    total_sec = None

    try:
        if metadata.get('duration_ms'):
            total_sec = metadata.get('duration_ms') / 1000.0
        else:
            total_sec = get_duration_seconds(input_file)
    except Exception:
        total_sec = None

    if total_sec:
        try:
            pbar = tqdm(total=total_sec, unit='s', desc='ffmpeg')
        except Exception:
            pbar = None

    time_re = re.compile(r'time=(\d+):(\d+):(\d+\.\d+)')
    last_pos = 0.0
    while True:
        line = proc.stderr.readline()
        if not line:
            break
        line = line.strip()
        m = time_re.search(line)
        if m and pbar:
            h = int(m.group(1))
            mm = int(m.group(2))
            ss = float(m.group(3))
            cur = h*3600 + mm*60 + ss
            try:
                delta = max(0.0, cur - last_pos)
                if delta > 0:
                    pbar.update(delta)
                    last_pos = cur
            except Exception:
                pass

    ret = proc.wait()
    if pbar:
        pbar.close()

    success = (ret == 0)

    if success:
        try:
            mp4 = MP4(output_file)
            if metadata.get('title'):
                mp4['\xa9nam'] = [str(metadata.get('title'))]
            if metadata.get('artist'):
                mp4['\xa9ART'] = [str(metadata.get('artist'))]
            if metadata.get('album'):
                mp4['\xa9alb'] = [str(metadata.get('album'))]
            if metadata.get('sort_title'):
                mp4['sonm'] = [str(metadata.get('sort_title'))]  # Sort Title

            # Add track number if available
            if metadata.get('track_number'):
                try:
                    track_num = int(metadata['track_number'])
                    total_tracks = int(metadata.get('total_tracks', 0))
                    if total_tracks > 0:
                        mp4['trkn'] = [(track_num, total_tracks)]
                    else:
                        mp4['trkn'] = [(track_num, 0)]
                except ValueError:
                    pass

            mp4['\xa9gen'] = [metadata.get('genre') or 'Audiobook']
            try:
                mp4['stik'] = [2]  # Audiobook
            except Exception:
                pass
            cover_path = metadata.get('cover_path')
            if cover_path and os.path.exists(cover_path):
                with open(cover_path, 'rb') as cf:
                    cover_data = cf.read()
                fmt = MP4Cover.FORMAT_JPEG if cover_path.lower().endswith(('.jpg', '.jpeg')) else MP4Cover.FORMAT_PNG
                mp4['covr'] = [MP4Cover(cover_data, imageformat=fmt)]
            mp4.save()
        except Exception:
            pass

    # Cleanup temporary files
    try:
        if cover and os.path.exists(cover):
            os.unlink(cover)
    except Exception:
        pass
    try:
        if md_file and os.path.exists(md_file):
            os.unlink(md_file)
    except Exception:
        pass

    return success


def verify_and_retry_conversions(source_mp3_files, conversion_output_dir, bitrate, ffmpeg_path, max_retries=5):
    """
    Verify that all source MP3 files have been successfully converted to M4A.
    Retry conversion for missing files up to max_retries times per file.

    Args:
        source_mp3_files: List of source MP3 file paths
        conversion_output_dir: Path to the conversion output directory
        bitrate: Bitrate for conversion
        ffmpeg_path: Path to ffmpeg executable
        max_retries: Maximum retry attempts per file

    Returns:
        bool: True if all files were successfully converted, False otherwise
    """
    print(f"[VERIFY] Verifying conversion completeness...")

    # Create expected M4A file mapping
    expected_m4a_files = {}
    for mp3_file in source_mp3_files:
        mp3_path = Path(mp3_file)
        expected_m4a = conversion_output_dir / f"{mp3_path.stem}.m4a"
        expected_m4a_files[str(mp3_file)] = expected_m4a

    # Check which files are missing or incomplete
    missing_files = []
    for mp3_file, m4a_file in expected_m4a_files.items():
        if not m4a_file.exists():
            missing_files.append(mp3_file)
            print(f"[VERIFY] Missing: {Path(mp3_file).name} -> {m4a_file.name}")
        elif m4a_file.stat().st_size < 1024:  # File too small, likely incomplete
            missing_files.append(mp3_file)
            print(f"[VERIFY] Incomplete: {Path(mp3_file).name} -> {m4a_file.name} (size: {m4a_file.stat().st_size} bytes)")

    if not missing_files:
        print(f"[VERIFY] ✅ All {len(source_mp3_files)} files successfully converted")
        return True

    print(f"[VERIFY] Found {len(missing_files)} missing/incomplete files - attempting retries...")

    # Retry conversion for missing files
    retry_count = {}
    remaining_files = missing_files.copy()

    while remaining_files and max(retry_count.get(f, 0) for f in remaining_files) < max_retries:
        current_batch = remaining_files.copy()
        remaining_files = []

        for mp3_file in current_batch:
            retry_count[mp3_file] = retry_count.get(mp3_file, 0) + 1
            attempt = retry_count[mp3_file]

            print(f"[RETRY] Attempting conversion {attempt}/{max_retries} for: {Path(mp3_file).name}")

            mp3_path = Path(mp3_file)
            m4a_file = expected_m4a_files[mp3_file]

            # Extract metadata for this file
            from .metadata import extract_all_metadata
            file_metadata = extract_all_metadata(mp3_file) or {}

            # Set basic metadata
            file_metadata.update({
                'title': mp3_path.stem,
                'album': mp3_path.parent.name,
                'genre': 'Audiobook'
            })

            # Attempt conversion
            success = convert_to_m4a(mp3_file, str(m4a_file), bitrate, file_metadata, ffmpeg_path)

            if success and m4a_file.exists() and m4a_file.stat().st_size > 1024:
                print(f"[RETRY] ✅ Successfully converted: {Path(mp3_file).name}")
            else:
                print(f"[RETRY] ❌ Failed conversion attempt {attempt} for: {Path(mp3_file).name}")
                remaining_files.append(mp3_file)

    # Final verification
    final_missing = []
    for mp3_file in missing_files:
        m4a_file = expected_m4a_files[mp3_file]
        if not m4a_file.exists() or m4a_file.stat().st_size < 1024:
            final_missing.append(mp3_file)

    if final_missing:
        print(f"[VERIFY] ❌ Final result: {len(final_missing)}/{len(missing_files)} files could not be converted after {max_retries} retries")
        for mp3_file in final_missing:
            print(f"  - {Path(mp3_file).name}")
        return False
    else:
        print(f"[VERIFY] ✅ All files successfully converted after retries")
        return True