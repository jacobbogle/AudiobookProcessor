# Audiobook Processor - M4B Converter

This tool now includes a converter that takes a folder of audio files (after metadata mutation) and converts them to a single M4B file with chapters.

## Quick Start

```bash
# Show all available commands
./audiobook-p-cli -h

# Convert a folder to M4B
./audiobook-p-cli convert /path/to/audiobook/folder /path/to/output/book.m4b

# Show help for specific command
./audiobook-p-cli convert -h
```

## Usage Workflow

1. **Extract metadata** from your audiobook folder:

   ```bash
   ./audiobook-p-cli extract /path/to/audiobook/folder
   ```

2. **Mutate the metadata** (optional, but recommended):

   ```bash
   ./audiobook-p-cli mutate /path/to/audiobook/folder /path/to/output/folder --album-sort-prefix "Author Name"
   ```

3. **Convert to M4B** with chapters:

   ```bash
   ./audiobook-p-cli convert /path/to/mutated/folder /path/to/output/book.m4b
   ```

## Available Commands

Use `./audiobook-p-cli -h` to see all available commands:

- **info** - Show package version information
- **extract** - Extract metadata from audio files or folders  
- **mutate** - Process and clean metadata, move files to organized structure
- **convert** - Convert audio folder to single M4B file with chapters

Each command has its own help: `./audiobook-p-cli [command] -h`

## Command Details

### Info Command

```bash
./audiobook-p-cli info
# Output: audiobook-p v1.0.0
```

### Extract Command

```bash
./audiobook-p-cli extract -h
```

**Usage:** `./audiobook-p-cli extract source`

**Arguments:**

- `source` - Path to audio file or folder

### Mutate Command

```bash
./audiobook-p-cli mutate -h
```

**Usage:** `./audiobook-p-cli mutate [options] source destination`

**Arguments:**

- `source` - Path to audio folder
- `destination` - Destination path for mutated files

**Options:**

- `--album-sort-prefix` - String to prefix album_sort with " : " separator
- `--album-suffix` - String to suffix album with " - " separator

### Convert Command

```bash
./audiobook-p-cli convert -h
```

**Usage:** `./audiobook-p-cli convert source output`

**Arguments:**

- `source` - Path to folder containing audio files (MP3/M4A)
- `output` - Output directory or M4B file path
  - If a directory: Creates `{folder_name}.m4b` in that directory
  - If a file path: Creates M4B at the specified location

**Examples:**

```bash
# Convert to Desktop folder (creates "Thorn and Talon.m4b")
./audiobook-p-cli convert "/path/to/Thorn and Talon" "/Users/user/Desktop/"

# Convert to specific file path
./audiobook-p-cli convert "/path/to/audiobook" "/path/to/output/my-book.m4b"
```

## What the Converter Does

The `convert` command:

- Takes all MP3/M4A files from the specified folder
- Concatenates them into a single M4B file (MP4 container with AAC audio)
- Creates chapter markers based on:
  - Individual file titles (used as chapter titles)
  - File durations (used to calculate chapter timestamps)
- Preserves metadata from the first file (album, artist, title, genre)
- Optimizes the output for streaming playback

## Example Output

```json
{
  "operation": "convert",
  "source_folder": "/path/to/mutated/folder",
  "output_file": "/path/to/output/book.m4b",
  "format": "M4B"
}
```

## Requirements

- ffmpeg must be installed on your system
- The `ffmpeg-python` package (automatically installed if missing)
- Source folder should contain only the audio files to be converted

## Chapter Creation

Chapters are created automatically:

- Chapter titles come from each file's `title` metadata
- Chapter boundaries are based on audio file durations
- If metadata extraction fails, chapters default to "Chapter 1", "Chapter 2", etc.

## Supported Input Formats

- MP3 files
- M4A files (AAC audio)

Output is always M4B format for optimal audiobook compatibility.
