# -*- coding: utf-8 -*-
"""
Simple progress tracking for Python 2.7 compatibility.
"""

import sys
import time
import logging

# Python 2/3 compatibility: prefer raw_input if available, else input
try:
    import builtins
    input_function = getattr(builtins, 'raw_input', builtins.input)
except Exception:
    # Fallback: use input
    input_function = input


logger = logging.getLogger(__name__)


class SimpleLogger:
    """Basic logging adapter for audiobook processing"""

    def __init__(self, level=logging.INFO):
        self.logger = logging.getLogger('audiobook_p.simple')
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setLevel(level)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(level)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)


def simple_progress(current, total, description="Processing"):
    """Simple progress display"""
    percentage = (current / float(total)) * 100
    # Emit interactive progress only when stdout is a TTY; otherwise log the progress
    try:
        use_stdout = sys.stdout.isatty()
    except Exception:
        use_stdout = False

    progress_str = "{}: {}/{} ({:.1f}%)".format(description, current, total, percentage)
    if use_stdout:
        try:
            sys.stdout.write("\r" + progress_str)
            sys.stdout.flush()
            if current >= total:
                sys.stdout.write("\n")
                sys.stdout.flush()
        except Exception:
            logger.info(progress_str)
    else:
        logger.info(progress_str)


def ask_user_confirmation(message, default=False):
    """Ask user for yes/no confirmation"""
    default_str = "Y/n" if default else "y/N"
    try:
        response = input_function("{} [{}]: ".format(message, default_str)).strip().lower()
    except (KeyboardInterrupt, EOFError):
        logger.warning("Operation cancelled by user.")
        return False
    except Exception:
        # Fallback in case input_function is not available
        try:
            response = input("{} [{}]: ".format(message, default_str)).strip().lower()
        except Exception:
            return default

    if not response:
        return default

    if response in ['y', 'yes']:
        return True
    elif response in ['n', 'no']:
        return False
    else:
        logger.warning("Please enter 'y' for yes or 'n' for no.")
        return ask_user_confirmation(message, default)


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
    logger = SimpleLogger()
    logger.info("\nProcessing Estimate:")
    logger.info("   Files: %d", file_count)
    logger.info("   Total Size: {:.1f} MB".format(total_size_mb))

    if total_estimate < 60:
        logger.info("   Estimated Time: %d seconds", int(total_estimate))
    else:
        minutes = int(total_estimate // 60)
        seconds = int(total_estimate % 60)
        logger.info("   Estimated Time: %dm %ds", minutes, seconds)

    logger.info("")


def display_operation_summary(operation, stats):
    """Display operation summary"""
    logger = SimpleLogger()
    logger.info("\n=== %s Summary ===", operation)

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

        logger.info("  %s: %s", display_key, formatted_value)


# For compatibility, create aliases
Logger = SimpleLogger
ProgressTracker = None  # Not implemented in simple version