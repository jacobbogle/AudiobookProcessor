# -*- coding: utf-8 -*-
"""
Simple progress tracking for Python 2.7 compatibility.
"""

import sys
import time

# Python 2/3 compatibility
try:
    # Python 2
    input_function = raw_input
except NameError:
    # Python 3
    input_function = input


class SimpleLogger:
    """Basic logging for audiobook processing"""
    
    def info(self, message):
        print("[INFO] {}".format(message))
    
    def warning(self, message):
        print("[WARNING] {}".format(message))
    
    def error(self, message):
        print("[ERROR] {}".format(message))


def simple_progress(current, total, description="Processing"):
    """Simple progress display"""
    import sys
    percentage = (current / float(total)) * 100
    sys.stdout.write("\r{}: {}/{} ({:.1f}%)".format(description, current, total, percentage))
    sys.stdout.flush()
    if current >= total:
        print()  # New line when complete


def ask_user_confirmation(message, default=False):
    """Ask user for yes/no confirmation"""
    default_str = "Y/n" if default else "y/N"
    
    try:
        # Python 2/3 compatibility
        try:
            response = input_function("{} [{}]: ".format(message, default_str)).strip().lower()
        except NameError:
            response = input("{} [{}]: ".format(message, default_str)).strip().lower()
        
        if not response:
            return default
        
        if response in ['y', 'yes']:
            return True
        elif response in ['n', 'no']:
            return False
        else:
            print("Please enter 'y' for yes or 'n' for no.")
            return ask_user_confirmation(message, default)
            
    except (KeyboardInterrupt, EOFError):
        print("\nOperation cancelled by user.")
        return False


def safe_operation(operation_name, operation_func, *args, **kwargs):
    """Execute an operation with error handling"""
    logger = SimpleLogger()
    
    try:
        logger.info("Starting {}...".format(operation_name))
        start_time = time.time()
        
        result = operation_func(*args, **kwargs)
        
        elapsed = time.time() - start_time
        logger.info("{} completed in {:.1f}s".format(operation_name, elapsed))
        
        return result
        
    except Exception as e:
        logger.error("{} failed: {}".format(operation_name, str(e)))
        return None


def show_processing_estimate(file_count, total_size_mb):
    """Show processing estimate"""
    metadata_time = file_count * 2
    conversion_time = total_size_mb * 2
    total_estimate = metadata_time + conversion_time
    
    print("\nProcessing Estimate:")
    print("   Files: {}".format(file_count))
    print("   Total Size: {:.1f} MB".format(total_size_mb))
    
    if total_estimate < 60:
        print("   Estimated Time: {} seconds".format(int(total_estimate)))
    else:
        minutes = int(total_estimate // 60)
        seconds = int(total_estimate % 60)
        print("   Estimated Time: {}m {}s".format(minutes, seconds))
    
    print()


def display_operation_summary(operation, stats):
    """Display operation summary"""
    print("\n=== {} Summary ===".format(operation))
    
    for key, value in stats.items():
        display_key = key.replace('_', ' ').title()
        
        if isinstance(value, (int, float)):
            if 'time' in key.lower() or 'duration' in key.lower():
                if value < 60:
                    formatted_value = "{:.1f}s".format(value)
                else:
                    minutes = int(value // 60)
                    seconds = int(value % 60)
                    formatted_value = "{}m {}s".format(minutes, seconds)
            elif 'size' in key.lower():
                if value > 1024 * 1024:
                    formatted_value = "{:.1f} MB".format(value / (1024 * 1024))
                elif value > 1024:
                    formatted_value = "{:.1f} KB".format(value / 1024)
                else:
                    formatted_value = "{} bytes".format(value)
            else:
                formatted_value = str(value)
        else:
            formatted_value = str(value)
        
        print("  {}: {}".format(display_key, formatted_value))


# For compatibility, create aliases
Logger = SimpleLogger
ProgressTracker = None  # Not implemented in simple version