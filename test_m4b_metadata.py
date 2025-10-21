# -*- coding: utf-8 -*-
"""
Test script to verify metadata in the created M4B file.
"""

import os
import sys

# Add the audiobook_p directory to the path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, str(script_dir))

def test_m4b_metadata():
    """Test that the M4B file has the correct metadata."""
    
    try:
        from mutagen.mp4 import MP4
    except ImportError:
        print("Mutagen MP4 support not available")
        return
    
    m4b_path = '/Users/channingbogle/Desktop/Throne and Talon'
    
    if not os.path.exists(m4b_path):
        print("M4B file not found: {}".format(m4b_path))
        return
    
    try:
        audio = MP4(m4b_path)
        
        print("M4B Metadata:")
        if audio.tags:
            # Check for key metadata fields
            key_tags = {
                u'\xa9nam': 'Title',
                u'\xa9ART': 'Artist', 
                u'\xa9alb': 'Album',
                u'\xa9gen': 'Genre',
                u'\xa9day': 'Year',
                'aART': 'Album Artist',
                'stik': 'Media Kind',
                'trkn': 'Track',
                'disk': 'Disc',
                'chap': 'Chapters'
            }
            
            for tag, desc in key_tags.items():
                if tag in audio.tags:
                    value = audio.tags[tag]
                    print("  {}: {}".format(desc, value))
            
            # Check if chapters were added
            if 'chap' in audio.tags:
                chapters = audio.tags['chap']
                print("  Chapter count: {}".format(len(chapters)))
            
            print("\nAll MP4 tags:")
            for tag, value in audio.tags.items():
                print("  {}: {}".format(tag, value))
                
        else:
            print("No metadata found in M4B file")
            
    except Exception as e:
        print("Error reading M4B file: {}".format(e))

if __name__ == "__main__":
    test_m4b_metadata()