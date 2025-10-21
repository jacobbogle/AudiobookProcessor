# -*- coding: utf-8 -*-
"""
Progress tracking and user feedback for audiobook processing operations.
"""

import sys
import time
from typing import Optional, Callable, Any


class ProgressTracker:
    """Simple progress tracker for console applications"""
    
    def __init__(self, total: int, description: str = "Processing", show_percentage: bool = True):
        self.total = total
        self.current = 0
        self.description = description
        self.show_percentage = show_percentage
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, increment: int = 1, message: str = None):
        """Update progress by increment amount"""
        self.current += increment
        
        # Don't update more than once per 0.1 seconds to avoid spam
        current_time = time.time()
        if current_time - self.last_update < 0.1 and self.current < self.total:
            return
        
        self.last_update = current_time
        self._display_progress(message)
        
    def set_progress(self, current: int, message: str = None):
        """Set absolute progress value"""
        self.current = current
        self._display_progress(message)
        
    def _display_progress(self, message: str = None):
        """Display current progress"""
        if self.show_percentage:
            percentage = (self.current / self.total) * 100
            progress_str = f"{self.description}: {self.current}/{self.total} ({percentage:.1f}%)"
        else:
            progress_str = f"{self.description}: {self.current}/{self.total}"
        
        if message:
            progress_str += f" - {message}"
        
        # Add estimated time remaining
        if self.current > 0:
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
        
        # Clear line and print progress
        print(f"\r{progress_str:<80}", end="", flush=True)
        
        if self.current >= self.total:
            elapsed = time.time() - self.start_time
            print(f"\n✓ Completed in {elapsed:.1f}s")
    
    def finish(self, message: str = "Complete"):
        """Mark progress as finished"""
        self.current = self.total
        self._display_progress(message)


class Logger:
    """Simple logging for audiobook processing"""
    
    LEVELS = {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3
    }
    
    def __init__(self, level: str = 'INFO', show_timestamps: bool = False):
        self.level = self.LEVELS.get(level.upper(), 1)
        self.show_timestamps = show_timestamps
    
    def _log(self, level: str, message: str):
        """Internal logging method"""
        if self.LEVELS.get(level.upper(), 1) >= self.level:
            timestamp = ""
            if self.show_timestamps:
                timestamp = f"[{time.strftime('%H:%M:%S')}] "
            
            level_str = f"[{level.upper()}]"
            print(f"{timestamp}{level_str} {message}")
    
    def debug(self, message: str):
        """Log debug message"""
        self._log('DEBUG', message)
    
    def info(self, message: str):
        """Log info message"""
        self._log('INFO', message)
    
    def warning(self, message: str):
        """Log warning message"""
        self._log('WARNING', message)
    
    def error(self, message: str):
        """Log error message"""
        self._log('ERROR', message)


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
    
    print(f"\n📊 Processing Estimate:")
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
    import random
    
    items = list(range(10))
    progress = ProgressTracker(len(items), "Testing")
    
    for i, item in enumerate(items):
        time.sleep(0.1)  # Simulate work
        progress.update(1, f"Processing item {item}")
    
    progress.finish("All done!")
    
    # Test logger
    logger = Logger('INFO')
    logger.info("This is an info message")
    logger.warning("This is a warning")
    logger.error("This is an error")
    
    print("\nProgress tracking system ready")