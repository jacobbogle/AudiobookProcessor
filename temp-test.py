#!/usr/bin/env python3
"""
Temp command wrapper script.
This script runs the commands needed for testing audiobook processing functionality.
"""

import subprocess
import sys
import os
import logging

# Module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_command(cmd, description):
    """Run a command and print the result."""
    logger.info("=== %s ===", description)
    logger.debug("Command: %s", ' '.join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.getcwd())
        logger.info("Exit code: %s", result.returncode)
        if result.stdout:
            logger.info("STDOUT:\n%s", result.stdout)
        if result.stderr:
            logger.debug("STDERR:\n%s", result.stderr)
    except Exception as e:
        logger.error("Error running command: %s", e, exc_info=True)

def main():
    """Run the test commands for audiobook processing."""

    logger.info("Running audiobook processing tests...")

    # Test 1: Show help
    run_command([sys.executable, "audiobook-p-cli", "--help"], "Show help")

    # Test 2: Show info
    run_command([sys.executable, "audiobook-p-cli", "info"], "Show info")

    # Test 3: Extract metadata from test file
    test_file = "/tmp/test_convert/01 Master Imus's Transgression.mp3"
    if os.path.exists(test_file):
        run_command([sys.executable, "audiobook-p-cli", "extract", test_file], "Extract metadata from test file")
    else:
        logger.debug("Test file not found: %s", test_file)

    # Test 4: Convert test folder
    test_folder = "/tmp/test_convert"
    if os.path.exists(test_folder):
        output_file = "/tmp/test_output_temp.m4b"
        run_command([sys.executable, "audiobook-p-cli", "convert", test_folder, output_file], "Convert test folder to M4B")
    else:
        logger.debug("Test folder not found: %s", test_folder)

    # Test 6: Test mutate-convert operation
    if os.path.exists(test_folder):
        mutate_output_file = "/tmp/test_mutate_convert_temp.m4b"
        run_command([sys.executable, "audiobook-p-cli", "mutate-convert", test_folder, mutate_output_file], "Test mutate-convert operation")
        
    # Test 7: Test mutate operation
    if os.path.exists(test_folder):
        mutate_dest = "/tmp/test_mutate_output"
        run_command([sys.executable, "audiobook-p-cli", "mutate", test_folder, mutate_dest], "Test mutate operation")
        
        # Check if mutated files exist and have metadata
        if os.path.exists(mutate_dest):
            mutated_files = [f for f in os.listdir(mutate_dest) if f.endswith('.mp3')]
            if mutated_files:
                mutated_file_path = os.path.join(mutate_dest, mutated_files[0])
                run_command([sys.executable, "audiobook-p-cli", "extract", mutated_file_path], "Extract metadata from mutated file")

    # Test 9: Test capitalization on specific file
    test_file = "/Users/channingbogle/Desktop/The Throne of Lies/01 01 The Sea of Souls.m4a"
    if os.path.exists(test_file):
        run_command([sys.executable, "audiobook-p-cli", "extract", test_file], "Extract metadata from capitalization test file")
        
        # Test mutate-convert on the folder containing this file
        test_folder = "/Users/channingbogle/Desktop/The Throne of Lies"
        if os.path.exists(test_folder):
            output_file = "/tmp/test_capitalization.m4b"
            run_command([sys.executable, "audiobook-p-cli", "mutate-convert", test_folder, output_file], "Test mutate-convert with capitalization on Throne of Lies")
    else:
        logger.debug("Capitalization test file not found: %s", test_file)

    logger.info("All tests completed")

if __name__ == "__main__":
    main()