# Test the new metadata parsing and reformatting functions
import json
import os
import pytest
from audiobook_p.main import extract_metadata_from_file, parse_metadata_to_python_safe, reformat_tag_for_file_type

# Test with the MP3 file
file_path = "/tmp/test_convert/01 Master Imus's Transgression.mp3"

if not os.path.exists(file_path):
    pytest.skip(f"Sample file not found: {file_path}", allow_module_level=True)

# Extract raw metadata
raw_metadata = extract_metadata_from_file(file_path)
print("Raw metadata:")
print(json.dumps(raw_metadata, indent=2))

# Parse to Python-safe with tag associations
parsed = parse_metadata_to_python_safe(raw_metadata)
print("\nParsed metadata with tag associations:")
print(json.dumps(parsed, indent=2))

# Test reformatting for MP3 and MP4
print("\nReformatting examples:")
for desc_key, info in parsed.items():
    if info['value']:
        mp3_formatted = reformat_tag_for_file_type(desc_key, info['value'], 'mp3')
        mp4_formatted = reformat_tag_for_file_type(desc_key, info['value'], 'mp4')
        print("{}: MP3={!r}, MP4={!r}".format(desc_key, mp3_formatted, mp4_formatted))
