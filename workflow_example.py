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
import json
import sys

# Add the audiobook_p directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(script_dir))

from audiobook_p.main import (
    extract_metadata_from_folder,
    mutate_metadata,
    convert_folder_to_m4b,
    move_to_destination
)

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

    print("🎵 Processing audiobook: {}".format(os.path.basename(source_path)))
    print("📁 Source: {}".format(source_path))
    print("🎧 Output: {}".format(output_path))

    if album_prefix:
        print("🏷️  Album sort prefix: '{}'".format(album_prefix))
    if album_suffix:
        print("🏷️  Album suffix: '{}'".format(album_suffix))

    # Step 1: Extract metadata
    print("\n📊 Step 1: Extracting metadata...")
    try:
        metadata = extract_metadata_from_folder(str(source_path), "novel")
        print("✅ Found {} audio files".format(len(metadata['files'])))
    except Exception as e:
        print("❌ Failed to extract metadata: {}".format(e))
        return False
    except Exception as e:
        print("❌ Failed to extract metadata: {}".format(e))
        return False

    # Step 2: Mutate metadata (optional customization)
    print("\n🔄 Step 2: Applying metadata mutations...")
    try:
        # Create a temporary directory for mutated files
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_output = os.path.join(temp_dir, "mutated")

            # Mutate the metadata
            mutated_path = mutate_metadata(metadata, album_prefix, album_suffix)

            # Move to temp location
            final_mutated_path = move_to_destination(mutated_path, str(temp_output), "novel")

            print("✅ Metadata mutated and saved to: {}".format(final_mutated_path))

            # Step 3: Convert to M4B
            print("\n🎵 Step 3: Converting to M4B with chapters...")
            try:
                m4b_path = convert_folder_to_m4b(final_mutated_path, str(output_path))
                print("✅ Successfully created M4B file: {}".format(m4b_path))

                # Get file size
                file_size = os.path.getsize(m4b_path) / (1024 * 1024)  # MB
                print("📏 File size: {} MB".format(file_size:.1f))
                print("\n🎉 Audiobook processing complete!")
                print("📖 Final M4B file: {}".format(output_path))

                return True

            except Exception as e:
                print("❌ Failed to convert to M4B: {}".format(e))
                return False

    except Exception as e:
        print("❌ Failed to mutate metadata: {}".format(e))
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
        os.path.splitext(args)[1]
    )

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()