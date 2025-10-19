"""
Audiobook Processor - Compression Operations
"""

import os
import zipfile
from pathlib import Path

# Auto-install required packages
try:
    from tqdm import tqdm
except ImportError:
    print("tqdm not installed. Installing...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm


def compress_original_files(folder_path, mp3_files, output_name, delete_originals=False):
    """Compress the original MP3 files into a ZIP archive.

    Args:
        folder_path: Path to the folder containing the files
        mp3_files: List of MP3 file paths to compress
        output_name: Base name for the archive
        delete_originals: Whether to delete original files after compression

    Returns:
        tuple: (success, archive_path)
    """
    try:
        folder_path = Path(folder_path)
        archive_name = f"{output_name}_original_files.zip"
        archive_path = folder_path / archive_name

        print(f"\n[COMPRESS] Compressing {len(mp3_files)} original MP3 files...")
        print(f"Archive: {archive_name}")

        # Create ZIP archive with optimized compression for speed
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as zipf:
            total_original_size = 0

            for mp3_file in tqdm(mp3_files, desc="Compressing files", unit="file"):
                mp3_path = Path(mp3_file)
                if mp3_path.exists():
                    # Get file size before compression
                    file_size = mp3_path.stat().st_size
                    total_original_size += file_size

                    # Add file to archive with just the filename (no path)
                    zipf.write(mp3_path, mp3_path.name)

        # Get compressed size
        compressed_size = archive_path.stat().st_size
        compression_ratio = (1 - compressed_size / total_original_size) * 100

        print(f"[SUCCESS] Compression complete!")
        print(f"   Original size: {total_original_size / (1024*1024):.1f} MB")
        print(f"   Compressed size: {compressed_size / (1024*1024):.1f} MB")
        print(f"   Compression ratio: {compression_ratio:.1f}%")

        # Delete original files if requested
        if delete_originals:
            deleted_count = 0
            for mp3_file in mp3_files:
                try:
                    os.remove(mp3_file)
                    deleted_count += 1
                except Exception as e:
                    print(f"[WARNING]  Failed to delete {mp3_file}: {e}")

            if deleted_count > 0:
                print(f"[DELETE] Deleted {deleted_count} original MP3 files")

        return True, str(archive_path)

    except Exception as e:
        print(f"[ERROR] Compression failed: {e}")
        return False, None