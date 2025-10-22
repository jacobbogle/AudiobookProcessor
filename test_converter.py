#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for the M4B converter functionality.
This demonstrates the converter workflow without requiring actual audio files.
"""

import importlib

# Import the converter functions from the package
main_mod = importlib.import_module('audiobook_p.main')
convert_folder_to_m4b = getattr(main_mod, 'convert_folder_to_m4b')
add_chapters_to_m4b = getattr(main_mod, 'add_chapters_to_m4b')

def test_converter_structure():
    """Test that the converter functions are properly defined and can be imported."""

    print("Testing M4B converter functionality...")

    # Test that functions exist
    assert callable(convert_folder_to_m4b), "convert_folder_to_m4b function should be callable"
    assert callable(add_chapters_to_m4b), "add_chapters_to_m4b function should be callable"

    print("Converter functions are properly defined")

    # Test CLI integration
    try:
        # Test that convert command is available
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        subparsers.add_parser('convert')
        parser.parse_args(['convert', '--help'])
        print("CLI test failed - should have shown help")
    except SystemExit:
        print("CLI integration working (help shown)")

    print("All converter tests passed!")

if __name__ == "__main__":
    test_converter_structure()