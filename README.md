# Audiobook Processor

A powerful command-line tool for processing audiobooks. Combine multiple MP3 files, convert to M4A, apply metadata, and organize your audiobook library.

## 🚀 Quick Start

```bash
# Process a single folder of MP3 files
python audiobook_processor.py folder "path/to/audiobook/folder"

# Process multiple folders recursively (batch mode)
python audiobook_processor.py batch "path/to/audiobooks/library"

# Convert single MP3 file to M4A
python audiobook_processor.py file "input.mp3"

# Combine multiple MP3 files
python audiobook_processor.py file "chapter1.mp3" "chapter2.mp3" "chapter3.mp3"
```

## 📁 File Structure & Organization

### Important: How Folders Are Processed

The processor expects your audiobooks to be organized in folders. Each folder containing MP3 files is treated as one audiobook:

```
📂 Audiobooks Library
├── 📂 "Harry Potter Series"
│   ├── 📂 "1 Harry Potter and the Philosopher's Stone"
│   │   ├── Chapter 01.mp3
│   │   ├── Chapter 02.mp3
│   │   └── ...
│   └── 📂 "2 Harry Potter and the Chamber of Secrets"
│       ├── Chapter 01.mp3
│       └── ...
├── 📂 "Ender's Game"
│   ├── Ender's Game (1).mp3
│   ├── Ender's Game (2).mp3
│   └── ...
└── 📂 "Standalone Book"
    └── single-file.mp3
```

**Key Points:**
- **Each folder = one audiobook**: All MP3 files in a folder are combined into a single output file
- **Folder name becomes title**: The folder name is used as the audiobook title (with sanitization)
- **Parent folders for series**: Parent folder names help organize series (e.g., "Harry Potter Series")
- **Minimum file requirement**: Configurable with `--min-files` (default: 2 for batch mode, 1 for folder mode). Special modes like `--combine-only` and `--metadata-only` can work with fewer files.

### First File Importance

The **first MP3 file** in each folder is crucial because:

1. **Bitrate detection**: Audio quality is auto-detected from the first file (128k, 192k, etc.)
2. **Metadata extraction**: Author, cover art, and existing metadata are taken from the first file
3. **Naming reference**: If no custom title is provided, the first filename helps determine the output name

**Tip**: Sort your MP3 files properly before processing - the first file sets the standard for the entire audiobook.

## 🧹 Name Sanitization

The processor automatically cleans and formats audiobook names for professional results:

### What Gets Sanitized
- **Leading numbers removed**: `"01 Harry Potter"` → `"Harry Potter"`
- **Series prefixes removed**: `"Book 3 - Title"` → `"Title"`
- **Special characters**: Only letters, spaces, and basic punctuation kept
- **Title casing**: Proper capitalization with small words lowercased
- **Processing suffixes removed**: `"_combined"` suffix removed when re-processing combined files

### Examples
```
Input Folder Name              → Output Title
─────────────────────────────────────────────────
"01 Harry Potter"              → "Harry Potter"
"Book 3 - Chamber of Secrets"  → "Chamber of Secrets"
"enders game (2020)"           → "Enders Game"
"TITAN'S CURSE"                → "Titan's Curse"
"1984 (audiobook)"             → "1984"
"Combined"                     → "Combined"
"Harry Potter Combined Edition" → "Harry Potter Combined Edition"
```

### Filename vs Metadata
- **Filenames**: Windows-safe, no special characters (`<>:"/\|?*`)
- **Metadata tags**: Preserve apostrophes and formatting for proper display
- **Processing artifacts**: Only "_combined" suffix (added during processing) is removed when re-processing

## 🎯 Processing Modes

### Batch Mode (Multiple Folders)

```bash
# Basic batch processing
python audiobook_processor.py batch "D:\Audiobooks" --combine-only --compress-originals --delete-originals

# Process with parent folder prefix (for series organization)
python audiobook_processor.py batch "D:\Harry Potter Series" --prefix-parent --format m4a

# Process with custom prefix string
python audiobook_processor.py batch "D:\Audiobooks" --custom-prefix "Audiobooks" --format m4a

# Combined: both parent folder and custom prefix
python audiobook_processor.py batch "D:\Audiobooks Library" --prefix-parent --custom-prefix "Library" --format m4a
```

- Recursively scans for folders with MP3 files
- Processes folders in batches (default: 5 at a time)
- Perfect for large libraries
- `--prefix-parent` option useful for organizing book series with parent folder names

### Folder Mode (Single Folder)

```bash
python audiobook_processor.py folder "D:\Audiobooks\Enders Game" --format m4a
```

- Processes one folder at a time
- Good for testing or individual books

### File Mode (Individual Files)

```bash
# Convert single MP3 to M4A
python audiobook_processor.py file "input.mp3" --format m4a

# Combine multiple MP3s
python audiobook_processor.py file *.mp3 --combine-only
```

- Single file: Convert to M4A
- Multiple files: Combine into one MP3

### Metadata Mode (Update Only)

