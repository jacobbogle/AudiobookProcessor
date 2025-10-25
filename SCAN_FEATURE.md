# AudiobookProcessor - Library Scan Feature

## Overview

The AudiobookProcessor now includes a powerful **library scan** feature that can recursively search through your audiobook directories to automatically find and process audiobook folders.

## New `scan` Command

```bash
audiobook-p scan <input_directory> <output_directory> [options]
```

### Features

- **Recursive Discovery**: Automatically finds all folders containing audio files
- **Smart Detection**: Identifies series vs novel folder structures
- **Batch Processing**: Processes multiple audiobooks in a single command
- **Dry Run Mode**: Preview what will be processed before running
- **Configurable Depth**: Control how deep to scan directory trees

### Usage Examples

#### Basic Library Scan
```bash
# Scan your entire audiobook library and convert all books to M4B
audiobook-p scan /path/to/audiobooks /path/to/output
```

#### Dry Run (Preview)
```bash
# See what would be processed without actually doing it
audiobook-p scan /path/to/audiobooks /path/to/output --dry-run
```

#### Limited Depth Scan
```bash
# Only scan 3 levels deep to avoid going too deep
audiobook-p scan /path/to/audiobooks /path/to/output --max-depth 3
```

#### With Processing Options
```bash
# Apply author name fixing and use chapter titles
audiobook-p scan /path/to/audiobooks /path/to/output --author-fix --chapter-titles
```

### How It Works

1. **Discovery Phase**: Recursively scans the input directory for folders containing audio files (`.m4a`, `.mp3`, `.m4b`, etc.)

2. **Type Detection**: For each discovered folder, automatically determines if it's:
   - **Novel**: Single folder with audio files
   - **Series**: Folder containing subfolders with audio files

3. **Processing Phase**: Each discovered audiobook folder is processed individually using the standard mutate-convert pipeline

4. **Output**: Creates M4B files in the output directory, named after the source folders

### Directory Structure Examples

#### Novel Structure (Standalone Book)
```
Audiobooks/
└── Standalone Novel/
    ├── Chapter 01.mp3
    ├── Chapter 02.mp3
    └── Chapter 03.mp3
```
→ Discovered as: `Standalone Novel` (novel, 3 files)

#### Series Structure
```
Audiobooks/
└── Fantasy Series/
    ├── Book 1 - The Beginning/
    │   ├── Chapter 01.mp3
    │   └── Chapter 02.mp3
    ├── Book 2 - The Middle/
    │   ├── Chapter 01.mp3
    │   └── Chapter 02.mp3
    └── Book 3 - The End/
        ├── Chapter 01.mp3
        └── Chapter 02.mp3
```
→ Discovered as: `Book 1 - The Beginning`, `Book 2 - The Middle`, `Book 3 - The End` (all novels)

### Command Line Options

- `--max-depth DEPTH`: Maximum directory depth to scan (default: 5)
- `--sort-by {filename,track}`: Sort audio files by filename or track number
- `--chapter-titles`: Use audio filenames as chapter titles in the M4B
- `--part-titles`: Enable part title processing
- `--author-name NAME`: Override author name for all books
- `--narrator-name NAME`: Override narrator name for all books
- `--author-fix`: Apply author name format fixing (Last, First → First Last)
- `--album-sort-prefix PREFIX`: Add prefix to album_sort field
- `--album-suffix SUFFIX`: Add suffix to album_sort field
- `--dry-run`: Show discovery results without processing

### Output

- Creates one M4B file per discovered audiobook folder
- Files are named after their source folder names
- Processing progress is shown for each book
- Summary shows total books processed

### Tips

- Use `--dry-run` first to verify what will be processed
- Start with a small subset of your library to test the output
- The scan respects the same processing options as individual `mutate-convert` commands
- Series books are processed individually - each book becomes its own M4B file