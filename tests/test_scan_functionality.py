import os
import tempfile
import shutil
import pytest
from audiobook_p.utils import discover_audiobook_folders, detect_folder_type
from audiobook_p.cli import main as cli_main
import sys
from unittest.mock import patch


def _make_silent_mp3(path, duration=0.5):
    """Create a short silent MP3 for testing."""
    # Use ffmpeg if available, otherwise create a dummy file
    if shutil.which('ffmpeg'):
        cmd = [
            'ffmpeg', '-y', '-f', 'lavfi', '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
            '-t', str(duration), '-c:a', 'mp3', '-b:a', '64k', path
        ]
        import subprocess
        subprocess.run(cmd, check=True, capture_output=True)
    else:
        # Create a dummy file if ffmpeg not available
        with open(path, 'wb') as f:
            f.write(b'dummy audio data')


class TestDiscoverAudiobookFolders:
    """Test the recursive folder discovery functionality."""

    def test_discover_empty_directory(self, tmp_path):
        """Test discovery on empty directory."""
        result = discover_audiobook_folders(str(tmp_path))
        assert result == []

    def test_discover_single_novel_folder(self, tmp_path):
        """Test discovery of a single novel folder."""
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        audio_file = novel_dir / "chapter1.mp3"
        _make_silent_mp3(str(audio_file))

        result = discover_audiobook_folders(str(tmp_path))
        assert len(result) == 1
        assert result[0]['path'] == str(novel_dir)
        assert result[0]['type'] == 'novel'
        assert result[0]['audio_files'] == 1

    def test_discover_series_structure(self, tmp_path):
        """Test discovery of series with multiple books."""
        series_dir = tmp_path / "series"
        book1_dir = series_dir / "book1"
        book2_dir = series_dir / "book2"
        book1_dir.mkdir(parents=True)
        book2_dir.mkdir()

        # Add audio files to books
        _make_silent_mp3(str(book1_dir / "chapter1.mp3"))
        _make_silent_mp3(str(book2_dir / "chapter1.mp3"))

        result = discover_audiobook_folders(str(tmp_path))
        assert len(result) == 2

        # Should find both book folders
        paths = [r['path'] for r in result]
        assert str(book1_dir) in paths
        assert str(book2_dir) in paths

        for r in result:
            assert r['type'] == 'novel'  # Individual books are novels
            assert r['audio_files'] == 1

    def test_discover_max_depth_limit(self, tmp_path):
        """Test that max_depth parameter limits recursion."""
        # Create deep nested structure
        deep_dir = tmp_path / "level1" / "level2" / "level3" / "level4" / "level5" / "book"
        deep_dir.mkdir(parents=True)
        _make_silent_mp3(str(deep_dir / "audio.mp3"))

        # With max_depth=3, should not find the deep book
        result = discover_audiobook_folders(str(tmp_path), max_depth=3)
        assert len(result) == 0

        # With higher max_depth, should find it
        result = discover_audiobook_folders(str(tmp_path), max_depth=6)
        assert len(result) == 1

    def test_detect_folder_type_novel(self, tmp_path):
        """Test novel folder type detection."""
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        _make_silent_mp3(str(novel_dir / "chapter1.mp3"))

        # Add a subdirectory without audio (should still be novel)
        sub_dir = novel_dir / "metadata"
        sub_dir.mkdir()
        (sub_dir / "info.txt").write_text("metadata")

        result = detect_folder_type(str(novel_dir))
        assert result == 'novel'

    def test_detect_folder_type_series_with_audio_subfolders(self, tmp_path):
        """Test series detection when folder has audio files and audio subfolders."""
        series_dir = tmp_path / "series"
        series_dir.mkdir()

        # Add audio file to root (unusual but possible)
        _make_silent_mp3(str(series_dir / "intro.mp3"))

        # Add book subfolder with audio
        book_dir = series_dir / "book1"
        book_dir.mkdir()
        _make_silent_mp3(str(book_dir / "chapter1.mp3"))

        result = detect_folder_type(str(series_dir))
        assert result == 'series'

    def test_detect_folder_type_unknown(self, tmp_path):
        """Test unknown type for folders without audio."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        result = detect_folder_type(str(empty_dir))
        assert result == 'unknown'


class TestScanCLI:
    """Test the scan CLI command."""

    def test_scan_dry_run(self, tmp_path):
        """Test scan command with dry run."""
        # Create test structure
        novel_dir = tmp_path / "novel"
        novel_dir.mkdir()
        _make_silent_mp3(str(novel_dir / "audio.mp3"))

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Mock sys.argv for CLI testing - new syntax: input output --dry-run (scan is default)
        with patch('sys.argv', ['cli.py', str(tmp_path), str(output_dir), '--dry-run']):
            with patch('builtins.print') as mock_print:
                cli_main()

                # Check that discovery messages were printed
                print_calls = [call.args[0] for call in mock_print.call_args_list]
                assert any("Found 1 audiobook folder" in msg for msg in print_calls)
                assert any("Dry run - not processing" in msg for msg in print_calls)

    def test_scan_help(self):
        """Test scan command help doesn't crash."""
        with patch('sys.argv', ['cli.py', 'scan', '--help']):
            with patch('sys.stdout'):
                with pytest.raises(SystemExit):  # --help causes SystemExit
                    cli_main()