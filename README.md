# Audiobook Processing System

A comprehensive audiobook processing system that converts, combines, and organizes MP3 audiobook files with advanced features for long-running operations.

## 🚀 Quick Start - Choose Your Installation

### Option 1: Enhanced Installer (Recommended - Zero Dependencies)
**Automatically downloads and bundles FFmpeg - no manual setup required!**

```cmd
install_enhanced.bat
```

**Features:**
- ✅ Automatic FFmpeg download and bundling
- ✅ Python dependency auto-installation  
- ✅ Desktop shortcuts and file associations
- ✅ Complete uninstaller included
- ✅ No manual dependency management needed

### Option 2: Portable Version (Zero Installation)
**Completely self-contained - runs from any folder**

```python
python build_portable.py
```

Creates portable packages with embedded Python and bundled FFmpeg.

### Option 3: Standard Installation (Manual Dependencies)
**Traditional installer - requires manual Python/FFmpeg setup**

```cmd
build_windows_installer.bat
```
- Filenames and tags are sanitized using a "book-title" style: title-cased, common punctuation preserved for tags, and filename-safe characters used for filenames. The script also removes the word "combined" from stems when naming outputs.
- The combiner writes MP3 ID3 tags (title/album) using the same book-title style.

## Options (short)

combine_mp3.py
- `-i`, `--input` — input directory or path
- `-o`, `--output` — output filename (if omitted the folder name is used)
- `-b`, `--bitrate` — export bitrate (e.g., `192k`)
- `-y`, `--yes` — overwrite without prompting
- `--ffmpeg-path` — full path to `ffmpeg.exe` or its folder

convert_to_m4a.py
- `-i`, `--input` — input MP3 file
- `-o`, `--output` — output M4A file
- `-b`, `--bitrate` — AAC bitrate (e.g., `192k`)
- `--ffmpeg-path` — full path to `ffmpeg.exe`
- `--metadata-json` — optional JSON file containing metadata keys like `title`, `artist`, `album`, `chapters`, `cover_path`

smoke_test.py
- No required arguments — runs a deterministic small test that exercises combine + convert. It will try to reuse metadata from `D:\Music\audiobooks\Airman` if present.

## Troubleshooting

- "Couldn't find ffmpeg or avconv" warnings: pass `--ffmpeg-path` to both scripts with the path to your `ffmpeg.exe`.
- If output filenames look collapsed (e.g., `Airmancombined.mp3`), the scripts sanitize names by removing digits and special characters and apply book-title style. If you prefer to preserve underscores/digits, I can add flags to control sanitization behavior.

### Conda Environment Issues

If you get "conda is not recognized" errors in new PowerShell windows:

**Automatic Fix (Recommended):**
```powershell
# Run this once to set up conda for all new PowerShell windows
& "C:\Users\Bogle\anaconda3\Scripts\conda.exe" init powershell
```

**Manual Fix for Current Session:**
```powershell
# Run these commands in each new PowerShell window
& "C:\Users\Bogle\anaconda3\Scripts\conda.exe" "shell.powershell" "hook" | Out-String | Invoke-Expression
conda activate .\.conda
```

**Note:** Conda should now initialize automatically in new PowerShell windows.

## Development notes

- The combiner uses `pydub` to assemble audio and runs export in a background thread. During export it shows an animated spinner/loader in the console.
- The converter uses `ffmpeg` for reliable MP4 creation and `mutagen` to write MP4 tags (`©nam`, `©ART`, `©alb`, `covr`, `stik` for media kind).

## Next steps / Customization ideas

- Allow a CLI flag to preserve digits in titles (useful for books like `1984`).
- Toggle between `m4a` and `m4b` containers via a converter flag.
- Optional colorized spinner output for PowerShell.

If you want any of those, tell me which to implement and I’ll add it.
