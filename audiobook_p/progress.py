# -*- coding: utf-8 -*-
"""
Progress tracking and user feedback for audiobook processing operations.
"""

import sys
import time
import logging
from typing import Callable, Any


class ProgressTracker:
    """Simple progress tracker for console applications"""
    
    def __init__(self, total: int, description: str = "Processing", show_percentage: bool = True, bar_width: int = 20):
        self.total = total
        self.current = 0
        self.description = description
        self.show_percentage = show_percentage
        self.bar_width = bar_width
        self.start_time = time.time()
        self.last_display = ""
        
        # Detect Unicode support and set characters accordingly
        self._detect_unicode_support()
        
    def _detect_unicode_support(self):
        """Detect if Unicode characters are supported and set appropriate characters"""
        try:
            # Try to encode Unicode characters
            '█'.encode(sys.stdout.encoding or 'utf-8')
            '░'.encode(sys.stdout.encoding or 'utf-8')
            # If successful, use Unicode block characters
            self.filled_char = '█'
            self.empty_char = '░'
        except (UnicodeEncodeError, LookupError):
            # Fall back to ASCII characters
            self.filled_char = '#'
            self.empty_char = '-'
        
    def update(self, increment: int = 1, message: str = None):
        """Update progress by increment amount"""
        self.current += increment
        
        # Display progress
        self._display_progress(message)
        
    def set_progress(self, current: int, message: str = None):
        """Set absolute progress value"""
        self.current = current
        self._display_progress(message)
        
    def _display_progress(self, message: str = None):
        """Display current progress with a loading bar"""
        if self.total == 0:
            return
            
        percentage = (self.current / self.total) * 100
        
        # Create loading bar using detected characters
        filled_width = int(self.bar_width * self.current / self.total)
        bar = self.filled_char * filled_width + self.empty_char * (self.bar_width - filled_width)
        
        # Build progress string
        progress_str = f"{self.description}: [{bar}] {self.current}/{self.total}"
        
        if self.show_percentage:
            progress_str += f" ({percentage:.1f}%)"
        
        if message:
            progress_str += f" - {message}"
        
        # Add estimated time remaining
        if self.current > 0 and self.current < self.total:
            elapsed = time.time() - self.start_time
            rate = self.current / elapsed
            if rate > 0:
                remaining_items = self.total - self.current
                eta_seconds = remaining_items / rate
                if eta_seconds < 60:
                    eta_str = f"{int(eta_seconds)}s"
                else:
                    eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s"
                progress_str += f" (ETA: {eta_str})"
        
        # Only print if different from last display to avoid spam
        if progress_str != self.last_display:
            # Clear the current line using ANSI escape code and print the new progress
            print('\033[2K\r', end='', flush=True)  # Clear entire line and return to start
            print(progress_str, end='', flush=True)  # Print new progress without newline
            self.last_display = progress_str
        
    def finish(self, message: str = "Complete"):
        """Mark progress as finished"""
        self.current = self.total
        
        # Show final progress bar
        bar = "█" * self.bar_width
        elapsed = time.time() - self.start_time
        
        progress_str = f"{self.description}: [{bar}] {self.current}/{self.total} (100.0%)"
        if message:
            progress_str += f" - {message}"
        progress_str += f" ✓ Completed in {elapsed:.1f}s"
        
        print(progress_str)  # Final message should stay on screen
        print()  # Add newline for subsequent output


class Logger:
    """Adapter that forwards to Python's logging while keeping a simple API."""

    def __init__(self, level: str = 'INFO', show_timestamps: bool = False):
        self.logger = logging.getLogger('audiobook_p.progress')
        if not self.logger.handlers:
            logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
        self.show_timestamps = show_timestamps

    def debug(self, message: str):
        self.logger.debug(message)

    def info(self, message: str):
        self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str):
        self.logger.error(message)


