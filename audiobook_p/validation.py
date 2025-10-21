# -*- coding: utf-8 -*-
"""
Enhanced validation and error handling for audiobook processing.
"""

import os
import subprocess
from mutagen import File as MutagenFile


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class DependencyError(Exception):
    """Custom exception for missing dependencies"""
    pass


def check_dependencies():
    """Check if required external dependencies are available"""
    errors = []
    
    # Check for ffmpeg
    try:
        # Use subprocess.call for Python 2.7 compatibility
        result = subprocess.call(['ffmpeg', '-version'], 
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result != 0:
            errors.append("ffmpeg is not working properly")
    except (OSError, IOError):  # FileNotFoundError doesn't exist in Python 2.7
        errors.append("ffmpeg is not installed or not in PATH")
    
    if errors:
        raise DependencyError("Missing dependencies: " + ", ".join(errors))
    
    return True


def validate_audio_file(file_path):
    """
    Validate that a file is a proper audio file that can be processed.
    
    Args:
        file_path: Path to the audio file
        
    Returns:
        bool: True if valid
        
    Raises:
        ValidationError: If file is invalid
    """
    # Check if file exists
    if not os.path.exists(file_path):
        raise ValidationError("File not found: {}".format(file_path))
    
    # Check if it's actually a file (not a directory)
    if not os.path.isfile(file_path):
        raise ValidationError("Path is not a file: {}".format(file_path))
    
    # Check file size (should be at least 1KB)
    file_size = os.path.getsize(file_path)
    if file_size < 1024:
        raise ValidationError("File too small ({} bytes), possibly corrupted: {}".format(file_size, file_path))
    
    # Check file extension
    _, ext = os.path.splitext(file_path.lower())
    if ext not in ['.mp3', '.m4a', '.m4b']:
        raise ValidationError("Unsupported file format: {}".format(ext))
    
    # Try to load with mutagen
    try:
        audio = MutagenFile(file_path)
        if audio is None:
            raise ValidationError("Cannot read audio metadata, file may be corrupted: {}".format(file_path))
        
        # Check if file has audio duration
        if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            if audio.info.length <= 0:
                raise ValidationError("Audio file has no duration: {}".format(file_path))
        
    except Exception as e:
        raise ValidationError("Error reading audio file {}: {}".format(file_path, str(e)))
    
    return True


def validate_folder_structure(folder_path):
    """
    Validate that a folder contains processable audio files.
    
    Args:
        folder_path: Path to the folder
        
    Returns:
        list: List of valid audio files found
        
    Raises:
        ValidationError: If folder structure is invalid
    """
    if not os.path.exists(folder_path):
        raise ValidationError("Folder not found: {}".format(folder_path))
    
    if not os.path.isdir(folder_path):
        raise ValidationError("Path is not a directory: {}".format(folder_path))
    
    # Find audio files
    audio_files = []
    audio_extensions = ['.mp3', '.m4a', '.m4b']
    
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            _, ext = os.path.splitext(file.lower())
            if ext in audio_extensions:
                try:
                    validate_audio_file(file_path)
                    audio_files.append(file_path)
                except ValidationError as e:
                    print("Warning: Skipping invalid file - {}".format(e))
    
    if not audio_files:
        raise ValidationError("No valid audio files found in: {}".format(folder_path))
    
    return sorted(audio_files)


def validate_output_path(output_path):
    """
    Validate that the output path is writable and appropriate.
    
    Args:
        output_path: Intended output file or directory path
        
    Returns:
        str: Validated and potentially corrected output path
        
    Raises:
        ValidationError: If output path is invalid
    """
    # If it's a directory, check if it exists and is writable
    if os.path.isdir(output_path):
        if not os.access(output_path, os.W_OK):
            raise ValidationError("Output directory is not writable: {}".format(output_path))
        return output_path
    
    # If it's a file path, check the directory
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as e:
            raise ValidationError("Cannot create output directory {}: {}".format(output_dir, e))
    
    if output_dir and not os.access(output_dir, os.W_OK):
        raise ValidationError("Output directory is not writable: {}".format(output_dir))
    
    # Check if output file already exists and warn
    if os.path.exists(output_path):
        print("Warning: Output file already exists and will be overwritten: {}".format(output_path))
    
    return output_path


def estimate_processing_time(audio_files):
    """
    Estimate processing time based on file count and sizes.
    
    Args:
        audio_files: List of audio file paths
        
    Returns:
        dict: Estimation details
    """
    total_size = sum(os.path.getsize(f) for f in audio_files)
    total_size_mb = total_size / (1024 * 1024)
    
    # Rough estimates based on typical performance
    # Metadata extraction: ~1MB/sec
    # M4B conversion: ~0.5MB/sec (depends on transcoding)
    
    metadata_time = len(audio_files) * 2  # ~2 seconds per file for metadata
    conversion_time = total_size_mb * 2   # ~2 seconds per MB for conversion
    
    total_estimate = metadata_time + conversion_time
    
    return {
        'file_count': len(audio_files),
        'total_size_mb': round(total_size_mb, 1),
        'estimated_seconds': int(total_estimate),
        'estimated_minutes': round(total_estimate / 60, 1)
    }


def safe_file_operation(operation_func, *args, **kwargs):
    """
    Wrapper for file operations with automatic cleanup on failure.
    
    Args:
        operation_func: Function to execute
        *args, **kwargs: Arguments for the function
        
    Returns:
        Result of operation_func
        
    Raises:
        Exception: Re-raises any exception from operation_func
    """
    temp_files = []
    temp_dirs = []
    
    try:
        # Store temp files/dirs for cleanup if operation tracks them
        if 'temp_tracking' in kwargs:
            temp_files = kwargs.pop('temp_tracking').get('files', [])
            temp_dirs = kwargs.pop('temp_tracking').get('dirs', [])
        
        result = operation_func(*args, **kwargs)
        return result
        
    except Exception as e:
        # Cleanup on failure
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        
        for temp_dir in temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    import shutil
                    shutil.rmtree(temp_dir)
            except:
                pass
        
        # Re-raise the original exception
        raise e


def progress_callback(current, total, operation="Processing"):
    """
    Simple progress callback for operations.
    
    Args:
        current: Current progress (0-based)
        total: Total items
        operation: Description of operation
    """
    percentage = ((current + 1) / total) * 100
    import sys
    sys.stdout.write("\r{}: {}/{} ({:.1f}%)".format(operation, current + 1, total, percentage))
    sys.stdout.flush()
    if current + 1 == total:
        print()  # New line when complete


if __name__ == "__main__":
    # Quick test of validation functions
    print("Testing validation functions...")
    
    try:
        check_dependencies()
        print("✓ Dependencies check passed")
    except DependencyError as e:
        print("✗ Dependencies check failed: {}".format(e))
    
    print("Validation module ready for use")