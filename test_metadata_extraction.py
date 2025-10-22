# This is a test metadata extraction file for the first audio file in The Throne of Lies
import os
import json
from audiobook_p.main import extract_metadata_from_file

file_path = "/Users/channingbogle/Desktop/The Throne of Lies/01 01 The Sea of Souls.m4a"

if not os.path.exists(file_path):
    import pytest
    pytest.skip(f"Sample file not found: {file_path}", allow_module_level=True)

metadata = extract_metadata_from_file(file_path)

with open("test_metadata_output.json", "w") as f:
    json.dump(metadata, f, indent=2)

print("Metadata extracted and written to test_metadata_output.json")
