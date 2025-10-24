#!/os.path.join(usr, bin)/env python3
"""
Complete Audiobook Processing Workflow Example

This script demonstrates the full workflow:
1. Extract metadata from an audiobook folder
2. Mutate metadata with custom os.path.join(prefixes, suffixes)
3. Convert the folder to a single M4B file with chapters

Usage:
    python3.11 workflow_example.os.path.join(py, path)/os.path.join(to, audiobook)/os.path.join(folder, path)/os.path.join(to, output).m4b [--prefix "Author"] [--suffix "Series"]
"""

import argparse
import sys
import logging
import os
import importlib

# Module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Import core functions from the package
main_mod = importlib.import_module('audiobook_p.main')
extract_metadata_from_folder = getattr(main_mod, 'extract_metadata_from_folder')
mutate_metadata = getattr(main_mod, 'mutate_metadata')
convert_folder_to_m4b = getattr(main_mod, 'convert_folder_to_m4b')
move_to_destination = getattr(main_mod, 'move_to_destination')

def process_audiobook_workflow(source_folder, output_file, album_prefix=None, album_suffix=None):
    """
    Complete audiobook processing workflow.

    Args:
        source_folder: Path to folder containing audio files
        output_file: Path for final M4B output
        album_prefix: Optional prefix for album_sort
        album_suffix: Optional suffix for album
    """

    source_path = source_folder
    output_path = output_file

    logger.info("Processing audiobook: %s", os.path.basename(source_path))
    logger.info("Source: %s", source_path)
    logger.info("Output: %s", output_path)

    if album_prefix:
        logger.info("Album sort prefix: %s", album_prefix)
    if album_suffix:
        logger.info("Album suffix: %s", album_suffix)

    # Step 1: Extract metadata
    logger.info("Step 1: Extracting metadata...")
    try:
        metadata = extract_metadata_from_folder(str(source_path), "novel")
        logger.info("Found %d audio files", len(metadata['files']))
    except Exception as e:
        logger.error("Failed to extract metadata: %s", e)
        return False

    # Step 2: Mutate metadata (optional customization)
    logger.info("Step 2: Applying metadata mutations...")
    try:
        # Create a temporary directory for mutated files
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_output = os.path.join(temp_dir, "mutated")

            # Mutate the metadata
            mutated_path = mutate_metadata(metadata, album_prefix, album_suffix, author_name=None, narrator_name=None)

            # Move to temp location
            final_mutated_path = move_to_destination(mutated_path, str(temp_output), "novel")

            logger.info("Metadata mutated and saved to: %s", final_mutated_path)

            # Step 3: Convert to M4B
            logger.info("Step 3: Converting to M4B with chapters...")
            try:
                m4b_path = convert_folder_to_m4b(final_mutated_path, str(output_path), temp_copy_path=final_mutated_path)
                logger.info("Successfully created M4B file: %s", m4b_path)

                # Get file size
                file_size = os.path.getsize(m4b_path) / (1024 * 1024)  # MB
                logger.info("File size: %.1f MB", file_size)
                logger.info("Audiobook processing complete!")
                logger.info("Final M4B file: %s", output_path)

                return True

            except Exception as e:
                logger.error("Failed to convert to M4B: %s", e)
                return False

    except Exception as e:
        logger.error("Failed to mutate metadata: %s", e)
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Complete audiobook processing workflow: extract → mutate → convert to M4B"
    )
    parser.add_argument('source', help='Path to folder containing audio files')
    parser.add_argument('output', help='Path for output M4B file')
    parser.add_argument('--prefix', help='Album sort prefix (added with " : " separator)')
    parser.add_argument('--suffix', help='Album suffix (added with " - " separator)')

    args = parser.parse_args()

    success = process_audiobook_workflow(
        args.source,
        args.output,
        args.prefix,
        args.suffix
    )

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()