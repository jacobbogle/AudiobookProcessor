# -*- coding: utf-8 -*-
"""
Test that the metadata mapping integration is working correctly.
"""

import json
import os
import sys

# Add the audiobook_p directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(script_dir))


def test_metadata_mapping():
    """Test that metadata mapping is working correctly."""
    
    print("Testing metadata mapping integration...")
    
    # Load the mapping
    mapping_path = os.path.join('audiobook_p', 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
    
    # Count total fields from all sections
    total_fields = 0
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            total_fields += len(mapping[section])
    
    print("Loaded metadata mapping with %d fields across all sections" % total_fields)
    
    # Test a few key mappings from core metadata
    test_cases = [
        ('album', u'\\xa9alb'),
        ('artist', u'\\xa9ART'), 
        ('title', u'\\xa9nam'),
    ]
    
    core_metadata = mapping.get('core_metadata', {})
    
    for field_name, expected_mp4_tag in test_cases:
        if field_name in core_metadata:
            mutagen_keys = core_metadata[field_name].get('mutagen_keys', {})
            mp4_key = mutagen_keys.get('mp4', '')
            if expected_mp4_tag == mp4_key:
                print("  %s -> %s: OK" % (field_name, expected_mp4_tag))
            else:
                print("  %s -> %s: FAILED (found: %s)" % (field_name, expected_mp4_tag, mp4_key))
        else:
            print("  %s: MISSING from core metadata" % field_name)
    
    # Test audiobook-specific fields
    audiobook_metadata = mapping.get('audiobook_specific', {})
    if 'media_kind' in audiobook_metadata:
        media_kind = audiobook_metadata['media_kind']
        mp4_key = media_kind.get('mutagen_keys', {}).get('mp4', '')
        if mp4_key == 'stik':
            print("  media_kind -> stik: OK")
        else:
            print("  media_kind -> stik: FAILED (found: %s)" % mp4_key)
    
    print("Metadata mapping test complete!")

if __name__ == "__main__":
    test_metadata_mapping()