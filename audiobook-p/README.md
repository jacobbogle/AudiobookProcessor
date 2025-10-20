# audiobook-p

Modern Python package for audiobook processing with CLI interface.

## Structure

- `audiobook_p/` — Python package
- `audiobook-p/main.py` — Console entrypoint to run package CLI
- `pyproject.toml` — Poetry project configuration
- `requirements.txt` — Runtime dependencies
- `tests/` — Basic smoke tests

## Installation

```bash
pip install -r requirements.txt
# or
poetry install
```

## Setup

To use the `audiobook-p-cli` command directly, add these lines to your `~/.zshrc` (or `~/.bashrc`):

```bash
export PYTHONPATH="/Users/channingbogle/Dev.nosync/AudiobookProcessor/audiobook-p:$PYTHONPATH"
export PATH="/Users/channingbogle/Dev.nosync/AudiobookProcessor:$PATH"
```

Then reload your shell: `source ~/.zshrc`

## Usage

### Direct Command (after setup)

If you've added the paths to your shell profile, you can run:

```bash
# Show package info
audiobook-p-cli info

# Extract metadata from audio files/folders
audiobook-p-cli extract <source_path>

# Mutate metadata and move files
audiobook-p-cli mutate <source_path> <destination_path> [options]
```

### Python Module (always works)

```bash
# From the AudiobookProcessor root directory
python -m audiobook_p.main info
python -m audiobook_p.main extract <source_path>
python -m audiobook_p.main mutate <source_path> <destination_path> [options]
```

### Mutate Options

- `--album-sort-prefix PREFIX` — Prefix album_sort field with "PREFIX : "
- `--album-suffix SUFFIX` — Suffix album field with " - SUFFIX"

### Examples

```bash
# Extract metadata from a single file
python -m audiobook_p.main extract "path/to/audio.mp3"

# Extract metadata from a folder
python -m audiobook_p.main extract "path/to/audio/folder"

# Mutate files with prefix and move to destination
python -m audiobook_p.main mutate "source/folder" "destination/folder" --album-sort-prefix "Series"

# Mutate files with both prefix and suffix
python -m audiobook_p.main mutate "source/folder" "destination/folder" --album-sort-prefix "Author" --album-suffix "Complete"
```