def with_progress(func: Callable, items: list, description: str = "Processing") -> Any:
    """
    Decorator/wrapper to add progress tracking to a function that processes a list of items.
    
    Args:
        func: Function that takes (item, progress_tracker) as arguments
        items: List of items to process
        description: Description for progress display
        
    Returns:
        Results from processing all items
    """
    progress = ProgressTracker(len(items), description)
    results = []
    
    for i, item in enumerate(items):
        try:
            result = func(item, progress)
            results.append(result)
            progress.update(1)
        except Exception as e:
            progress.update(1, f"Error: {str(e)[:50]}...")
            results.append({'error': str(e), 'item': item})
    
    progress.finish()
    return results


def safe_operation(operation_name: str, operation_func: Callable, *args, **kwargs) -> Any:
    """
    Execute an operation with error handling and user feedback.
    
    Args:
        operation_name: Human-readable name for the operation
        operation_func: Function to execute
        *args, **kwargs: Arguments for the function
        
    Returns:
        Result of operation_func or None if failed
    """
    logger = Logger()
    
    try:
        logger.info(f"Starting {operation_name}...")
        start_time = time.time()
        
        result = operation_func(*args, **kwargs)
        
        elapsed = time.time() - start_time
        logger.info(f"✓ {operation_name} completed in {elapsed:.1f}s")
        
        return result
        
    except Exception as e:
        logger.error(f"✗ {operation_name} failed: {str(e)}")
        return None


def ask_user_confirmation(message: str, default: bool = False) -> bool:
    """
    Ask user for yes/no confirmation.
    
    Args:
        message: Question to ask the user
        default: Default answer if user just presses Enter
        
    Returns:
        True for yes, False for no
    """
    default_str = "Y/n" if default else "y/N"
    
    while True:
        try:
            response = input(f"{message} [{default_str}]: ").strip().lower()
            
            if not response:
                return default
            
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")
                
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            return False


def display_operation_summary(operation: str, stats: dict):
    """
    Display a summary of an operation's results.
    
    Args:
        operation: Name of the operation
        stats: Dictionary containing operation statistics
    """
    print(f"\n=== {operation} Summary ===")
    
    for key, value in stats.items():
        # Format the key for display
        display_key = key.replace('_', ' ').title()
        
        if isinstance(value, (int, float)):
            if 'time' in key.lower() or 'duration' in key.lower():
                if value < 60:
                    formatted_value = f"{value:.1f}s"
                else:
                    minutes = int(value // 60)
                    seconds = int(value % 60)
                    formatted_value = f"{minutes}m {seconds}s"
            elif 'size' in key.lower():
                if value > 1024 * 1024:
                    formatted_value = f"{value / (1024 * 1024):.1f} MB"
                elif value > 1024:
                    formatted_value = f"{value / 1024:.1f} KB"
                else:
                    formatted_value = f"{value} bytes"
            else:
                formatted_value = str(value)
        else:
            formatted_value = str(value)
        
        print(f"  {display_key}: {formatted_value}")


def show_processing_estimate(file_count: int, total_size_mb: float):
    """
    Show an estimate of processing time to the user.
    
    Args:
        file_count: Number of files to process
        total_size_mb: Total size in megabytes
    """
    # Rough estimates based on typical performance
    metadata_time = file_count * 2  # ~2 seconds per file
    conversion_time = total_size_mb * 2  # ~2 seconds per MB
    total_estimate = metadata_time + conversion_time
    
    print("\n📊 Processing Estimate:")
    print(f"   Files: {file_count}")
    print(f"   Total Size: {total_size_mb:.1f} MB")
    
    if total_estimate < 60:
        print(f"   Estimated Time: {int(total_estimate)} seconds")
    else:
        minutes = int(total_estimate // 60)
        seconds = int(total_estimate % 60)
        print(f"   Estimated Time: {minutes}m {seconds}s")
    
    print()


if __name__ == "__main__":
    # Test the progress tracking system
    print("Testing progress tracking...")
    
    # Test basic progress tracker
    
    items = list(range(10))
    progress = ProgressTracker(len(items), "Testing")
    
    for i, item in enumerate(items):
        time.sleep(0.1)  # Simulate work
        progress.update(1, f"Processing item {item}")
    
    progress.finish("All done!")
    
    # Test logger
    logger = Logger('INFO')
    logger.info("This is an info message")
    logger.debug("This is a debug message")
    logger.error("This is an error")
    
    print("\nProgress tracking system ready")