```bash
python audiobook_processor.py metadata "folder/" --title-name "New Title" --author-name "Author Name"
```

- Only updates metadata, no combining or converting
- Can work with single files or folders with any number of MP3s

## ⚙️ Key Options

### Output Formats

- `--format m4a`: Convert to AAC M4A (default, smaller files)
- `--format mp3`: Keep as MP3 (faster, no conversion)
- `--combine-only`: Combine MP3s and apply metadata without converting to M4A (works with 1+ files)

### Compression & Cleanup

- `--compress-originals`: Create ZIP archives of original MP3s
- `--delete-originals`: Remove original files after compression
- `--delete-combined`: Remove combined MP3 after M4A conversion

### Metadata

- `-t, --title-name`: Custom title (overrides folder name)
- `-a, --author-name`: Author/artist name
- `-c, --cover`: Path to cover image (JPG/PNG)
- `-s, --sort-as`: Sort title for library ordering

### Batch Processing Title Customization

- `--prefix-parent`: Prepend parent folder name to title (useful for series)
  - Format: `"Parent Folder - Book Name"`
  - Example: Process folders in "Harry Potter Series" → titles become "Harry Potter Series - Philosopher's Stone", "Harry Potter Series - Chamber of Secrets", etc.

- `--custom-prefix`: Add a custom prefix string to all titles
  - Works standalone: all titles prefixed with custom string
  - Works with `--prefix-parent`: applies both parent folder name AND custom prefix
  - Example: `--custom-prefix "Audiobook"` → "Audiobook - Book Name"
  - Combined example: `--prefix-parent --custom-prefix "Series"` → "Series - Parent Folder - Book Name"

### Performance

- `--parallel`: Process folders simultaneously (faster but more CPU)
- `--batch-size`: Number of folders per batch (default: 5)
- `--long-running`: Prevent system sleep during processing
- `-b, --bitrate`: Audio quality (128k, 192k, etc.)
- `--min-files`: Minimum MP3 files required per folder (default: 2 for batch, 1 for folder). Special modes may allow fewer files.

## 📋 Requirements & Setup

### Dependencies
- **Python 3.8+**
- **FFmpeg** (automatically downloaded by enhanced installer)
- **Required packages**: pydub, mutagen, tqdm, colorama

### Installation Options

1. **Enhanced Installer** (Recommended):
   ```cmd
   install_enhanced.bat
   ```
   Downloads everything automatically.

2. **Portable Version**:
   ```python
   python build_portable.py
   ```

3. **Manual Setup**: Install Python packages yourself

## 🔧 Troubleshooting

### Common Issues

**"FFmpeg not found"**
- Use the enhanced installer or run `install_enhanced.bat`

**"Permission denied"**
- Close any media players using the files
- Check write permissions on destination folder

**"No MP3 files found"**
- Ensure files end with `.mp3` (case-sensitive)
- Check folder has at least `--min-files` MP3s (default: 2 for batch, 1 for folder/standard modes)
- Note: `--combine-only` and `--metadata-only` modes can work with single files

**"Concatenation failed"**
- File paths with special characters are handled automatically
- Check for corrupted MP3 files

### File Naming Tips

- **Avoid special characters** in folder names when possible
- **Leading numbers** are automatically removed (use them for sorting)
- **Series organization**: Use parent folders for series names
- **Consistent naming**: The first file's metadata sets the standard

### Performance Tips

- **Batch mode** for large libraries (handles hundreds of books)
- **Parallel processing** for faster completion on multi-core systems
- **Long-running flag** for overnight processing
- **Combine-only** for fastest processing (no format conversion)

## 📊 Processing Flow

1. **Scan**: Find folders with MP3 files (configurable minimum, default 2 for batch, 1 for folder)
2. **Analyze**: Extract metadata from first file, detect bitrate
3. **Sanitize**: Clean folder names for titles (preserves legitimate "combined" in names)
4. **Combine**: Concatenate MP3s using FFmpeg (fast, no re-encoding)
5. **Convert**: Optional M4A conversion with AAC encoding
6. **Metadata**: Apply title, author, cover art, chapters
7. **Compress**: Optional ZIP archiving of originals
8. **Cleanup**: Optional deletion of source files

## 🎵 Output Details

- **M4A files**: AAC-encoded, iTunes-compatible, ~50% smaller than MP3
- **MP3 files**: Original quality preserved, fast processing
- **Metadata**: Full ID3/MP4 tags with cover art support
- **Filenames**: Windows-safe, descriptive names
- **Archives**: Original files preserved in ZIP format

## 📝 Examples

```bash
# Process entire library with compression
python audiobook_processor.py batch "D:\Audiobooks" --compress-originals --delete-originals --format m4a

# Quick MP3 combine only (fastest)
python audiobook_processor.py folder "D:\Books\Enders Game" --combine-only

# Custom metadata
python audiobook_processor.py file *.mp3 -t "Ender's Game" -a "Orson Scott Card" -c "cover.jpg"

# Large batch with power management
python audiobook_processor.py batch "D:\Library" --parallel --long-running --batch-size 10
```
