"""Audiobook P - Main CLI entrypoint for audiobook processing"""

import glob
import os
import argparse
import json
import shutil
import sys
import tempfile
import logging

# Module logger
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Auto-install required packages
try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TIT1, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TPE2, TCOM, TPOS, TSOP, TSO2
except ImportError:
    logging.getLogger(__name__).warning("mutagen not installed. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mutagen"])
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1, TALB, TCON, TSOA, TSOT, TRCK, TMED, TPE2, TCOM, TPOS, TSOP, TSO2

# Optional utils functions: try to dynamically import audiobook_p.utils if available
try:
    import importlib
    utils_mod = importlib.import_module('audiobook_p.utils')
    novel_verify = getattr(utils_mod, 'novel_verify', None)
    series_verify = getattr(utils_mod, 'series_verify', None)
    batch_verify = getattr(utils_mod, 'batch_verify', None)
    book_title_logic = getattr(utils_mod, 'book_title_logic', None)
    remove_track_numbers = getattr(utils_mod, 'remove_track_numbers', None)
except Exception:
    # Fallback if utils module not present
    novel_verify = None
    series_verify = None
    batch_verify = None

    def remove_track_numbers(x):
        return x

    # Define book_title_logic locally
    def book_title_logic(title):
        """
        Remove track numbers from chapter titles.
        Examples:
        - "01 Chapter Title" -> "Chapter Title"
        - "1 Introduction" -> "Introduction" 
        - "01 01 The Beginning" -> "01 The Beginning" (removes first number)
        """
        import re
        if not title:
            return title
        # Remove the first leading track number and whitespace
        cleaned = re.sub(r'^(\d+\s+)', '', title)
        # Capitalize the first letter (find the first alphabetic character)
        if cleaned:
            # Find the first alphabetic character and capitalize it
            for i, char in enumerate(cleaned):
                if char.isalpha():
                    return cleaned[:i] + char.upper() + cleaned[i+1:]
            # If no alphabetic characters, return as-is
            return cleaned
        return cleaned


def extract_metadata_from_file(file_path):
    """
    Extract metadata from a single file using the combined-metadata-mapping.json.
    Returns a dict with descriptive keys and their values.
    """
    # Find the mapping file relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')

    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = mutagen.File(file_path)
    if audio is None:
        raise ValueError("Could not load audio file: {}".format(file_path))

    extracted = {}
    
    # Combine all metadata sections from the new mapping structure
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    for desc_key, info in all_fields.items():
        # Get mutagen keys from the new structure
        mutagen_keys = info.get('mutagen_keys', {})
        tags = []
        
        # Add both MP4 and ID3 tags if available
        if 'mp4' in mutagen_keys:
            tags.append(mutagen_keys['mp4'])
        if 'id3' in mutagen_keys:
            tags.append(mutagen_keys['id3'])
            
        # Handle special cases for cover art
        if desc_key in ['picture', 'cover_art']:
            tags.extend(['covr', 'APIC:'])
        
        value = None

        # Helper: generate candidate key variants for matching
        def generate_key_variants(tag_literal):
            variants = []
            # Add the original
            variants.append(tag_literal)
            try:
                if isinstance(tag_literal, str):
                    # If mapping used escaped unicode like "\\xa9nam", decode to real unicode
                    if '\\x' in tag_literal:
                        decoded = tag_literal.encode('ascii').decode('unicode_escape')
                        variants.append(decoded)
                        # Also add latin-1 encoded bytes and utf-8 decoded forms
                        try:
                            variants.append(decoded.encode('latin-1'))
                        except Exception:
                            pass
                        try:
                            variants.append(decoded.encode('utf-8'))
                        except Exception:
                            pass
                    # Also try common plain forms
                    try:
                        variants.append(tag_literal.encode('latin-1'))
                    except Exception:
                        pass
                    try:
                        variants.append(tag_literal.encode('utf-8'))
                    except Exception:
                        pass
            except Exception:
                pass
            return variants

        # Collect available tag keys from the file (as-is)
        available_keys = list(audio.tags.keys()) if hasattr(audio, 'tags') and audio.tags else []

        # Build a flat list of candidate keys from mapping tags
        candidates = []
        for tag in tags:
            candidates.extend(generate_key_variants(tag))

        # Also include direct lookup for common MP4 and ID3 names
        # Iterate available keys and try to match candidates in several normalized ways
        found_key = None
        # Special handling for COMM frames - collect all COMM frames and choose the best one
        if desc_key.lower() == "comment":
            comm_frames = []
            for ak in available_keys:
                if ak.startswith("COMM:"):
                    try:
                        raw_value = audio.tags[ak]
                        comm_frames.append((ak, raw_value))
                    except Exception as e:
                        logger.debug("Error reading COMM frame %s: %s", ak, e)
                        continue
            
            # Choose the best COMM frame: prefer ones without description, or with longest text
            if comm_frames:
                best_frame = None
                best_text = ""
                for ak, raw_value in comm_frames:
                    text_value = ""
                    if isinstance(raw_value, list) and len(raw_value) > 0:
                        item = raw_value[0]
                        if hasattr(item, 'text'):
                            text_value = str(item.text)
                        else:
                            text_value = str(item)
                    elif hasattr(raw_value, 'text'):
                        text_value = str(raw_value.text)
                    else:
                        text_value = str(raw_value)
                    
                    # Prefer frames without description (just "COMM::eng") or with longer text
                    if "::" in ak and len(text_value) > len(best_text):
                        best_frame = ak
                        best_text = text_value
                    elif not best_frame and len(text_value) > len(best_text):
                        best_frame = ak
                        best_text = text_value
                
                if best_frame:
                    found_key = best_frame
        
        # If not a COMM frame or no special handling triggered, use normal matching
        if found_key is None:
            for candidate in candidates:
                for ak in available_keys:
                    try:
                        # Direct equality
                        if ak == candidate:
                            found_key = ak
                            break
                        # Special handling for COMM frames (comments) - match "COMM" with "COMM:*"
                        if candidate == "COMM" and ak.startswith("COMM:"):
                            found_key = ak
                            break
                        # Compare string forms
                        if isinstance(ak, bytes) and isinstance(candidate, str):
                            if ak.decode('utf-8', errors='ignore') == candidate:
                                found_key = ak
                                break
                        if isinstance(candidate, bytes) and isinstance(ak, str):
                            if candidate.decode('utf-8', errors='ignore') == ak:
                                found_key = ak
                                break
                        # Compare repr/raw representation
                        if str(ak) == str(candidate):
                            found_key = ak
                            break
                    except Exception:
                        continue
                if found_key is not None:
                    break

        # If we found a matching key, extract its value
        if found_key is not None:
            raw_value = audio.tags[found_key]
            # Reuse existing normalization logic for raw_value
            if isinstance(raw_value, list):
                if len(raw_value) > 0:
                    item = raw_value[0]
                    if isinstance(item, (str, int, float)):
                        value = item
                    elif hasattr(item, 'text'):
                        text_value = item.text
                        if isinstance(text_value, list) and len(text_value) > 0:
                            value = text_value[0]
                        else:
                            value = text_value
                    else:
                        # Binary data (cover art)
                        if desc_key in ['picture', 'cover_art']:
                            value = 'Present'
            elif isinstance(raw_value, (str, int, float)):
                value = raw_value
            elif hasattr(raw_value, 'text'):
                text_value = raw_value.text
                if isinstance(text_value, list) and len(text_value) > 0:
                    value = text_value[0]
                else:
                    value = text_value
            else:
                # Fallback for binary objects
                if desc_key in ['picture', 'cover_art']:
                    value = 'Present'

        # If still not found, as a last resort try direct attribute access
        if value is None:
            for tag in tags:
                try:
                    if hasattr(audio, tag):
                        raw_value = getattr(audio, tag)
                        if isinstance(raw_value, (str, int, float)):
                            value = raw_value
                            break
                        if isinstance(raw_value, list) and len(raw_value) > 0:
                            item = raw_value[0]
                            if isinstance(item, (str, int, float)):
                                value = item
                                break
                            if hasattr(item, 'text'):
                                value = item.text
                                break
                except Exception:
                    continue

        # If no value found, use empty
        if value is None:
            value = ''

        # Additional handling for MP4Cover objects and other binary data
        try:
            from mutagen.mp4 import MP4Cover
            if isinstance(value, MP4Cover):
                extracted[desc_key] = 'Present'
            else:
                extracted[desc_key] = value
        except ImportError:
            # If mutagen.mp4 is not available, just use the value
            extracted[desc_key] = value

    return extracted


def parse_metadata_to_python_safe(metadata_dict):
    """
    Parse metadata dict from extract_metadata_from_file into a Python-safe dataset
    with MP3 and M4A tag associations for each descriptive key.

    Args:
        metadata_dict: Dict from extract_metadata_from_file with desc_keys as keys

    Returns:
        Dict with desc_key -> {'mp3': mutagen_key, 'mp4': mutagen_key, 'value': python_safe_value}
    """
    # Load the mapping
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Combine all fields
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    result = {}
    for desc_key, value in metadata_dict.items():
        if desc_key in all_fields:
            info = all_fields[desc_key]
            mutagen_keys = info.get('mutagen_keys', {})
            mp3_key = mutagen_keys.get('id3', '')
            mp4_key = mutagen_keys.get('mp4', '')
            # Normalize value to Python-safe (string, int, etc.)
            python_value = value
            if isinstance(value, list) and len(value) > 0:
                python_value = value[0]
            if hasattr(python_value, 'text'):
                python_value = python_value.text
            # Handle string types (Python 3 only in this project)
            string_types = (str,)

            if isinstance(python_value, string_types):
                # Already a string type, keep as-is
                pass
            elif isinstance(python_value, bytes):
                # Bytes that need decoding
                try:
                    python_value = python_value.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        python_value = python_value.decode('latin-1')
                    except UnicodeDecodeError:
                        python_value = str(python_value)
            else:
                # For other types, convert to string
                python_value = str(python_value)
            
            # Add the processed value to result
            result[desc_key] = {
                'mp3': mp3_key,
                'mp4': mp4_key,
                'value': python_value
            }
    return result


def reformat_tag_for_file_type(desc_key, python_value, file_type):
    """
    Reformat a Python-safe tag value back to the proper format for the given file type (mp3 or mp4).

    Args:
        desc_key: Descriptive key (e.g., 'title')
        python_value: Python-safe value (string, int, etc.)
        file_type: 'mp3' or 'mp4'

    Returns:
        Properly formatted value for setting in the file
    """
    # Load the mapping
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Combine all fields
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    if desc_key not in all_fields:
        return python_value

    info = all_fields[desc_key]
    data_types = info.get('data_types', {})

    if file_type.lower() == 'mp3':
        dt = data_types.get('id3', 'text_string_with_encoding')
        if dt == 'text_string_with_encoding':
            # For ID3, mutagen handles encoding, just return the string
            return python_value
        elif dt == 'numeric_string':
            return str(python_value)
        else:
            return python_value
    elif file_type.lower() == 'mp4':
        dt = data_types.get('mp4', 'utf8_text')
        if dt == 'utf8_text':
            # Return a list containing the string representation for MP4 text fields
            return [str(python_value)]
        elif dt == 'integer':
            # Accept strings like "1/1" or stringified lists and extract the first integer.
            try:
                # If passed a list (e.g., ['1/1']), use its first element
                if isinstance(python_value, list) and len(python_value) > 0:
                    python_value = python_value[0]
                # Normalize bytes to str
                if isinstance(python_value, bytes):
                    try:
                        s = python_value.decode('utf-8')
                    except Exception:
                        s = python_value.decode('latin-1', errors='ignore')
                else:
                    s = str(python_value)

                # Find the first integer in the string (handles '1/1', "['1/1']", etc.)
                import re
                m = re.search(r"(\d+)", s)
                if m:
                    return [int(m.group(1))]
                # Fallback: try direct int conversion
                try:
                    return [int(python_value)]
                except Exception:
                    return [0]
            except Exception:
                return [0]
        elif dt == 'boolean':
            return [bool(python_value)]
        elif dt == 'tuple_of_ints':
            # Handle track/disc numbers like "1/12" or tuple
            # Normalize detection to Python 3 string types
            # If passed a list like ['1/12'], unwrap it
            if isinstance(python_value, list) and len(python_value) > 0:
                python_value = python_value[0]
            is_string = isinstance(python_value, str)
            
            if is_string and '/' in python_value:
                parts = python_value.split('/')
                try:
                    return [(int(parts[0]), int(parts[1]))]
                except (ValueError, IndexError):
                    return [(int(python_value) if python_value.isdigit() else 0, 0)]
            elif isinstance(python_value, tuple):
                return [python_value]
            else:
                # Single number, assume it's the first part of a tuple
                try:
                    return [(int(python_value), 0)]
                except ValueError:
                    return [(0, 0)]
        elif dt == 'list_of_mp4cover':
            # For cover art, assume python_value is 'Present' or actual data
            return python_value  # Handle separately
        else:
            return [str(python_value)]
    else:
        return python_value


def _determine_track_value_for_sources(source_files, MutagenFile):
    """
    Determine the MP4-style trkn value for the final M4B based on source files.

    Preference order:
      1) If the first source has an MP4 'trkn', use that value.
      2) If the first source exposes an ID3 'TRCK' (or variant), parse and convert it.
      3) Otherwise, derive from the index of the first source (1-based) and total.

    Returns: (track_val, track_written)
      - track_val: value suitable to assign to MP4 tags['trkn'] (e.g. [(n,total)])
      - track_written: True if value came from explicit source metadata (so default fallback should not overwrite)
    """
    total = len(source_files) if source_files else 0
    if not source_files or len(source_files) == 0:
        return ([(1, total if total else 0)], False)

    first = source_files[0]
    try:
        fa = MutagenFile(first)
    except Exception:
        fa = None

    # Prefer MP4 trkn if present
    if fa and hasattr(fa, 'tags') and fa.tags:
        try:
            if 'trkn' in fa.tags:
                try:
                    logger.debug("DBG: _determine_track_value_for_sources found MP4 trkn: %r on %s", fa.tags.get('trkn'), first)
                except Exception:
                    pass
                return (fa.tags['trkn'], True)
        except Exception:
            pass

        # Look for ID3-like TRCK keys (case-insensitive prefix match)
        try:
            for ak in list(fa.tags.keys()):
                try:
                    if isinstance(ak, str) and ak.upper().startswith('TRCK'):
                        raw = fa.tags[ak]
                        try:
                            logger.debug("DBG: _determine_track_value_for_sources found ID3 TRCK raw=%r on %s", raw, first)
                        except Exception:
                            pass
                        formatted = reformat_tag_for_file_type('track_number', raw, 'mp4')
                        try:
                            logger.debug("DBG: _determine_track_value_for_sources formatted TRCK -> %r", formatted)
                        except Exception:
                            pass
                        return (formatted, True)
                except Exception:
                    continue
        except Exception:
            pass

    # Fallback: derive from index of first source in the list
    try:
        first_name = os.path.basename(first)
        idx = 0
        for i, sf in enumerate(source_files):
            if os.path.basename(sf) == first_name:
                idx = i
                break
        return ([(int(idx) + 1, int(total) if total else 0)], False)
    except Exception:
        return ([(1, int(total) if total else 0)], False)


def sanitize_metadata_value(val):
    """
    Normalize metadata values into reasonable Python types:
    - Unwrap stringified lists like "['1/1']" -> '1/1'
    - Decode bytes to utf-8 where appropriate
    - Leave bytes (image data) alone
    - For lists of one element, return the element (caller will wrap as needed)
    """
    import re
    # If it's already bytes or tuple or list, return as-is (but decode inner bytes)
    if isinstance(val, bytes):
        return val
    if isinstance(val, tuple):
        return val
    if isinstance(val, list):
        # simplify single-element lists
        if len(val) == 0:
            return val
        if len(val) == 1:
            return sanitize_metadata_value(val[0])
        # sanitize each element
        return [sanitize_metadata_value(x) for x in val]

    # If it's a mutagen object with .data, prefer that raw data
    try:
        if hasattr(val, 'data'):
            return val.data
    except Exception:
        pass

    # If it's a string that looks like a python list literal, try to eval safely
    if isinstance(val, str):
        stripped = val.strip()
        # common pattern: "['1/1']" or '["1/1"]'
        if stripped.startswith('[') and stripped.endswith(']'):
            # attempt to extract inner quoted value(s)
            items = re.findall(r"'([^']*)'|\"([^\"]*)\"", stripped)
            # items is list of tuples from alternation; flatten
            flat = [a if a else b for a, b in items if a or b]
            if len(flat) == 1:
                return sanitize_metadata_value(flat[0])
            if len(flat) > 1:
                return [sanitize_metadata_value(x) for x in flat]

        # If it's bytes-as-string (b'...'), try to decode
        if stripped.startswith("b'") or stripped.startswith('b"'):
            try:
                # remove leading b' and trailing '
                inner = stripped[2:]
                if inner.startswith("'") or inner.startswith('"'):
                    inner = inner[1:-1]
                return inner
            except Exception:
                pass

        # Otherwise return the string as-is
        return val

    # Last resort: convert to str
    try:
        return str(val)
    except Exception:
        return val


def parse_series_index_from_folder_name(folder_name):
    """
    Try to extract a numeric series/volume/book index from a folder name.

    Examples it recognizes:
      - "Book 03" -> 3
      - "Vol. 2" -> 2
      - "Volume 10" -> 10
      - "#4" -> 4
      - "Book 2 of 12" -> 2

    Returns an int if found, otherwise None.
    """
    import re
    if not folder_name or not isinstance(folder_name, str):
        return None

    s = folder_name
    # Remove any bracketed content (e.g., {..}, [..], (..), <..>) which often
    # contains volume/edition noise. Replace with a space so surrounding tokens
    # remain separated.
    try:
        # First, inspect bracketed segments for explicit numbers like '{Vol - 3}'
        bracket_re = re.compile(r'\{([^}]*)\}|\[([^\]]*)\]|\(([^)]*)\)|<([^>]*)>')
        for m in bracket_re.finditer(s):
            # m.groups() will contain the captured content in one of the positions
            inner = next((g for g in m.groups() if g), None)
            if inner:
                # Look for a number inside the bracket content
                mnum = re.search(r'(?:book|vol(?:ume)?|v)?\s*[:\.]?\s*(\d{1,3})', inner, re.IGNORECASE)
                if mnum:
                    try:
                        return int(mnum.group(1))
                    except Exception:
                        pass
        # If no number found inside brackets, remove the bracketed segments
        s = re.sub(r'\{[^}]*\}|\[[^\]]*\]|\([^)]*\)|<[^>]*>', ' ', s)
    except Exception:
        # If the regex fails for whatever reason, fall back to original
        s = folder_name

    # Normalize separators and whitespace
    s = re.sub(r'[\._]', ' ', s)
    s = re.sub(r'[-]+', ' ', s)
    s = s.lower().strip()

    # Helper: convert simple roman numerals (I..MMM) to int
    def _roman_to_int(r):
        r = r.upper()
        vals = {'I':1,'V':5,'X':10,'L':50,'C':100,'D':500,'M':1000}
        total = 0
        prev = 0
        for ch in reversed(r):
            v = vals.get(ch, 0)
            if v < prev:
                total -= v
            else:
                total += v
            prev = v
        return total

    # Word-number map for simple English words up to twenty
    WORD_NUM = {
        'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
        'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20
    }

    # Recognize patterns like 'Vol IX' or 'Book IV' (roman numerals)
    try:
        m_roman = re.search(r'\b(?:book|vol(?:ume)?|v)\b[\s\.:\-]*?([ivxlcdm]{1,7})\b', s, re.IGNORECASE)
        if m_roman:
            try:
                val = _roman_to_int(m_roman.group(1))
                if val > 0:
                    return val
            except Exception:
                pass
        # Also accept a standalone roman numeral token if no prefix
        m_roman_standalone = re.search(r'\b([ivxlcdm]{1,7})\b', s, re.IGNORECASE)
        if m_roman_standalone:
            try:
                val = _roman_to_int(m_roman_standalone.group(1))
                if val > 0:
                    return val
            except Exception:
                pass
    except Exception:
        pass

    # Recognize spelled-out English numbers (supports hyphenated and compound numbers)
    try:
        def _words_to_int(text):
            if not text or not isinstance(text, str):
                return None
            # Tokenize on spaces and hyphens
            tokens = re.split(r'[\s-]+', text.lower())

            units = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9}
            teens = {'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19}
            tens = {'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
            mags = {'hundred':100, 'thousand':1000}

            total = 0
            current = 0
            matched = False
            for t in tokens:
                if not t:
                    continue
                if t in units:
                    current += units[t]
                    matched = True
                elif t in teens:
                    current += teens[t]
                    matched = True
                elif t in tens:
                    current += tens[t]
                    matched = True
                elif t in mags:
                    matched = True
                    # Apply magnitude
                    if current == 0:
                        current = 1
                    current *= mags[t]
                    total += current
                    current = 0
                else:
                    # Unknown token: bail out
                    return None
            if not matched:
                return None
            return total + current

        # Try patterns like 'Volume twenty-one' or 'Book two hundred and three'
        m_word = re.search(r'\b(?:book|vol(?:ume)?|v|volume|band|teil|livre|episode|disc)\b[\s\.:\-]*?([a-z\s\-]+)\b', s, re.IGNORECASE)
        if m_word:
            try:
                candidate = m_word.group(1).strip()
                # try simple map first
                if candidate in WORD_NUM:
                    return int(WORD_NUM[candidate])
                # try compound parsing
                num = _words_to_int(candidate.replace(' and ', ' '))
                if num is not None:
                    return int(num)
            except Exception:
                pass

        # fallback: scan for any compound spelled-out number token in the string
        # (matches hyphenated or spaced numbers like 'twenty-one' or 'two hundred')
        m_word2 = re.search(r'\b([a-z]+(?:[\s-][a-z]+)*)\b', s, re.IGNORECASE)
        if m_word2:
            try:
                token = m_word2.group(1).strip()
                if token in WORD_NUM:
                    return int(WORD_NUM[token])
                num = _words_to_int(token.replace(' and ', ' '))
                if num is not None:
                    return int(num)
            except Exception:
                pass
    except Exception:
        pass

    # Patterns to match common forms like:
    #  - Leading numeric prefixes: '01 - Title', '1 Title', '01. Title'
    #  - Vol/Volume/Book/v followed by number: 'Vol.1', 'volume-1', 'book 03', 'v3'
    #  - Hash-prefixed: '#4'
    #  - '2 of 12' style
    patterns = [
        r'^\s*(\d{1,3})\b',
        r'\b(?:book|vol(?:ume)?|v)\b[\s\.:\-]*?(\d{1,3})\b',
        r'#\s*(\d{1,3})\b',
        r'\b(\d{1,3})\s*(?:of|/)\s*\d{1,3}\b',
        r'\bpart\s*(\d{1,3})\b'
    ]

    for p in patterns:
        try:
            m = re.search(p, s)
        except Exception:
            m = None
        if m:
            try:
                return int(m.group(1))
            except Exception:
                continue

    # Fallback: any standalone number token (avoid matching years/long numbers)
    try:
        m = re.search(r'\b(\d{1,3})\b', s)
    except Exception:
        m = None
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None

    return None


def clean_album_name(name):
    """Clean a folder name to use as an album/book title.

    Removes common leading numbering (e.g. "01 -", "(01)", "1 ") and
    returns a title-cased string suitable for an album name.
    """
    import re
    if not name or not isinstance(name, str):
        return name

    # Remove leading numeric prefixes like '01 -', '1 ', '(01) ', '01. '
    cleaned = re.sub(r'^\s*(?:\(|)?\d{1,3}(?:\)|)?(?:\s|-|\.|:)+', '', name)
    cleaned = cleaned.strip()

    # If nothing left, return original trimmed name
    if not cleaned:
        return name.strip()

    # Title-case the result (simple but effective for album names)
    return cleaned.title()


def sanitize_series_name(name):
    """Sanitize user-provided series name for consistent tagging and sorting.

    - Applies book_title_logic
    - Removes leading punctuation and numeric prefixes
    - Collapses multiple spaces
    - Returns None for empty/invalid input
    """
    import re
    if not name:
        return None
    try:
        # Prefer book_title_logic to normalize casing and remove track numbers
        s = book_title_logic(name)
    except Exception:
        s = str(name)

    s = s.strip()
    if not s:
        return None

    # Remove leading punctuation/underscores/spaces
    s = re.sub(r'^[\-\._\s]+', '', s)
    # Remove leading numeric prefixes like '01 -', '1 ', '01.'
    s = re.sub(r'^\d{1,3}[\s\-:\._]+', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s{2,}', ' ', s).strip()

    return s if s else None


def natural_sort_key(filename):
    """
    Generate a sort key for natural sorting (handles numbers correctly).
    E.g., "Chapter 2.mp3" < "Chapter 10.mp3"
    """
    import re
    # Split into parts: alternating strings and numbers
    parts = re.split(r'(\d+)', filename)
    # Convert numeric parts to integers for proper sorting
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def track_number_sort_key(file_path, metadata_dict):
    """
    Generate a sort key for sorting by track number (with filename fallback).
    
    Args:
        file_path: Path to the audio file
        metadata_dict: Metadata dictionary for the file
        
    Returns:
        Tuple: (priority, sort_value) where priority 0 = track number, 1 = filename
    """
    # Try to get track number from metadata
    track_number = metadata_dict.get('track_number')
    
    if track_number:
        # Handle different formats
        if isinstance(track_number, tuple) and len(track_number) >= 1:
            # MP4 format: (track, total)
            return (0, track_number[0])
        elif isinstance(track_number, str):
            # MP3 format: "1" or "1/12"
            track_str = track_number.split('/')[0]  # Take first part if "1/12"
            try:
                return (0, int(track_str))
            except ValueError:
                pass  # Fall through to filename sorting
    
    # Fallback to filename-based natural sorting
    filename = os.path.basename(file_path)
    return (1, natural_sort_key(filename))


def extract_metadata_from_folder(folder_path, folder_type, sort_by='filename'):
    """
    Extract metadata from all audio files in a folder.
    Returns a dict with folder type, folder path, and file paths as keys with their metadata as values.
    """
    folder_path = folder_path
    if not os.path.isdir(folder_path):
        raise ValueError("Path is not a directory: {}".format(folder_path))

    # Find all audio files in the folder
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))

    if not audio_files:
        raise ValueError("No audio files found in: {}".format(folder_path))

    # Sort files based on sort_by parameter
    if sort_by == 'track':
        # Extract metadata first to get track numbers
        file_metadata = {}
        for audio_file in audio_files:
            try:
                metadata = extract_metadata_from_file(str(audio_file))
                file_metadata[str(audio_file)] = metadata
            except Exception as e:
                file_metadata[str(audio_file)] = {"error": str(e)}
        
        # Sort by track number with filename fallback
        audio_files.sort(key=lambda f: track_number_sort_key(f, file_metadata.get(str(f), {})))
    else:
        # Default: sort by filename naturally
        audio_files.sort(key=natural_sort_key)

    results = {}
    for audio_file in audio_files:
        try:
            metadata = extract_metadata_from_file(str(audio_file))
            results[str(audio_file)] = metadata
        except Exception as e:
            results[str(audio_file)] = {"error": str(e)}

    return {
        "folder_type": folder_type,
        "folder": str(folder_path),
        "files": results
    }


def copy_folder(source_path, max_attempts=5):
    """
    Copy a folder to a temporary location with retry logic.

    Args:
        source_path: Path to the folder to copy
        max_attempts: Maximum number of copy attempts (default: 5)

    Returns:
        Path to the temporary folder on success, None on failure after all attempts
    """
    source_path = source_path

    # Validate source path
    if not os.path.exists(source_path) or not os.path.isdir(source_path):
        return None

    for attempt in range(max_attempts):
        try:
            # Create a temporary directory
            temp_dir = tempfile.mkdtemp(prefix="audiobook_copy_")
            temp_path = temp_dir

            # Copy the entire folder
            dest_path = os.path.join(temp_path, os.path.basename(source_path))
            try:
                # Try Python 3 version first
                shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            except TypeError:
                # Python 2.7 doesn't have dirs_exist_ok parameter
                shutil.copytree(source_path, dest_path)

            # Return the path to the copied folder
            return str(dest_path)

        except Exception:
            # Clean up failed temp directory if it was created
            try:
                if 'temp_path' in locals():
                    shutil.rmtree(temp_path, ignore_errors=True)
            except Exception:
                pass

            # If this was the last attempt, return None
            if attempt == max_attempts - 1:
                return None

            # Otherwise continue to next attempt
            continue

    # This should never be reached, but just in case
    return None


def apply_metadata_to_file(file_path, metadata_dict):
    """
    Apply metadata changes to an audio file using the combined-metadata-mapping.json.

    Args:
        file_path: Path to the audio file
        metadata_dict: Dict with descriptive keys and values to apply
    """
    # Find the mapping file relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    
    # Load the mapping
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Load the audio file
    audio = mutagen.File(file_path)
    if audio is None:
        raise ValueError("Could not load audio file: {}".format(file_path))

    # Check if this is an MP3 file
    is_mp3 = isinstance(audio, MP3)
    
    # For MP3 files, preserve original APIC data before saving
    original_apic_data = {}
    if is_mp3 and hasattr(audio, 'tags') and audio.tags is not None:
        # Extract original APIC frames to preserve them
        for tag_name in list(audio.tags.keys()):
            if tag_name.startswith('APIC'):
                original_apic_data[tag_name] = audio.tags[tag_name]
    
    # Combine all metadata sections from the new mapping structure
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    # Apply each metadata field
    for desc_key, value in metadata_dict.items():
        if desc_key not in all_fields:
            continue

        info = all_fields[desc_key]
        mutagen_keys = info.get('mutagen_keys', {})
        
        # Skip if value is None or empty (except for picture which we preserve)
        if value is None or (isinstance(value, str) and not value.strip()):
            if desc_key != 'picture':  # Always preserve picture
                continue

        # Helper: decode MP4 mapping keys like "\\xa9nam" -> "©nam"
        def _decode_mp4_key(k):
            try:
                if isinstance(k, str) and '\\x' in k:
                    return k.encode('ascii').decode('unicode_escape')
            except Exception:
                pass
            return k

        # Get appropriate tags based on file format (decode MP4 keys before use)
        tags_to_try = []
        if is_mp3 and 'id3' in mutagen_keys:
            tags_to_try.append(mutagen_keys['id3'])
        elif not is_mp3 and 'mp4' in mutagen_keys:
            # Decode escaped MP4 atom names stored in mapping (e.g. "\\xa9nam")
            tags_to_try.append(_decode_mp4_key(mutagen_keys['mp4']))
        
        # Determine file type for reformatting
        file_type = 'mp3' if is_mp3 else 'mp4'
        
        # Use the utility function to reformat the value
        formatted_value = reformat_tag_for_file_type(desc_key, value, file_type)
        
        # Apply to each tag
        for tag in tags_to_try:
            try:
                if is_mp3 and hasattr(audio, 'tags') and audio.tags is not None:
                    # MP3 files need proper ID3 frames
                    if tag == 'TIT2':
                        audio.tags.add(TIT2(encoding=3, text=formatted_value))
                    elif tag == 'TIT1':
                        audio.tags.add(TIT1(encoding=3, text=formatted_value))
                    elif tag == 'TPE1':
                        audio.tags.add(TPE1(encoding=3, text=formatted_value))
                    elif tag == 'TALB':
                        audio.tags.add(TALB(encoding=3, text=formatted_value))
                    elif tag == 'TCON':
                        audio.tags.add(TCON(encoding=3, text=formatted_value))
                    elif tag == 'TPE2':
                        audio.tags.add(TPE2(encoding=3, text=formatted_value))
                    elif tag == 'TCOM':
                        audio.tags.add(TCOM(encoding=3, text=formatted_value))
                    elif tag == 'TRCK':
                        audio.tags.add(TRCK(encoding=3, text=formatted_value))
                    elif tag == 'TPOS':
                        audio.tags.add(TPOS(encoding=3, text=formatted_value))
                    elif tag == 'TSOA':
                        audio.tags.add(TSOA(encoding=3, text=formatted_value))
                    elif tag == 'TSOT':
                        audio.tags.add(TSOT(encoding=3, text=formatted_value))
                    elif tag == 'TSOP':
                        audio.tags.add(TSOP(encoding=3, text=formatted_value))
                    elif tag == 'TSO2':
                        audio.tags.add(TSO2(encoding=3, text=formatted_value))
                    elif tag == 'TMED':
                        audio.tags.add(TMED(encoding=3, text=formatted_value))
                    # Skip other tags for now
                elif hasattr(audio, 'tags') and audio.tags is not None:
                    # Handle different tag types for other formats (MP4/M4A/M4B)
                    if desc_key == 'picture':
                        # Preserve existing picture data
                        if tag in audio.tags:
                            continue  # Don't overwrite existing pictures
                    else:
                        # Debug: log attempt to set tag
                        try:
                            logger.debug("Setting tag %r -> %r (type %s) on %s", tag, formatted_value, type(formatted_value), file_path)
                        except Exception:
                            pass
                        # Prepare write key (ensure freeform atoms are handled)
                        write_key = tag
                        # If this is a freeform '----:' atom we must write bytes payloads
                        try:
                            if isinstance(write_key, str) and write_key.startswith('----:'):
                                def _ensure_bytes(x):
                                    if isinstance(x, bytes):
                                        return x
                                    if isinstance(x, str):
                                        return x.encode('utf-8')
                                    try:
                                        return str(x).encode('utf-8')
                                    except Exception:
                                        return b''

                                if isinstance(formatted_value, list):
                                    audio.tags[write_key] = [_ensure_bytes(x) for x in formatted_value]
                                else:
                                    audio.tags[write_key] = [_ensure_bytes(formatted_value)]
                            else:
                                # Apply the formatted value directly for normal MP4 atoms
                                audio.tags[write_key] = formatted_value

                        except Exception:
                            # Fallback: attempt direct assignment
                            try:
                                audio.tags[tag] = formatted_value
                            except Exception:
                                pass
                        # For best compatibility with Apple tools, also mirror grouping to freeform SERIES
                        try:
                            if desc_key == 'grouping':
                                series_key = '----:com.apple.iTunes:SERIES'
                                try:
                                    from mutagen.mp4 import MP4FreeForm
                                    if isinstance(formatted_value, list):
                                        audio.tags[series_key] = [MP4FreeForm(str(x).encode('utf-8')) for x in formatted_value]
                                    else:
                                        audio.tags[series_key] = [MP4FreeForm(str(formatted_value).encode('utf-8'))]
                                except Exception:
                                    # Fallback to raw bytes
                                    if isinstance(formatted_value, list):
                                        audio.tags[series_key] = [str(x).encode('utf-8') for x in formatted_value]
                                    else:
                                        audio.tags[series_key] = [str(formatted_value).encode('utf-8')]
                        except Exception:
                            pass
                elif hasattr(audio, tag):
                    # Direct attribute (for some formats)
                    setattr(audio, tag, formatted_value)
            except Exception:
                # Skip tags that can't be set
                continue

    # Save the changes
    audio.save()
    # Reload the file to ensure changes are flushed to disk and visible to
    # subsequent Mutagen reads (prevents race where conversion reads stale tags).
    try:
        audio = mutagen.File(file_path)
    except Exception:
        # If reload fails, continue; the save has already been attempted
        pass
    
    # For MP3 files, restore original APIC data after saving to prevent recompression
    if is_mp3 and original_apic_data and hasattr(audio, 'tags') and audio.tags is not None:
        # Reload the file to get the current state
        audio = MP3(file_path)
        # Restore the original APIC frames
        for tag_name, apic_frame in original_apic_data.items():
            audio.tags[tag_name] = apic_frame
        # Save again with the original APIC data preserved
            # Attempt to save and provide detailed diagnostics if it fails
            try:
                audio.save()
                # After restoring original APIC frames and saving, reload the
                # file to guarantee the updated tags are visible to later reads.
                try:
                    audio = MP3(file_path)
                except Exception:
                    pass
            except Exception as save_exc:
                # Print diagnostics about tag keys and value types to help debug
                try:
                    logger.error("Error saving MP4 tags: %s", save_exc)
                    logger.debug("Diagnostics: listing audio.tags items (key -> type / sample repr)")
                    for k, v in list(audio.tags.items()):
                        try:
                            t = type(v)
                            if isinstance(v, list):
                                inner_types = [type(x) for x in v]
                                sample = v[0] if len(v) > 0 else None
                                logger.debug("  %s -> list of %s, sample type: %s, sample repr: %s", k, inner_types, type(sample), repr(sample)[:200])
                            else:
                                logger.debug("  %s -> %s repr: %s", k, t, repr(v)[:200])
                        except Exception as e_inner:
                            logger.debug("  %s -> (error inspecting value: %s)", k, e_inner)
                except Exception:
                    pass
                # Re-raise the original exception to preserve previous behavior (caught by outer code)
                raise


def mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None):
    """
    Mutate metadata for all files in a folder based on folder type.

    Args:
        metadata_dict: Dict with:
            - folder_type: "novel" or "series"
            - folder: path to source folder
            - files: dict of {file_path: metadata_dict}
        album_sort_prefix: Optional string to prefix album_sort with " : " separator
        album_suffix: Optional string to suffix album with " - " separator
        sort_by: How to sort files ('filename' or 'track')
        chapter_titles: If True, use "BookName: Chapter X" format for titles

    Returns:
        Path to the mutated temporary folder
    """
    folder_type = metadata_dict.get('folder_type')
    source_folder = metadata_dict.get('folder')
    files_dict = metadata_dict.get('files', {})

    if not source_folder or not files_dict:
        raise ValueError("Invalid metadata_dict: missing folder or files")

    # Copy folder to temp location
    temp_folder = copy_folder(source_folder)
    if not temp_folder:
        raise ValueError("Failed to copy folder: {}".format(source_folder))

    temp_path = temp_folder

    # Get folder names for processing
    source_path = source_folder
    folder_name = os.path.basename(source_path)
    cleaned_folder_name = clean_album_name(folder_name)

    # For series, get parent folder name
    parent_name = ""
    cleaned_parent_name = ""
    if folder_type == "series":
        parent_name = os.path.basename(os.path.dirname(source_path))
        cleaned_parent_name = clean_album_name(parent_name)

    # Process each file
    if sort_by == 'track':
        # Sort by track number with filename fallback
        sorted_files = sorted(files_dict.keys(), key=lambda f: track_number_sort_key(f, files_dict.get(str(f), {})))
    else:
        # Default: sort by filename naturally
        sorted_files = sorted(files_dict.keys(), key=natural_sort_key)
    
    for index, source_file_path in enumerate(sorted_files, 1):
        metadata = files_dict[source_file_path]

        # Normalize metadata values using the utility function
        normalized_metadata = parse_metadata_to_python_safe(metadata)
        
        # Extract the normalized values for processing
        processed_metadata = {}
        for desc_key, info in normalized_metadata.items():
            if isinstance(info, dict) and 'value' in info:
                processed_metadata[desc_key] = info['value']
            else:
                processed_metadata[desc_key] = info

        # Get corresponding temp file path
        source_file = source_file_path
        temp_file = os.path.join(temp_path, os.path.basename(source_file))

        if not os.path.exists(temp_file):
            continue  # Skip if temp file doesn't exist

        # Create updated metadata dict
        updated_metadata = processed_metadata.copy()

        # Clean existing text metadata values
        # Preserve artist/composer/year/grouping/series_index/genre mostly as-is (strip only)
        for key, value in updated_metadata.items():
            if not isinstance(value, str):
                continue
            if key in ['picture', 'title_sort', 'chapter_sort', 'sort_title']:
                # Don't clean these
                continue
            if key in ['composer', 'artist', 'year', 'grouping', 'series_index', 'genre', 'album_artist']:
                # Preserve original form, only trim whitespace
                updated_metadata[key] = value.strip()
            else:
                # For other text fields (titles, album) apply book_title_logic
                updated_metadata[key] = book_title_logic(value)

        # Apply folder-type specific logic
        if folder_type == "series":
            # Add cleaned folder name to album
            updated_metadata['album'] = cleaned_folder_name
            # Add cleaned parent folder name to front of album_sort
            updated_metadata['album_sort'] = "{} - {}".format(cleaned_parent_name, cleaned_folder_name)
            # For series, set grouping (series name) and attempt to set series_index if available
            # grouping will map to ©grp in MP4
            # If the caller supplied an explicit series_name, sanitize and use that for grouping;
            # otherwise fall back to the cleaned parent folder name. This ensures a
            # CLI-provided series name can override inferred values.
            cleaned_series_input = sanitize_series_name(series_name) if series_name else None
            updated_metadata['grouping'] = cleaned_series_input if cleaned_series_input else cleaned_parent_name
            # If incoming metadata included a series index, preserve it; otherwise try to parse from parent folder name
            # Prefer explicit series_index from processed metadata (normalize '1/1' -> 1)
            if processed_metadata.get('series_index'):
                try:
                    si = processed_metadata.get('series_index')
                    if isinstance(si, str) and '/' in si:
                        si = si.split('/')[0]
                    updated_metadata['series_index'] = int(si)
                except Exception:
                    updated_metadata['series_index'] = processed_metadata.get('series_index')
            else:
                # 1) Try numeric prefix on the current folder name (highest priority)
                inferred = parse_series_index_from_folder_name(folder_name)

                # 2) If no prefix on current folder, scan sibling folders for numeric
                #    prefixes and prefer using that sibling-prefix scheme if present.
                if not inferred:
                    try:
                        parent_dir = os.path.dirname(source_path)
                        siblings = [d for d in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, d))]
                        prefix_map = {}
                        for s in siblings:
                            try:
                                n = parse_series_index_from_folder_name(s)
                                if n:
                                    # Map cleaned album name (without numeric prefix) to the numeric prefix
                                    cleaned = clean_album_name(s)
                                    prefix_map[cleaned] = n
                            except Exception:
                                continue

                        # If any siblings have numeric prefixes, try to match by cleaned folder name
                        if prefix_map:
                            current_clean = clean_album_name(folder_name)
                            if current_clean in prefix_map:
                                inferred = prefix_map.get(current_clean)
                            else:
                                # Also try basename of source_path cleaned
                                basename = os.path.basename(source_path)
                                if basename in prefix_map:
                                    inferred = prefix_map.get(basename)
                                else:
                                    # fallback: try cleaned parent folder name
                                    inferred = None
                    except Exception:
                        inferred = None

                # 3) Fallback: try numeric prefix on parent (older behavior)
                if not inferred:
                    inferred = parse_series_index_from_folder_name(parent_name)

                # 4) If still not found, attempt sibling-order inference (alphabetical)
                if not inferred:
                    try:
                        parent_dir = os.path.dirname(source_path)
                        siblings = [d for d in os.listdir(parent_dir) if os.path.isdir(os.path.join(parent_dir, d))]
                        # Clean sibling names and ignore leading 'The '
                        def _clean_for_sort(n):
                            cn = clean_album_name(n)
                            # strip leading 'The ' for sorting
                            if isinstance(cn, str) and cn.lower().startswith('the '):
                                return cn[4:]
                            return cn

                        siblings_sorted = sorted(siblings, key=lambda x: natural_sort_key(_clean_for_sort(x) or x))
                        try:
                            idx = siblings_sorted.index(os.path.basename(source_path))
                            inferred = idx + 1
                        except ValueError:
                            inferred = None
                    except Exception:
                        inferred = None

                if inferred:
                    updated_metadata['series_index'] = inferred
                else:
                    updated_metadata['series_index'] = ''
        elif folder_type == "novel":
            # Add cleaned folder name to album and album_sort
            updated_metadata['album'] = cleaned_folder_name
            updated_metadata['album_sort'] = cleaned_folder_name
            # For single novels, grouping can still be the album/book title
            updated_metadata['grouping'] = cleaned_folder_name

        # Apply album_sort prefix if provided
        if album_sort_prefix:
            current_album_sort = updated_metadata.get('album_sort', '')
            updated_metadata['album_sort'] = "{} : {}".format(album_sort_prefix, current_album_sort)

        # If an explicit series_name was provided, sanitize it and prepend to album_sort
        cleaned_series_input = sanitize_series_name(series_name) if series_name else None
        if cleaned_series_input:
            try:
                current_album_sort = updated_metadata.get('album_sort', '')
                if current_album_sort:
                    updated_metadata['album_sort'] = "{} : {}".format(cleaned_series_input, current_album_sort)
                else:
                    updated_metadata['album_sort'] = cleaned_series_input
            except Exception:
                pass

        # Apply album suffix if provided
        if album_suffix:
            current_album = updated_metadata.get('album', '')
            updated_metadata['album'] = "{} - {}".format(current_album, album_suffix)

        # Set title: use existing title metadata if available, otherwise use filename as written
        file_stem = os.path.splitext(os.path.basename(source_file))[0]
        if chapter_titles:
            # Primary prefix: use the parent folder name of the file being processed
            # (i.e., the folder that contains the file). This allows titles like
            # "Inkheart: Chapter 1" even when the overall source folder name is
            # different. Fall back to album/grouping, cleaned source folder name,
            # filename, or finally just "Chapter N".
            try:
                parent_folder = os.path.basename(os.path.dirname(source_file))
            except Exception:
                parent_folder = ''

            cleaned_parent = clean_album_name(parent_folder) if parent_folder else ''

            book_name_for_title = (cleaned_parent or
                                   updated_metadata.get('album') or
                                   updated_metadata.get('grouping') or
                                   cleaned_folder_name or
                                   book_title_logic(os.path.basename(source_path)) or
                                   file_stem)

            # Ensure it's a trimmed string
            try:
                book_name_for_title = book_name_for_title.strip()
            except Exception:
                book_name_for_title = str(book_name_for_title).strip()

            if book_name_for_title:
                cleaned_title = "{}: Chapter {}".format(book_name_for_title, index)
            else:
                cleaned_title = "Chapter {}".format(index)
        elif processed_metadata.get('title') and processed_metadata['title'].strip():
            # Use existing title metadata and apply book_title_logic
            cleaned_title = book_title_logic(processed_metadata['title'])
        else:
            # Use filename as written (without book_title_logic)
            cleaned_title = file_stem
        updated_metadata['title'] = cleaned_title

    # Set title_sort to uncleaned filename stem (mapping expects 'title_sort')
    updated_metadata['title_sort'] = file_stem

    # Set track number
    updated_metadata['track'] = str(index)

    # Ensure media_kind is set to Audiobook (stik=2)
    updated_metadata['media_kind'] = 2
    # Preserve genre if present from source files; otherwise set to "Audiobook"
    # Only default to 'Audiobook' for MP4/M4A/M4B outputs; don't set for MP3
    _, ext = os.path.splitext(temp_file)
    ext = ext.lower()
    if not updated_metadata.get('genre'):
        if ext in ['.m4a', '.m4b', '.mp4', '.mp3']:
            updated_metadata['genre'] = "Audiobook"
        else:
            # Leave genre unset for other formats (e.g., mp3)
            updated_metadata['genre'] = updated_metadata.get('genre', '')

    # Apply changes to the temp file
    try:
        apply_metadata_to_file(str(temp_file), updated_metadata)
    except Exception as e:
        print("Warning: Failed to update metadata for {}: {}".format(temp_file, e))

    # Clean up the folder name in temp directory
    cleaned_temp_folder_name = book_title_logic(os.path.basename(temp_path))
    # Additional sanitization to avoid leading punctuation / numeric prefixes
    import re
    if cleaned_temp_folder_name:
        cleaned_temp_folder_name = re.sub(r'^[\-\._\s]+', '', cleaned_temp_folder_name)
        cleaned_temp_folder_name = re.sub(r'^\d{1,3}[\s\-:\._]+', '', cleaned_temp_folder_name)
        cleaned_temp_folder_name = re.sub(r'\s{2,}', ' ', cleaned_temp_folder_name).strip()
    new_temp_path = os.path.join(os.path.dirname(temp_path), cleaned_temp_folder_name)

    # Rename the folder if name changed
    if cleaned_temp_folder_name != os.path.basename(temp_path):
        os.rename(temp_path, new_temp_path)
        temp_folder = str(new_temp_path)

    return temp_folder


def get_sleep_prevention_command():
    """
    Get the appropriate command to prevent system sleep during long operations.
    Returns a list of command arguments to prepend to the main command.
    
    Returns:
        List of command arguments, or empty list if not supported
    """
    import platform
    
    system = platform.system().lower()
    
    if system == 'darwin':  # macOS
        # Check if caffeinate is available
        try:
            import subprocess
            result = subprocess.run(['which', 'caffeinate'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return ['caffeinate', '-i']
        except Exception as e:
            logger.debug("caffeinate check failed: %s", e)
    elif system == 'linux':
        # Try systemd-inhibit first (most reliable on modern Linux)
        try:
            import subprocess
            result = subprocess.run(['which', 'systemd-inhibit'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return ['systemd-inhibit', '--what=idle:sleep', '--who=audiobook-p', '--why=Long running audio conversion']
        except Exception as e:
            logger.debug("systemd-inhibit check failed: %s", e)
        
        # Fallback to caffeine if available
        try:
            import subprocess
            result = subprocess.run(['which', 'caffeine'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return ['caffeine']
        except Exception as e:
            logger.debug("caffeine check failed: %s", e)
    elif system == 'windows':
        # Windows sleep prevention is more complex and requires PowerShell
        # For now, we'll skip it to avoid changing system settings
        # Users can manually disable sleep or use third-party tools
        pass
    
    # Return empty list if no sleep prevention available
    return []


def convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename', original_source_path=None, chapter_titles=False, series_name=None):
    """
    Convert a folder of audio files (os.path.join(MP3, M4A)) to a single M4B file with chapters.

    Args:
        folder_path: Path to folder containing audio files
        output_path: Path for the output M4B file
        config: Optional configuration object for settings
        sort_by: 'filename' or 'track' - how to sort files
        original_source_path: Path to original source files for cover art
        chapter_titles: If True, use file titles directly for chapter titles (already formatted)

    Returns:
        Path to the created M4B file
    """
    folder_path = folder_path
    output_path = output_path

    # Local sanitize helper for folder basenames to avoid leading punctuation/numeric
    def _local_sanitize_folder_name(name):
        import re
        if not name:
            return name
        s = name.strip()
        s = re.sub(r'^[\-\._\s]+', '', s)
        s = re.sub(r'^\d{1,3}[\s\-:\._]+', '', s)
        s = re.sub(r'\s{2,}', ' ', s)
        return s.strip()

    # Use a sanitized folder basename for internal filenames/chapters
    folder_basename = _local_sanitize_folder_name(os.path.basename(folder_path))

    if not os.path.isdir(folder_path):
        raise ValueError("Path is not a directory: {}".format(folder_path))

    # Find all audio files in the folder
    audio_extensions = ['*.m4a', '*.mp3']
    audio_files = []
    for ext in audio_extensions:
        audio_files.extend(list(glob.glob(os.path.join(folder_path, ext))))

    if not audio_files:
        raise ValueError("No audio files found in: {}".format(folder_path))

    # Sort files based on sort_by parameter
    if sort_by == 'track':
        # Extract metadata first to get track numbers
        file_metadata = {}
        for audio_file in audio_files:
            try:
                metadata = extract_metadata_from_file(str(audio_file))
                file_metadata[str(audio_file)] = metadata
            except Exception as e:
                file_metadata[str(audio_file)] = {"error": str(e)}
        
        # Sort by track number with filename fallback
        audio_files.sort(key=lambda f: track_number_sort_key(f, file_metadata.get(str(f), {})))
    else:
        # Default: sort by filename naturally
        audio_files.sort(key=natural_sort_key)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Create chapter metadata file for ffmpeg
    import tempfile
    
    # Create a temporary file list for ffmpeg concatenation
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=os.getcwd()) as f:
        file_list_path = f.name
        for audio_file in audio_files:
            # Use relative path from current working directory
            try:
                rel_path = os.path.relpath(audio_file, os.getcwd())
            except ValueError:
                # If relpath fails, use absolute path
                rel_path = str(audio_file)
            # Escape single quotes properly for ffmpeg concat
            escaped_path = rel_path.replace("'", "'\\''")
            f.write("file '{}'\n".format(escaped_path))

    # Create chapter metadata file and collect chapter info for post-processing
    chapters_info = []
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, dir=os.getcwd()) as f:
        metadata_path = f.name
        f.write(";FFMETADATA1\n")
        
        # Calculate chapter timestamps and write metadata
        current_time = 0
        for i, audio_file in enumerate(audio_files):
            # Get duration from source file
            source_audio = mutagen.File(audio_file)
            if source_audio and hasattr(source_audio, 'info') and hasattr(source_audio.info, 'length'):
                duration_ms = int(source_audio.info.length * 1000)  # Convert to milliseconds
            else:
                # Fallback: estimate 10 minutes per chapter if duration can't be read
                duration_ms = 600000  # 10 minutes in milliseconds

            # Get chapter title from source file metadata or use filename
            chapter_title = "Chapter {}".format(i+1)
            try:
                source_metadata = extract_metadata_from_file(audio_file)
                if source_metadata.get('title'):
                    if chapter_titles:
                        # Use title directly (already formatted by mutate_metadata)
                        chapter_title = source_metadata['title']
                    else:
                        # Apply book title logic to clean up chapter titles
                        chapter_title = book_title_logic(source_metadata['title'])
                else:
                    # Use filename without extension as fallback
                    file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                    if chapter_titles:
                        # For chapter_titles mode, still use filename as-is
                        chapter_title = file_stem
                    else:
                        # Apply book title logic to clean up filename-based titles too
                        chapter_title = book_title_logic(file_stem)
            except Exception as e:
                # Use filename without extension as final fallback
                logger.debug("Error extracting title metadata for %s: %s", audio_file, e)
                file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                if chapter_titles:
                    chapter_title = file_stem
                else:
                    # Apply book title logic to clean up filename-based titles
                    chapter_title = book_title_logic(file_stem)

            # Write chapter info to metadata file
            f.write("\n[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write("START={}\n".format(current_time))
            f.write("END={}\n".format(current_time + duration_ms))
            f.write("title={}\n".format(chapter_title))
            
            # Collect chapter info for post-processing (convert to seconds)
            chapters_info.append({
                'start': current_time / 1000.0,  # Convert milliseconds to seconds
                'title': chapter_title
            })
            
            current_time += duration_ms

    try:
        # Use ffmpeg with concat input and chapter metadata
        import subprocess

        # Get audio quality from config if available
        audio_quality = '128k'  # Default
        try:
            if config:
                audio_quality = config.get('processing.ffmpeg_quality', '128k')
        except Exception as e:
            logger.debug("Error reading config audio quality: %s", e)

        # Build the ffmpeg command with chapter metadata
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', file_list_path,
            '-i', metadata_path,
            '-map', '0:a',  # Map only audio streams from first input
            '-map_metadata', '1',  # Use metadata from second input (metadata file)
            '-c:a', 'aac',
            '-b:a', audio_quality,
            '-f', 'mp4',
            '-movflags', '+faststart',
            '-y',  # Overwrite output
            str(output_path)
        ]

        # Handle sleep prevention
        import platform
        system = platform.system().lower()
        if system == 'windows':
            # For Windows, wrap the entire ffmpeg command in PowerShell with sleep prevention
            try:
                import subprocess
                result = subprocess.run(['where', 'powershell'], capture_output=True, text=True)
                if result.returncode == 0:
                    # Create PowerShell script that prevents sleep during ffmpeg execution
                    ffmpeg_args = ' '.join([f'"{arg}"' if ' ' in arg or '"' in arg else arg for arg in cmd])
                    powershell_script = f'''
$code = @"
using System;
using System.Runtime.InteropServices;
public class Power {{
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
}}
"@;
Add-Type -TypeDefinition $code;
[Power]::SetThreadExecutionState([Power]::ES_CONTINUOUS -bor [Power]::ES_SYSTEM_REQUIRED -bor [Power]::ES_DISPLAY_REQUIRED);
try {{
    & ffmpeg.exe {ffmpeg_args}
}} finally {{
    [Power]::SetThreadExecutionState([Power]::ES_CONTINUOUS);
}}
'''
                    cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', powershell_script]
                else:
                    # PowerShell not available, continue without sleep prevention
                    pass
            except Exception as e:
                # Error checking PowerShell, continue without sleep prevention
                logger.debug("Error checking for PowerShell: %s", e)
        else:
            # For macOS/Linux, use the standard prefix approach
            sleep_prevention_cmd = get_sleep_prevention_command()
            if sleep_prevention_cmd:
                cmd = sleep_prevention_cmd + cmd

        # Initialize progress tracker for M4B conversion
        try:
            from audiobook_p.progress import ProgressTracker
            # Use total seconds (rounded) for progress tracking when available
            try:
                total_duration = int(max(1, current_time / 1000.0))
            except Exception:
                total_duration = 1
            progress = ProgressTracker(total_duration, "Converting to M4B")
            progress.update(0, "Starting conversion...")
        except ImportError:
            # Fallback if progress module not available
            progress = None
            logger.info("Converting to M4B...")

        # Run the command and stream stderr to update progress in real time
        try:
            # Start ffmpeg process
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)

            # Parse ffmpeg stderr lines for time=HH:MM:SS.micro to estimate progress
            import re
            time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")

            # If we don't have a sensible total_duration fallback to 1 to avoid divide-by-zero
            try:
                total_secs = float(max(1.0, current_time / 1000.0))
            except Exception:
                total_secs = 1.0

            # Read stderr line-by-line
            if proc.stderr is not None:
                for raw_line in proc.stderr:
                    line = raw_line.strip()
                    # Try to find a time= value
                    m = time_re.search(line)
                    if m:
                        hh = int(m.group(1))
                        mm = int(m.group(2))
                        ss = float(m.group(3))
                        elapsed = hh * 3600 + mm * 60 + ss
                        # Update progress based on elapsed / total_secs
                        if progress:
                            # Cap elapsed at total_secs
                            cur = int(min(elapsed, total_secs))
                            progress.set_progress(cur, "Converting: {}s/{:.0f}s".format(int(elapsed), total_secs))
                    # Optionally, print ffmpeg line in verbose mode or debug
                    # print(line)

            # Wait for process to finish
            retcode = proc.wait()
            if retcode != 0:
                # Capture output for error reporting (don't keep unused variables)
                try:
                    proc.communicate(timeout=2)
                except Exception as e:
                    logger.debug("Error communicating with ffmpeg process: %s", e)
                raise Exception("ffmpeg failed with exit code {}".format(retcode))

            # Update progress to complete
            if progress:
                progress.finish("M4B conversion complete")
            else:
                logger.info("M4B conversion complete")

        except Exception:
            # If something goes wrong, try a non-streaming call to capture the error
            try:
                error_output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
                raise Exception("ffmpeg failed: {}".format(error_output))
            except subprocess.CalledProcessError as e2:
                raise Exception("ffmpeg failed with exit code {}: {}".format(e2.returncode, e2.output))
            except Exception:
                # Re-raise original
                raise

        # Verify the output file was created and has content
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Output file was not created or is empty")

        # Add chapters to the M4B file using mutagen
        if chapters_info:
            try:
                from mutagen.mp4 import MP4, MP4Chapters, Chapter
                audio = MP4(str(output_path))
                
                # Create chapter objects from our collected info
                chapter_objects = []
                for chapter in chapters_info:
                    chapter_obj = Chapter(start=chapter['start'], title=chapter['title'])
                    chapter_objects.append(chapter_obj)
                
                # Create MP4Chapters and set its internal chapters
                mp4_chapters = MP4Chapters()
                mp4_chapters._chapters = chapter_objects
                
                # Set the chapters on the MP4 file
                audio.chapters = mp4_chapters
                audio.save()
                logger.info("Chapters added to M4B file")
            except Exception as e:
                logger.warning("Failed to add chapters to M4B: %s", e)

        # Add additional metadata to the M4B file (audiobook-specific tags)
        # Try to find original source files for better cover art quality
        original_audio_files = None
        try:
            # If we have an explicit original source path, use it
            if original_source_path and os.path.exists(original_source_path):
                # Find audio files in the original source path
                original_files = []
                for ext in ['*.m4a', '*.mp3']:
                    original_files.extend(glob.glob(os.path.join(original_source_path, ext)))
                if original_files:
                    # Sort to match the order of temp files
                    original_files.sort(key=natural_sort_key)
                    original_audio_files = original_files
                    logger.info("Found %d original source files from explicit path", len(original_files))
            # Fallback: If the folder_path looks like a temp directory (contains "audiobook_copy_"), 
            # try to find the original files by looking at the source folder structure
            elif "audiobook_copy_" in folder_path:
                # This is likely a mutated temp folder, try to find original files
                # Look for files with similar names in the current directory or parent
                folder_dir = os.path.dirname(folder_path)
                folder_name = os.path.basename(folder_path)
                
                # Try to find a folder with similar audio files in the same directory
                for item in os.listdir(folder_dir):
                    item_path = os.path.join(folder_dir, item)
                    if os.path.isdir(item_path) and item != folder_name:
                        # Check if this folder has similar audio files
                        test_files = []
                        for ext in ['*.m4a', '*.mp3']:
                            test_files.extend(glob.glob(os.path.join(item_path, ext)))
                        if test_files:
                            # Check if filenames are similar (same stem)
                            original_files = []
                            for temp_file in audio_files:
                                temp_stem = os.path.splitext(os.path.basename(temp_file))[0]
                                for test_file in test_files:
                                    test_stem = os.path.splitext(os.path.basename(test_file))[0]
                                    if temp_stem == test_stem:
                                        original_files.append(test_file)
                                        break
                            if len(original_files) > 0:
                                original_audio_files = original_files
                                logger.info("Found %d original source files for cover art", len(original_files))
                                break
        except Exception as e:
            logger.warning("Failed to find original source files: %s", e)
            pass  # If we can't find originals, use the provided files

        # Add audiobook metadata to the output file (copy tags, cover art, series)
        add_audiobook_metadata(str(output_path), audio_files, original_audio_files, series_name=series_name)

        return str(output_path)

    finally:
        # Clean up temporary files
        try:
            os.remove(file_list_path)
        except Exception as e:
            logger.debug("Failed to remove file_list_path %s: %s", file_list_path, e)
        try:
            os.remove(metadata_path)
        except Exception as e:
            logger.debug("Failed to remove metadata_path %s: %s", metadata_path, e)


def add_chapters_to_m4b(m4b_path, chapters_info):
    """
    Add chapters to an existing M4B file.
    
    Args:
        m4b_path: Path to the M4B file
        chapters_info: List of dicts with 'start' and 'title' keys
    """
    try:
        from mutagen.mp4 import MP4, MP4Chapters, Chapter
        audio = MP4(str(m4b_path))

        # Create chapter objects from our collected info
        chapter_objects = []
        for chapter in chapters_info:
            chapter_obj = Chapter(start=chapter['start'], title=chapter['title'])
            chapter_objects.append(chapter_obj)

        # Create MP4Chapters and set its internal chapters
        mp4_chapters = MP4Chapters()
        mp4_chapters._chapters = chapter_objects

        # Set the chapters on the MP4 file
        audio.chapters = mp4_chapters
        audio.save()
        logger.info("Chapters added to M4B file")
        return True
    except Exception as e:
        logger.warning("Failed to add chapters to M4B: %s", e)
        return False


def add_audiobook_metadata(m4b_path, source_files, original_source_files=None, series_name=None, mp4_class=None, mutagen_file_func=None):
    """
    Add audiobook metadata to an existing M4B file.

    Optional parameters:
      - mp4_class: a replacement class for mutagen.mp4.MP4 (for testing)
      - mutagen_file_func: a replacement for mutagen.File (for testing)
    """
    # Resolve MP4 and MP4Tags, allowing injection for tests
    try:
        if mp4_class is not None:
            MP4 = mp4_class
            MP4Tags = dict
        else:
            from mutagen.mp4 import MP4, MP4Tags

        if mutagen_file_func is not None:
            MutagenFile = mutagen_file_func
        else:
            from mutagen import File as MutagenFile
    except ImportError:
        logger.warning("mutagen MP4 support not available, skipping metadata addition")
        return

    # Load the M4B file
    audio = MP4(m4b_path)
    if audio.tags is None:
        audio.tags = MP4Tags()
    # Track whether we've explicitly written a trkn value during this run
    track_written = False

    # Load the mapping to determine which tags to copy
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)

    # Combine all metadata sections
    all_fields = {}
    for section in ['core_metadata', 'audiobook_specific', 'sort_fields', 'extended_metadata']:
        if section in mapping:
            all_fields.update(mapping[section])

    # Copy metadata and images from the first file that has them
    if source_files:
        try:
            # Try to find a source file with picture data
            # Prioritize original source files for cover art to avoid compression
            picture_sources = []
            if original_source_files:
                picture_sources.extend(original_source_files)
            picture_sources.extend(source_files)
            
            source_with_picture = None
            for source_file in picture_sources:
                try:
                    # Check for picture data directly
                    test_audio = MutagenFile(source_file)
                    if test_audio and hasattr(test_audio, 'tags') and test_audio.tags:
                        # Check for any tag containing 'APIC' or 'PIC' (MP3) or 'covr' (M4A)
                        has_picture = False
                        for tag_name in test_audio.tags:
                            if 'APIC' in tag_name or 'PIC' in tag_name or tag_name == 'covr':
                                has_picture = True
                                break
                        if has_picture:
                            source_with_picture = source_file
                            break
                except Exception as e:
                    logger.debug("Error checking %s: %s", source_file, e)
                    continue

            # Helper: sanitize incoming values that may be malformed
            def sanitize_metadata_value(val):
                """
                Normalize metadata values into reasonable Python types:
                - Unwrap stringified lists like "['1/1']" -> ['1/1'] -> '1/1'
                - Decode bytes to utf-8 where appropriate
                - Leave bytes (image data) alone
                - For lists of one element, return the element (caller will wrap as needed)
                """
                import re
                # If it's already bytes or tuple or list, return as-is (but decode inner bytes)
                if isinstance(val, bytes):
                    return val
                if isinstance(val, tuple):
                    return val
                if isinstance(val, list):
                    # simplify single-element lists
                    if len(val) == 0:
                        return val
                    if len(val) == 1:
                        return sanitize_metadata_value(val[0])
                    # sanitize each element
                    return [sanitize_metadata_value(x) for x in val]

                # If it's a mutagen object with .data, prefer that raw data
                try:
                    if hasattr(val, 'data'):
                        return val.data
                except Exception:
                    pass

                # If it's a string that looks like a python list literal, try to eval safely
                if isinstance(val, str):
                    stripped = val.strip()
                    # common pattern: "['1/1']" or '["1/1"]'
                    if stripped.startswith('[') and stripped.endswith(']'):
                        # attempt to extract inner quoted value(s)
                        items = re.findall(r"'([^']*)'|\"([^\"]*)\"", stripped)
                        # items is list of tuples from alternation; flatten
                        flat = [a if a else b for a, b in items if a or b]
                        if len(flat) == 1:
                            return sanitize_metadata_value(flat[0])
                        if len(flat) > 1:
                            return [sanitize_metadata_value(x) for x in flat]

                    # If it's bytes-as-string (b'...'), try to decode
                    if stripped.startswith("b'") or stripped.startswith('b"'):
                        try:
                            # remove leading b' and trailing '
                            inner = stripped[2:]
                            if inner.startswith("'") or inner.startswith('"'):
                                inner = inner[1:-1]
                            return inner
                        except Exception:
                            pass

                    # Otherwise return the string as-is
                    return val

                # Last resort: convert to str
                try:
                    return str(val)
                except Exception:
                    return val

            # Use the mutated source files for basic text metadata so we pick up
            # any changes applied during the mutate step. Keep original_source_files
            # available and prioritized earlier when selecting cover art only.
            # Prefer source_files[0] for text metadata (these are the post-mutate files)
            first_file = source_files[0]
            first_audio = MutagenFile(first_file)
            try:
                # Debug: log tag keys at debug level to reduce test noise
                logger.debug("DBG: first_audio tags keys: %s", list(first_audio.tags.keys()) if first_audio and hasattr(first_audio, 'tags') and first_audio.tags else [])
            except Exception:
                pass

            # Determine track value up-front and mark whether it originated from
            # explicit source metadata so later copy/default logic does not
            # accidentally overwrite it. Doing this before the general metadata
            # copy ensures trkn is authoritative and preserved.
            try:
                try:
                    pre_track_val, pre_track_from_source = _determine_track_value_for_sources(source_files, MutagenFile)
                except Exception:
                    pre_track_val, pre_track_from_source = (None, False)

                if pre_track_val is not None:
                    try:
                        audio.tags['trkn'] = pre_track_val
                        track_written = bool(pre_track_from_source)
                        logger.debug("Pre-seeded trkn from helper: %r (source-derived=%r)", pre_track_val, pre_track_from_source)
                    except Exception:
                        pass
            except Exception:
                pass

            # PRIORITY: Copy picture data early so cover art is preserved even if
            # other metadata assignments later fail. Prefer original source files
            # for best quality (original_source_files already included in picture_sources).
            picture_copied = False
            if source_with_picture:
                try:
                    source_audio = MutagenFile(source_with_picture)
                    if source_audio and hasattr(source_audio, 'tags') and source_audio.tags:
                        # First check for M4A cover art (covr tag)
                        if 'covr' in source_audio.tags:
                            covr_data = source_audio.tags['covr']
                            if isinstance(covr_data, list) and len(covr_data) > 0:
                                try:
                                    logger.debug("Copying covr from source (early copy): type=%s, sample type=%s", type(covr_data), type(covr_data[0]))
                                except Exception:
                                    pass
                                audio.tags['covr'] = covr_data
                                picture_copied = True
                                logger.info("Cover art copied from M4A source (early)")

                        # If no M4A cover found, check for MP3-style APIC tags
                        if not picture_copied:
                            for tag_name in source_audio.tags:
                                if 'APIC' in tag_name or 'PIC' in tag_name:
                                    picture_data = source_audio.tags[tag_name]
                                    if isinstance(picture_data, list) and len(picture_data) > 0:
                                        pic = picture_data[0]
                                    else:
                                        pic = picture_data

                                    if hasattr(pic, 'data'):
                                        try:
                                            audio.tags['covr'] = [pic.data]
                                            picture_copied = True
                                            logger.info("Cover art copied from MP3 source (early, raw APIC data, %d bytes)", len(pic.data))
                                            break
                                        except Exception:
                                            try:
                                                from mutagen.mp4 import MP4Cover
                                                audio.tags['covr'] = [MP4Cover(pic.data)]
                                                picture_copied = True
                                                logger.info("Cover art copied from MP3 source (early, via MP4Cover)")
                                                break
                                            except Exception:
                                                pass

                                    # TRACE: show what we found after attempting ID3 parse paths
                                    # Debug trace removed: no-op
                except Exception:
                    pass

                # Helper to decode mapping keys like "\\xa9ART" into real unicode atoms
                def _decode_mp4_key(k):
                    try:
                        if isinstance(k, str) and '\\x' in k:
                            return k.encode('ascii').decode('unicode_escape')
                    except Exception:
                        pass
                    return k

                # Proceed to copy text-based metadata that has MP4 equivalents
                if first_audio and hasattr(first_audio, 'tags') and first_audio.tags:
                    # Copy all text-based metadata that has MP4 equivalents
                    for desc_key, field_info in all_fields.items():
                        mutagen_keys = field_info.get('mutagen_keys', {})
                        mp3_key = mutagen_keys.get('id3', '')
                        mp4_key = mutagen_keys.get('mp4', '')
                        decoded_mp4_key = _decode_mp4_key(mp4_key) if mp4_key else mp4_key

                        # Skip if no MP4 equivalent or if it's picture (handled separately)
                        if not mp4_key or desc_key == 'cover_art':
                            continue

                        # Try to find the value in the source file (support MP3 ID3 and MP4 atoms)
                        source_value = None
                        # Prefer MP4 atom if available (covers .m4a/.m4b sources)
                        # Decode the mapping key (e.g. "\\xa9ART") to the real unicode atom (e.g. "©ART")
                        if mp4_key:
                            decoded_mp4_key = _decode_mp4_key(mp4_key)
                        else:
                            decoded_mp4_key = mp4_key

                        if decoded_mp4_key and decoded_mp4_key in first_audio.tags:
                            raw_value = first_audio.tags[decoded_mp4_key]
                            # MP4 values are frequently lists
                            if isinstance(raw_value, list) and len(raw_value) > 0:
                                item = raw_value[0]
                                # MP4 text atoms are plain strings
                                try:
                                    source_value = str(item)
                                except Exception:
                                    try:
                                        source_value = repr(item)
                                    except Exception:
                                        source_value = None
                            else:
                                try:
                                    source_value = str(raw_value)
                                except Exception:
                                    source_value = None
                        # Fall back to ID3/MP3 tags if MP4 atom not present
                        elif mp3_key and mp3_key in first_audio.tags:
                            raw_value = first_audio.tags[mp3_key]
                            # Extract text value
                            if isinstance(raw_value, list) and len(raw_value) > 0:
                                item = raw_value[0]
                                if hasattr(item, 'text'):
                                    # ID3 text-like frames expose .text as list
                                    if isinstance(item.text, list) and len(item.text) > 0:
                                        source_value = str(item.text[0])
                                    else:
                                        source_value = str(item.text)
                                else:
                                    source_value = str(item)
                            elif hasattr(raw_value, 'text'):
                                # Some frames may expose .text directly
                                if isinstance(raw_value.text, list) and len(raw_value.text) > 0:
                                    source_value = str(raw_value.text[0])
                                else:
                                    source_value = str(raw_value.text)
                            else:
                                source_value = str(raw_value)

                        # Special handling for COMM frames
                        if desc_key == 'comment' and not source_value:
                            # Try to find COMM frames manually and choose the best one
                            comm_frames = []
                            for tag_name in first_audio.tags:
                                if tag_name.startswith("COMM:"):
                                    raw_value = first_audio.tags[tag_name]
                                    text_value = ""
                                    if isinstance(raw_value, list) and len(raw_value) > 0:
                                        item = raw_value[0]
                                        if hasattr(item, 'text'):
                                            # item.text is a list of strings for COMM frames
                                            if isinstance(item.text, list) and len(item.text) > 0:
                                                text_value = item.text[0]
                                            else:
                                                text_value = str(item.text)
                                        else:
                                            text_value = str(item)
                                    elif hasattr(raw_value, 'text'):
                                        if isinstance(raw_value.text, list) and len(raw_value.text) > 0:
                                            text_value = raw_value.text[0]
                                        else:
                                            text_value = str(raw_value.text)
                                    else:
                                        text_value = str(raw_value)
                                    comm_frames.append((tag_name, text_value))
                            
                            # Choose the best COMM frame: prefer ones without description, or with longest text
                            if comm_frames:
                                best_frame = None
                                best_text = ""
                                for tag_name, text_value in comm_frames:
                                    # Prefer frames without description (just "COMM::eng") or with longer text
                                    if "::" in tag_name and len(text_value) > len(best_text):
                                        best_frame = tag_name
                                        best_text = text_value
                                    elif not best_frame and len(text_value) > len(best_text):
                                        best_frame = tag_name
                                        best_text = text_value
                                
                                if best_frame:
                                    source_value = best_text

                        # If we found a value, set it in the M4B file
                        if source_value is not None and source_value != '':
                            # Sanitize the source_value
                            try:
                                source_value = sanitize_metadata_value(source_value)
                            except Exception:
                                pass

                            # Use the utility function to format the value for MP4
                            formatted_value = reformat_tag_for_file_type(desc_key, source_value, 'mp4')
                            # track_number handling logged via tests; avoid noisy prints here
                            # Diagnostic: print types and repr before assignment to catch mixups
                            try:
                                existing = audio.tags.get(mp4_key)
                                logger.debug("Setting MP4 tag '%s': formatted_value type=%s, repr=%s, existing type=%s", mp4_key, type(formatted_value), repr(formatted_value)[:200], type(existing))
                            except Exception:
                                pass

                            # If this is a freeform '----:' atom, mutagen expects bytes for the data payload.
                            # Convert any string elements to UTF-8 bytes to avoid "can't concat str to bytes" errors.
                            try:
                                if isinstance(mp4_key, str) and mp4_key.startswith('----:'):
                                    def ensure_bytes(x):
                                        if isinstance(x, bytes):
                                            return x
                                        if isinstance(x, str):
                                            return x.encode('utf-8')
                                        try:
                                            return str(x).encode('utf-8')
                                        except Exception:
                                            return bytes()

                                    if isinstance(formatted_value, list):
                                        formatted_value = [ensure_bytes(x) for x in formatted_value]
                                    else:
                                        formatted_value = [ensure_bytes(formatted_value)]
                            except Exception:
                                pass

                            # Special-case normalization for track/disc tuples (trkn/disk)
                            try:
                                if mp4_key in ('trkn', 'disk'):
                                    import re as _re
                                    def normalize_tuple_val(val):
                                        # Unwrap lists
                                        if isinstance(val, list) and len(val) > 0:
                                            val = val[0]
                                        # If it's already a tuple, keep it
                                        if isinstance(val, tuple):
                                            return [val]
                                        # If it's bytes, decode
                                        if isinstance(val, bytes):
                                            try:
                                                val = val.decode('utf-8')
                                            except Exception:
                                                val = str(val)
                                        # If it's a string, try to extract integers
                                        if isinstance(val, str):
                                            nums = _re.findall(r"(\d+)", val)
                                            if len(nums) >= 2:
                                                return [(int(nums[0]), int(nums[1]))]
                                            elif len(nums) == 1:
                                                return [(int(nums[0]), 0)]
                                            else:
                                                return [(0, 0)]
                                        # If it's numeric
                                        try:
                                            iv = int(val)
                                            return [(iv, 0)]
                                        except Exception:
                                            return [(0, 0)]

                                    formatted_value = normalize_tuple_val(formatted_value)
                            except Exception:
                                pass

                            # Write using the decoded MP4 key (e.g., '©alb') when possible
                            try:
                                write_key = decoded_mp4_key if decoded_mp4_key else mp4_key
                            except Exception:
                                write_key = mp4_key
                            # If this is a track/disc write and we already have an
                            # explicit track value sourced above, skip to avoid
                            # overwriting the authoritative value.
                            if write_key in ('trkn', 'disk') or (isinstance(decoded_mp4_key, str) and decoded_mp4_key in ('trkn', 'disk')):
                                if track_written:
                                    logger.debug("Skipping write of %s because track_written is True", write_key)
                                else:
                                    audio.tags[write_key] = formatted_value
                            else:
                                audio.tags[write_key] = formatted_value
                            # Debug trace: log when we set trkn/disk during copy
                            try:
                                if write_key in ('trkn', 'disk') or (isinstance(decoded_mp4_key, str) and decoded_mp4_key in ('trkn', 'disk')):
                                    logger.debug("DBG: set %s = %r (from source %s)", write_key, formatted_value, first_file)
                            except Exception:
                                pass
                            # If we just wrote a track/disc tuple, mark it so later
                            # default logic doesn't overwrite the explicitly set value.
                            try:
                                if write_key in ('trkn', 'disk') or (isinstance(decoded_mp4_key, str) and decoded_mp4_key in ('trkn', 'disk')):
                                    track_written = True
                                    try:
                                        logger.debug("DBG: track_written set True after writing %s", write_key)
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # If this field is grouping, also set the freeform iTunes SERIES key
                            try:
                                if desc_key == 'grouping' and formatted_value:
                                    try:
                                        from mutagen.mp4 import MP4FreeForm
                                        if isinstance(formatted_value, list):
                                            audio.tags['----:com.apple.iTunes:SERIES'] = [MP4FreeForm(str(x).encode('utf-8')) for x in formatted_value]
                                        else:
                                            audio.tags['----:com.apple.iTunes:SERIES'] = [MP4FreeForm(str(formatted_value).encode('utf-8'))]
                                    except Exception:
                                        if isinstance(formatted_value, list):
                                            audio.tags['----:com.apple.iTunes:SERIES'] = [str(x).encode('utf-8') for x in formatted_value]
                                        else:
                                            audio.tags['----:com.apple.iTunes:SERIES'] = [str(formatted_value).encode('utf-8')]
                            except Exception:
                                pass

                    # If grouping wasn't found via MP4 atom or ID3 fallbacks above and
                    # the source file is an MP3, check for TIT1 frames (ID3 grouping)
                    if 'grouping' in all_fields and (not audio.tags.get('\u00A9grp')):
                        try:
                            # TIT1 is the ID3 frame for grouping (category)
                            # Try to read TIT1 from the source file (MP3)
                            from mutagen.mp3 import MP3 as MutagenMP3
                            sa = MutagenFile(first_file)
                            if isinstance(sa, MutagenMP3) and hasattr(sa, 'tags') and sa.tags:
                                for ak in sa.tags.keys():
                                    if ak == 'TIT1' or ak.startswith('TIT1'):
                                        try:
                                            tit1 = sa.tags[ak]
                                            # tit1 may expose .text
                                            val = None
                                            if isinstance(tit1, list) and len(tit1) > 0:
                                                item = tit1[0]
                                                if hasattr(item, 'text'):
                                                    val = item.text[0] if isinstance(item.text, list) else item.text
                                                else:
                                                    val = str(item)
                                            elif hasattr(tit1, 'text'):
                                                val = tit1.text[0] if isinstance(tit1.text, list) else tit1.text
                                            else:
                                                val = str(tit1)

                                            if val:
                                                # Sanitize and write to MP4 grouping and freeform SERIES
                                                try:
                                                    audio.tags['\u00A9grp'] = [val]
                                                    audio.tags['----:com.apple.iTunes:SERIES'] = [str(val).encode('utf-8')]
                                                except Exception:
                                                    pass
                                                break
                                        except Exception:
                                            continue
                        except Exception:
                            pass
                
                # Set critical audiobook-specific metadata (override any copied values)
                audio.tags['stik'] = [2]  # Media Kind: 2 = Audiobook (critical for iTunes recognition)
                audio.tags['pgap'] = [1]  # Gapless playback for seamless listening
                audio.tags['\xa9too'] = ['audiobook-p']  # Encoding tool identification
                
                # Optional: Set content rating to clean by default (only if not already set)
                if 'rtng' not in audio.tags:
                    audio.tags['rtng'] = [0]  # 0 = No rating, 2 = Clean, 4 = Explicit
                
                else:
                    logger.warning("First file has no tags or could not be loaded")

            # Copy picture data if available. Prefer audio file metadata first (covr/APIC),
            # then fall back to folder images.
            picture_copied = False
            
            # First priority: Check audio file metadata (covr or APIC)
            if source_with_picture:
                source_audio = MutagenFile(source_with_picture)
                if source_audio and hasattr(source_audio, 'tags') and source_audio.tags:
                    # First check for M4A cover art (covr tag)
                    if 'covr' in source_audio.tags:
                        covr_data = source_audio.tags['covr']
                        if isinstance(covr_data, list) and len(covr_data) > 0:
                            # M4A files already have MP4Cover objects, copy directly
                            try:
                                logger.debug("Copying covr from source: type=%s, sample type=%s", type(covr_data), type(covr_data[0]))
                            except Exception:
                                pass
                            audio.tags['covr'] = covr_data
                            picture_copied = True
                            logger.info("Cover art copied from M4A source")

                    # If no M4A cover found, check for MP3-style APIC tags
                    if not picture_copied:
                        for tag_name in source_audio.tags:
                            if 'APIC' in tag_name or 'PIC' in tag_name:
                                try:
                                    picture_data = source_audio.tags[tag_name]
                                except Exception:
                                    continue

                                # Normalize to a single picture object
                                if isinstance(picture_data, list) and len(picture_data) > 0:
                                    pic = picture_data[0]
                                else:
                                    pic = picture_data

                                # Try to obtain raw image bytes
                                img_bytes = None
                                try:
                                    if hasattr(pic, 'data'):
                                        img_bytes = pic.data
                                    elif isinstance(pic, (bytes, bytearray)):
                                        img_bytes = bytes(pic)
                                except Exception:
                                    logger.debug("Failed to read image bytes from tag %s", tag_name, exc_info=True)
                                    img_bytes = None

                                if img_bytes:
                                    try:
                                        from mutagen.mp4 import MP4Cover
                                        audio.tags['covr'] = [MP4Cover(img_bytes)]
                                    except Exception:
                                        # As a fallback, store raw bytes
                                        audio.tags['covr'] = [img_bytes]

                                    picture_copied = True
                                    logger.info("Cover art copied from MP3 source (converted to MP4Cover, %d bytes)", len(img_bytes))
                                    break

            # Second priority: Fall back to folder images if no audio metadata found
            if not picture_copied:
                try:
                    source_folder = os.path.dirname(source_with_picture) if source_with_picture else os.path.dirname(first_file)
                    candidates = []
                    for name in ['Folder.jpg', 'Folder.jpeg', 'cover.jpg', 'cover.jpeg', 'albumart.jpg']:
                        candidate = os.path.join(source_folder, name)
                        if os.path.exists(candidate):
                            candidates.append(candidate)
                    # Also include any jpg/png images and pick the largest
                    for ext in ('*.jpg', '*.jpeg', '*.png'):
                        for p in glob.glob(os.path.join(source_folder, ext)):
                            if p not in candidates:
                                candidates.append(p)

                            if candidates:
                                # Choose the largest file by size
                                best = max(candidates, key=lambda p: os.path.getsize(p))
                                try:
                                    with open(best, 'rb') as imgf:
                                        data = imgf.read()
                                    from mutagen.mp4 import MP4Cover
                                    # Don't specify format to preserve original data
                                    cover_obj = MP4Cover(data)
                                    audio.tags['covr'] = [cover_obj]
                                    picture_copied = True
                                    logger.info("Cover art copied from folder image: %s", best)
                                except Exception as e:
                                    logger.warning("Failed to copy folder image %s: %s", best, e)
                    
                except Exception:
                    pass

            if not picture_copied:
                logger.warning("No cover art found in source file or folder")

        except Exception as e:
            logger.warning("Failed to copy metadata to M4B: %s", e)
            pass  # Skip metadata if extraction fails

        # If a CLI provided series_name was supplied, sanitize and apply it now
        try:
            if series_name:
                try:
                    cleaned = sanitize_series_name(series_name)
                except Exception:
                    cleaned = series_name

                if cleaned:
                    try:
                        # Set MP4 grouping atom
                        audio.tags['\xa9grp'] = [cleaned]
                    except Exception:
                        pass

                    try:
                        # Also set freeform iTunes SERIES atom as MP4FreeForm or bytes
                        try:
                            from mutagen.mp4 import MP4FreeForm
                            audio.tags['----:com.apple.iTunes:SERIES'] = [MP4FreeForm(cleaned.encode('utf-8'))]
                        except Exception:
                            # Fallback to raw bytes
                            audio.tags['----:com.apple.iTunes:SERIES'] = [cleaned.encode('utf-8')]
                    except Exception:
                        pass

        except Exception:
            pass

            # Ensure album_sort and title_sort are explicitly written.
            try:
                # album_sort ('soal') is typically copied from mutated files earlier; leave as-is.
                # For title_sort ('sonm'), always set it to the uncleaned filename (file stem) of the first source file
                if source_files and len(source_files) > 0:
                    first_source = source_files[0]
                    file_stem = os.path.splitext(os.path.basename(first_source))[0]
                    # Write sonm as a list of UTF-8 strings (override to ensure consistency)
                    audio.tags['sonm'] = [str(file_stem)]
                    try:
                        audio.save()
                    except Exception:
                        pass
            except Exception:
                pass

                # If we did not already pre-seed trkn from sources above, consult
                # the consolidated helper as a final attempt. We avoid overwriting
                # an existing source-derived value.
            try:
                if not track_written:
                    try:
                        track_val, track_from_source = _determine_track_value_for_sources(source_files, MutagenFile)
                    except Exception:
                        track_val, track_from_source = (None, False)

                    if track_val is not None:
                        try:
                            audio.tags['trkn'] = track_val
                        except Exception:
                            pass
                        try:
                            track_written = bool(track_from_source)
                        except Exception:
                            pass
                        try:
                            logger.debug("Helper-determined trkn applied: %r (source-derived=%r)", track_val, track_from_source)
                        except Exception:
                            pass
                        try:
                            audio.save()
                        except Exception:
                            pass
            except Exception:
                pass
            # Ensure track number (trkn) is present on the final M4B.
            try:
                # Set track number to 1 of N where N is the number of source files
                # that were concatenated into this M4B. This provides a consistent
                # trkn value on the final single-file M4B (track 1 of N).
                total = len(source_files) if source_files else 0
                if total and total > 0:
                    # Don't overwrite an existing trkn set above - preserve
                    # original per-chapter track numbers when available.
                    try:
                        if not track_written and ('trkn' not in audio.tags or not audio.tags.get('trkn')):
                            audio.tags['trkn'] = [(1, int(total))]
                        else:
                            logger.debug("Existing trkn present or already written, skipping default overwrite")
                    except Exception:
                        if not track_written:
                            audio.tags['trkn'] = [(1, int(total))]
                else:
                    # Fallback: try to copy trkn from the first source file if available
                    try:
                        import re
                        # Only attempt to copy from the first source as a safety net
                        # when we have not already written a track value from source metadata.
                        if not track_written and first_file:
                            fa = MutagenFile(first_file)
                            if fa and hasattr(fa, 'tags') and fa.tags:
                                # Prefer MP4 trkn if present
                                if 'trkn' in fa.tags:
                                    audio.tags['trkn'] = fa.tags['trkn']
                                else:
                                    # Try to find ID3/TRCK and convert
                                    for ak in fa.tags.keys():
                                        try:
                                            if isinstance(ak, str) and ak.upper().startswith('TRCK'):
                                                # Use reformat helper to convert to MP4 format
                                                formatted = reformat_tag_for_file_type('track_number', fa.tags[ak], 'mp4')
                                                audio.tags['trkn'] = formatted
                                                break
                                        except Exception:
                                            continue
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

        audio.save()

    # Ensure a deterministic series index (tvsn) is present on the final M4B.
    # Prefer an explicit numeric prefix from the original source folder when available.
    try:
        # Use MP4 class resolved earlier (supports injection via mp4_class)
        # Attempt to infer from original_source_files (passed in by convert_folder_to_m4b)
        inferred = None
        if original_source_files and len(original_source_files) > 0:
            try:
                orig_folder = os.path.basename(os.path.dirname(original_source_files[0]))
                inferred = parse_series_index_from_folder_name(orig_folder)
            except Exception:
                inferred = None

        # Fallback: try to infer from the provided source_files (temp/mutated files)
        if inferred is None and source_files and len(source_files) > 0:
            try:
                src_folder = os.path.basename(os.path.dirname(source_files[0]))
                inferred = parse_series_index_from_folder_name(src_folder)
            except Exception:
                inferred = None

        # If we have an inferred numeric index, set tvsn explicitly
        if inferred:
            try:
                audio = MP4(m4b_path)
                if audio.tags is None:
                    from mutagen.mp4 import MP4Tags
                    audio.tags = MP4Tags()
                audio.tags['tvsn'] = [int(inferred)]
                # Also mirror to ID3-style grouping if present
                if '\xa9grp' not in audio.tags and audio.tags.get('----:com.apple.iTunes:SERIES'):
                    # No-op: grouping likely already set, but ensure SERIES freeform exists
                    pass
                audio.save()
                logger.info("Set deterministic tvsn=%s on %s", inferred, m4b_path)
            except Exception:
                logger.debug("Failed to set deterministic tvsn for %s", m4b_path, exc_info=True)
    except Exception:
        # If MP4 support not available or inference failed, skip silently
        pass

    # Final attempt: if the first source file had an MP4 'trkn' value, ensure
    # it is copied to the final M4B. This is a safety net to preserve original
    # per-chapter track numbers in cases where earlier writes failed.
    try:
        # Only attempt this safety-net copy if we have NOT already written
        # an explicit track value from source metadata. Respect the
        # track_written flag so we don't overwrite a source-derived trkn.
        if (not track_written) and source_files and len(source_files) > 0:
            first_src = source_files[0]
            try:
                fa = MutagenFile(first_src)
                if fa and hasattr(fa, 'tags') and fa.tags and 'trkn' in fa.tags:
                    try:
                        audio = MP4(m4b_path)
                        if audio.tags is None:
                            audio.tags = MP4Tags()
                        audio.tags['trkn'] = fa.tags['trkn']
                        audio.save()
                        logger.info("Copied original trkn from %s to %s", first_src, m4b_path)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    except Exception:
        pass

    # Final safety: ensure sonm (title_sort) equals the uncleaned filename stem
    try:
        if source_files and len(source_files) > 0:
            first_src = source_files[0]
            file_stem = os.path.splitext(os.path.basename(first_src))[0]
            try:
                audio = MP4(m4b_path)
                if audio.tags is None:
                    audio.tags = MP4Tags()
                # Always set/override sonm to ensure deterministic title_sort
                audio.tags['sonm'] = [str(file_stem)]
                audio.save()
            except Exception:
                pass
    except Exception:
        pass

    # Finally, ensure a trkn (track number) atom exists on the final M4B.
    try:
        # Use MP4/MP4Tags resolved earlier (may be injected for tests)
        audio = MP4(m4b_path)
        if audio.tags is None:
            audio.tags = MP4Tags()
        total = len(source_files) if source_files else 0
        if total and total > 0:
            # Only set a default trkn if one wasn't already written above and
            # the helper did not indicate the track came from source metadata.
            # This preserves original source track numbers when available.
            try:
                if (not track_written) and ('trkn' not in audio.tags or not audio.tags.get('trkn')):
                    audio.tags['trkn'] = [(1, int(total))]
                    audio.save()
                    logger.info("Set default trkn=(1,%d) on %s", int(total), m4b_path)
                else:
                    logger.debug("trkn already present on %s or was source-derived, not overwriting", m4b_path)
            except Exception:
                # If anything goes wrong, don't crash the whole operation
                logger.debug("Failed to set default trkn on %s", m4b_path, exc_info=True)
    except Exception:
        logger.debug("Failed to set trkn on %s", m4b_path, exc_info=True)


def move_to_destination(source_path, destination_path, folder_type):
    """
    Move a folder to the destination, creating subdirectories as needed.
    
    Args:
        source_path: Path to the source folder
        destination_path: Path to the destination directory
        folder_type: "novel" or "series" (affects folder structure)
    
    Returns:
        Path to the final destination
    """
    source_path = source_path
    destination_path = destination_path
    
    # Ensure destination directory exists
    if not os.path.exists(destination_path):
        os.makedirs(destination_path)
    
    # For series, create a subdirectory based on the folder name
    if folder_type == "series":
        # Get the parent folder name for series organization
        parent_name = os.path.basename(os.path.dirname(source_path))
        series_dest = os.path.join(destination_path, parent_name)
        if not os.path.exists(series_dest):
            os.makedirs(series_dest)
        destination_path = series_dest
    
    # Move the folder
    folder_name = os.path.basename(source_path)
    final_dest = os.path.join(destination_path, folder_name)
    
    # If destination already exists, remove it first
    if os.path.exists(final_dest):
        shutil.rmtree(final_dest)
    
    shutil.move(source_path, final_dest)
    
    return final_dest


def analyze_folder_structure(source_path):
    """
    Recursively analyze folder structure to classify folders as series or novel.
    
    Args:
        source_path: Root path to analyze
        
    Returns:
        List of dicts with 'folder_type', 'folder' keys
    """
    results = []
    
    def has_audio_files(folder_path):
        """Check if folder contains audio files"""
        audio_extensions = ['*.m4a', '*.mp3']
        for ext in audio_extensions:
            if list(glob.glob(os.path.join(folder_path, ext))):
                return True
        return False
    
    def analyze_recursive(current_path, depth=0):
        """Recursively analyze folders"""
        if not os.path.isdir(current_path):
            return
            
        # Check if this folder has audio files directly
        if has_audio_files(current_path):
            # Classify based on depth from source
            # Direct children of source = novel
            # Deeper than direct children = series
            if depth == 1:
                folder_type = 'novel'
            else:
                folder_type = 'series'
                
            results.append({
                'folder_type': folder_type,
                'folder': current_path
            })
            return  # Don't recurse deeper if it has audio files
        
        # If no audio files directly, continue recursing
        subfolders = [f for f in os.listdir(current_path) 
                     if os.path.isdir(os.path.join(current_path, f))]
        
        for subfolder in subfolders:
            subfolder_path = os.path.join(current_path, subfolder)
            analyze_recursive(subfolder_path, depth + 1)
    
    analyze_recursive(source_path)
    return results


def cmd_convert(args, original_source_path=None):
    """Convert a folder of audio files to a single M4B file with chapters"""
    import os  # Ensure os is available for this function
    
    # Import our new enhancement modules
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.validation import check_dependencies, validate_folder_structure, validate_output_path, estimate_processing_time
            from audiobook_p.progress_simple import Logger, safe_operation, ask_user_confirmation, display_operation_summary, show_processing_estimate
            from audiobook_p.config import get_config
        except ImportError:
            # Fallback for when running as script
            import sys
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from validation import check_dependencies, validate_folder_structure, validate_output_path, estimate_processing_time
            from progress_simple import Logger, safe_operation, ask_user_confirmation, display_operation_summary, show_processing_estimate
            from config import get_config
        
        logger = Logger()
        config = get_config()
        
    except ImportError:
        # Fallback to basic operation if enhancement modules not available
        logger = None
        config = None
    
    source_path = args.source
    output_path = args.output

    try:
        # Enhanced validation if available
        if logger:
            logger.info("Validating input and dependencies...")
        
        # Check dependencies first
        try:
            if config:
                check_dependencies()
            if logger:
                logger.info("Dependencies check passed")
        except Exception as e:
            if logger:
                logger.error("Dependency check failed: {}".format(e))
            else:
                print("Warning: {}".format(e))
        
        # Validate source path
        if not os.path.isdir(source_path):
            error_msg = "Error: Source must be a directory: {}".format(source_path)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return
        
        # Enhanced folder validation if available
        try:
            if config:
                audio_files = validate_folder_structure(source_path)
                if logger:
                    logger.info("Found {} valid audio files".format(len(audio_files)))
            else:
                # Basic validation fallback
                audio_extensions = ['*.m4a', '*.mp3']
                audio_files = []
                for ext in audio_extensions:
                    audio_files.extend(list(glob.glob(os.path.join(source_path, ext))))
                audio_files.sort(key=natural_sort_key)
                
                if not audio_files:
                    raise ValueError("No audio files found")
                    
        except Exception as e:
            error_msg = "Source validation failed: {}".format(e)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return

        # If output_path is a directory, generate filename from source folder name
        if os.path.isdir(output_path):
            source_folder_name = os.path.basename(source_path.rstrip('/\\'))

            # Sanitize the folder name for use as a filename:
            # - Remove leading/trailing whitespace
            # - Remove leading hyphens or punctuation like '- ' or '_ '
            # - Remove simple numeric prefixes like '1-' or '01 ' while keeping the rest
            def _sanitize_filename(name):
                import re
                if not name:
                    return name
                s = name.strip()
                # Remove leading hyphens and punctuation
                s = re.sub(r'^[\-\._\s]+', '', s)
                # Remove leading numeric prefixes like '01 -', '1-', '1 '
                s = re.sub(r'^\d{1,3}[\s\-:\._]+', '', s)
                # Collapse multiple spaces
                s = re.sub(r'\s{2,}', ' ', s)
                return s.strip()

            safe_name = _sanitize_filename(source_folder_name)
            output_filename = "{}.m4b".format(safe_name if safe_name else source_folder_name)
            final_output_path = os.path.join(output_path, output_filename)
        else:
            final_output_path = output_path

        # Enhanced output validation if available
        try:
            if config:
                final_output_path = validate_output_path(final_output_path)
        except Exception as e:
            error_msg = "Output validation failed: {}".format(e)
            if logger:
                logger.error(error_msg)
            else:
                print(error_msg)
            return

        # Show processing estimate if available
        if config and logger:
            try:
                estimate = estimate_processing_time(audio_files)
                show_processing_estimate(estimate['file_count'], estimate['total_size_mb'])
                
                # Ask for confirmation for large operations
                if estimate['estimated_minutes'] > 5:
                    confirmation_msg = "This operation may take {:.1f} minutes. Continue?".format(estimate['estimated_minutes'])
                    if not ask_user_confirmation(confirmation_msg, True):
                        logger.info("Operation cancelled by user")
                        return
                        
            except Exception:
                pass  # Continue without estimate if it fails

        # Convert to M4B with enhanced progress tracking
        def convert_operation():
            return convert_folder_to_m4b(str(source_path), str(final_output_path), config, args.sort_by, original_source_path, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
        
        if logger:
            m4b_path = safe_operation("M4B Conversion", convert_operation)
            if m4b_path is None:
                return  # Operation failed
        else:
            m4b_path = convert_folder_to_m4b(
                str(source_path),
                str(final_output_path),
                config,
                args.sort_by,
                original_source_path,
                chapter_titles=getattr(args, 'chapter_titles', False),
                series_name=getattr(args, 'series_name', None)
            )

        # Display results
        result = {
            "operation": "convert",
            "source_folder": str(source_path),
            "output_file": m4b_path,
            "format": "M4B"
        }
        
        # Enhanced summary if available
        if logger and os.path.exists(m4b_path):
            try:
                output_size = os.path.getsize(m4b_path)
                stats = {
                    'source_files': len(audio_files),
                    'output_file': os.path.basename(m4b_path),
                    'output_size': output_size,
                    'compression_ratio': "{}:1 files".format(len(audio_files))
                }
                display_operation_summary("M4B Conversion", stats)
            except Exception:
                pass
        
        print(json.dumps(result, indent=2))

    except Exception as e:
        error_msg = "Error: {}".format(e)
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)


def cmd_extract(args):
    """Extract metadata from audio files"""
    source_path = args.source

    try:
        if os.path.isfile(source_path):
            # Process single file
            if os.path.splitext(source_path)[1].lower() not in ['.m4a', '.mp3', '.m4b']:
                print("File is not an audio file: {}".format(source_path))
                return

            metadata = extract_metadata_from_file(str(source_path))
            # Convert all values to strings to ensure JSON serializability
            serializable_metadata = {}
            for key, value in metadata.items():
                try:
                    # Convert to string while preserving Unicode characters
                    if isinstance(value, str):
                        serializable_metadata[key] = value
                    elif isinstance(value, (int, float, bool)):
                        serializable_metadata[key] = value
                    elif hasattr(value, '__str__'):
                        serializable_metadata[key] = str(value)
                    else:
                        serializable_metadata[key] = repr(value)
                except Exception as e:
                    # Fallback to string representation
                    serializable_metadata[key] = "Error converting value: {}".format(str(e))
            result = {
                "file": str(source_path),
                "metadata": serializable_metadata
            }
            print(json.dumps(result, indent=2))

        elif os.path.isdir(source_path):
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(glob.glob(os.path.join(source_path, ext))):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(os.path.isdir(os.path.join(source_path, child)) for child in os.listdir(source_path) if os.path.isdir(os.path.join(source_path, child)))

            if has_individual_files and not has_subfolders:
                # Simple novel folder
                results = extract_metadata_from_folder(str(source_path), "novel")
                print(json.dumps(results, indent=2))
            elif has_subfolders:
                # Could be series or batch - use batch_verify to analyze
                if batch_verify:
                    try:
                        batch_result = batch_verify(str(source_path))
                        if batch_result and isinstance(batch_result, list):
                            # Extract each folder individually
                            all_results = []
                            for item in batch_result:
                                folder_type = item.get('folder_type')
                                folder_path = item.get('folder')
                                if folder_type and folder_path:
                                    try:
                                        folder_result = extract_metadata_from_folder(folder_path, folder_type)
                                        all_results.append(folder_result)
                                    except Exception as e:
                                        all_results.append({
                                            "folder_type": folder_type,
                                            "folder": folder_path,
                                            "error": str(e)
                                        })

                            print(json.dumps(all_results, indent=2))
                            return
                    except Exception:
                        pass

                # Fallback: try series_verify
                if series_verify:
                    try:
                        series_result = series_verify(str(source_path))
                        if series_result and isinstance(series_result, list) and len(series_result) > 0:
                            # Extract series folders
                            all_results = []
                            for item in series_result:
                                if item.get('type') == 'series' and item.get('paths'):
                                    for path in item['paths']:
                                        try:
                                            folder_result = extract_metadata_from_folder(path, "series")
                                            all_results.append(folder_result)
                                        except Exception as e:
                                            all_results.append({
                                                "folder_type": "series",
                                                "folder": path,
                                                "error": str(e)
                                            })
                            if all_results:
                                print(json.dumps(all_results, indent=2))
                                return
                    except Exception:
                        pass

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        print("Error: {}".format(e))


def cmd_mutate(args):
    """Mutate metadata and move files"""
    source_path = args.source
    destination_path = args.destination

    try:
        if os.path.isfile(source_path):
            print("Mutate operation requires a folder. Use extract for single files.")
            return

        elif os.path.isdir(source_path):
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(glob.glob(os.path.join(source_path, ext))):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(os.path.isdir(os.path.join(source_path, child)) for child in os.listdir(source_path) if os.path.isdir(os.path.join(source_path, child)))

            if has_individual_files and not has_subfolders:
                # Simple novel folder
                # Extract metadata first, then mutate
                metadata_dict = extract_metadata_from_folder(str(source_path), "novel")
                mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                final_path = move_to_destination(mutated_path, str(destination_path), "novel")
                result = {
                    "operation": "mutate",
                    "original_folder": str(source_path),
                    "mutated_folder": mutated_path,
                    "final_destination": final_path,
                    "folder_type": "novel"
                }
                print(json.dumps(result, indent=2))
            elif has_subfolders:
                # Could be series or batch - use batch_verify to analyze
                if batch_verify:
                    try:
                        batch_result = batch_verify(str(source_path))
                        if batch_result and isinstance(batch_result, list):
                            # Mutate each folder individually
                            mutated_results = []
                            for item in batch_result:
                                folder_type = item.get('folder_type')
                                folder_path = item.get('folder')
                                if folder_type and folder_path:
                                    try:
                                        # Extract metadata first
                                        metadata_dict = extract_metadata_from_folder(folder_path, folder_type)
                                        # Then mutate
                                        mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                        # Move to destination
                                        final_path = move_to_destination(mutated_path, str(destination_path), folder_type)
                                        mutated_results.append({
                                            "folder_type": folder_type,
                                            "original_folder": folder_path,
                                            "mutated_folder": mutated_path,
                                            "final_destination": final_path
                                        })
                                    except Exception as e:
                                        mutated_results.append({
                                            "folder_type": folder_type,
                                            "folder": folder_path,
                                            "error": str(e)
                                        })

                            result = {
                                "operation": "mutate_batch",
                                "results": mutated_results
                            }
                            print(json.dumps(result, indent=2))
                            return
                    except Exception:
                        pass

                # Fallback: try series_verify
                if series_verify:
                    try:
                        series_result = series_verify(str(source_path))
                        if series_result and isinstance(series_result, list) and len(series_result) > 0:
                            # Mutate series folders
                            mutated_results = []
                            for item in series_result:
                                if item.get('type') == 'series' and item.get('paths'):
                                    for path in item['paths']:
                                        try:
                                            metadata_dict = extract_metadata_from_folder(path, "series")
                                            mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                            final_path = move_to_destination(mutated_path, str(destination_path), "series")
                                            mutated_results.append({
                                                "folder_type": "series",
                                                "original_folder": path,
                                                "mutated_folder": mutated_path,
                                                "final_destination": final_path
                                            })
                                        except Exception as e:
                                            mutated_results.append({
                                                "folder_type": "series",
                                                "folder": path,
                                                "error": str(e)
                                            })
                            if mutated_results:
                                result = {
                                    "operation": "mutate_series",
                                    "results": mutated_results
                                }
                                print(json.dumps(result, indent=2))
                                return
                    except Exception:
                        pass

                # Final fallback: use our own recursive analysis
                print("Using built-in folder structure analysis...")
                try:
                    folder_structure = analyze_folder_structure(str(source_path))
                    if folder_structure:
                        # Mutate each folder individually
                        mutated_results = []
                        for item in folder_structure:
                            folder_type = item.get('folder_type')
                            folder_path = item.get('folder')
                            if folder_type and folder_path:
                                try:
                                    # Extract metadata first
                                    metadata_dict = extract_metadata_from_folder(folder_path, folder_type)
                                    # Then mutate
                                    mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False))
                                    # Move to destination
                                    final_path = move_to_destination(mutated_path, str(destination_path), folder_type)
                                    mutated_results.append({
                                        "folder_type": folder_type,
                                        "original_folder": folder_path,
                                        "mutated_folder": mutated_path,
                                        "final_destination": final_path
                                    })
                                except Exception as e:
                                    mutated_results.append({
                                        "folder_type": folder_type,
                                        "folder": folder_path,
                                        "error": str(e)
                                    })

                        result = {
                            "operation": "mutate_batch_fallback",
                            "results": mutated_results
                        }
                        print(json.dumps(result, indent=2))
                        return
                except Exception as e:
                    print("Fallback analysis failed: {}".format(e))

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        print("Error: {}".format(e))


def cmd_config(args):
    """Manage configuration settings"""
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.config import get_config, create_default_config_file
        except ImportError:
            # Fallback for when running as script
            import sys
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from config import get_config, create_default_config_file
        
        config = get_config()
        
        if args.show:
            config.show_config()
        elif args.reset:
            config.reset_to_defaults()
            config.save()
            print("Configuration reset to defaults and saved.")
        elif args.create_default:
            # If args.create_default is True, pass None to create default in cwd.
            create_default_config_file(None if args.create_default is True else args.create_default)
        elif args.set:
            try:
                key, value = args.set.split('=', 1)
                # Try to parse value as JSON for proper type handling
                try:
                    import json
                    parsed_value = json.loads(value)
                except ValueError:  # json.JSONDecodeError doesn't exist in Python 2.7
                    # If not valid JSON, treat as string
                    parsed_value = value
                
                config.set(key, parsed_value)
                config.save()
                print("Set {} = {}".format(key, parsed_value))
            except ValueError:
                print("Error: --set requires format key=value")
        elif args.get:
            value = config.get(args.get)
            print("{} = {}".format(args.get, value))
        else:
            print("Configuration file location: {}".format(config.config_path or "Not found"))
            print("Use --help for configuration options")
            
    except ImportError:
        print("Configuration management not available")


def cmd_mutate_convert(args):
    """Mutate metadata, create temporary files, then convert to M4B and send to destination"""
    import tempfile
    import shutil
    
    source_path = args.source
    destination_path = args.destination
    
    # Create a temporary directory for the mutated files
    temp_dir = tempfile.mkdtemp(prefix="mutate_convert_")
    
    try:
        logger.info("Starting mutate-convert operation")
        logger.info("Source: %s", source_path)
        logger.info("Destination: %s", destination_path)
        logger.debug("Temporary directory: %s", temp_dir)
        
        if os.path.isfile(source_path):
            print("Mutate-convert operation requires a folder. Use extract for single files.")
            return

        elif os.path.isdir(source_path):
            # Step 1: Mutate the source files to temporary directory
            logger.info("Step 1: Mutating metadata and copying files...")
            
            # Check if this folder has individual audio files
            audio_extensions = ['*.m4a', '*.mp3']
            has_individual_files = False
            for ext in audio_extensions:
                if list(glob.glob(os.path.join(source_path, ext))):
                    has_individual_files = True
                    break

            # Check if this folder has subfolders
            has_subfolders = any(os.path.isdir(os.path.join(source_path, child)) for child in os.listdir(source_path) if os.path.isdir(os.path.join(source_path, child)))

            if has_individual_files and not has_subfolders:
                # Simple novel folder
                # Extract metadata first, then mutate
                metadata_dict = extract_metadata_from_folder(str(source_path), "novel")
                mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                temp_mutated_path = move_to_destination(mutated_path, temp_dir, "novel")
                
                logger.info("Mutated files created in: %s", temp_mutated_path)
                
                # Step 2: Convert the mutated files to M4B
                logger.info("Step 2: Converting mutated files to M4B...")
                
                # Create a mock args object for cmd_convert
                class MockArgs:
                    def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None):
                        self.source = source
                        self.output = output
                        self.sort_by = sort_by
                        self.chapter_titles = chapter_titles
                        self.series_name = series_name
                
                convert_args = MockArgs(temp_mutated_path, destination_path, args.sort_by, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                cmd_convert(convert_args, source_path)  # Pass original source path
                
                logger.info("Mutate-convert operation completed successfully")
                logger.info("Final M4B file location: %s", destination_path)
                
            elif has_subfolders:
                # Could be series or batch - use batch_verify to analyze
                if batch_verify:
                    try:
                        batch_result = batch_verify(str(source_path))
                        if batch_result and isinstance(batch_result, list):
                            # Process each folder individually
                            convert_results = []
                            for item in batch_result:
                                folder_type = item.get('folder_type')
                                folder_path = item.get('folder')
                                if folder_type and folder_path:
                                    try:
                                        # Extract metadata first
                                        metadata_dict = extract_metadata_from_folder(folder_path, folder_type)
                                        # Then mutate
                                        mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                        # Move to temp directory
                                        temp_mutated_path = move_to_destination(mutated_path, temp_dir, folder_type)
                                        
                                        # Convert to M4B
                                        # Create a mock args object for cmd_convert
                                        class MockArgs:
                                            def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None):
                                                self.source = source
                                                self.output = output
                                                self.sort_by = sort_by
                                                self.chapter_titles = chapter_titles
                                                self.series_name = series_name

                                        # Generate output filename from folder name
                                        folder_name = os.path.basename(temp_mutated_path)
                                        m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))

                                        convert_args = MockArgs(temp_mutated_path, m4b_output_path, args.sort_by, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                        cmd_convert(convert_args, folder_path)  # Pass original folder path
                                        
                                        convert_results.append({
                                            "folder_type": folder_type,
                                            "original_folder": folder_path,
                                            "mutated_folder": temp_mutated_path,
                                            "m4b_file": m4b_output_path
                                        })
                                    except Exception as e:
                                        convert_results.append({
                                            "folder_type": folder_type,
                                            "folder": folder_path,
                                            "error": str(e)
                                        })

                            result = {
                                "operation": "mutate_convert_batch",
                                "results": convert_results
                            }
                            print(json.dumps(result, indent=2))
                            return
                    except Exception:
                        pass

                # Fallback: try series_verify
                if series_verify:
                    try:
                        series_result = series_verify(str(source_path))
                        if series_result and isinstance(series_result, list) and len(series_result) > 0:
                            # Process series folders
                            convert_results = []
                            for item in series_result:
                                if item.get('type') == 'series' and item.get('paths'):
                                    for path in item['paths']:
                                        try:
                                            metadata_dict = extract_metadata_from_folder(path, "series")
                                            mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                            temp_mutated_path = move_to_destination(mutated_path, temp_dir, "series")
                                            
                                            # Convert to M4B
                                            class MockArgs:
                                                def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None):
                                                    self.source = source
                                                    self.output = output
                                                    self.sort_by = sort_by
                                                    self.chapter_titles = chapter_titles
                                                    self.series_name = series_name
                                            
                                            folder_name = os.path.basename(temp_mutated_path)
                                            m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))
                                            
                                            convert_args = MockArgs(temp_mutated_path, m4b_output_path, args.sort_by, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                            cmd_convert(convert_args, path)  # Pass original folder path
                                            
                                            convert_results.append({
                                                "folder_type": "series",
                                                "original_folder": path,
                                                "mutated_folder": temp_mutated_path,
                                                "m4b_file": m4b_output_path
                                            })
                                        except Exception as e:
                                            convert_results.append({
                                                "folder_type": "series",
                                                "folder": path,
                                                "error": str(e)
                                            })
                            if convert_results:
                                result = {
                                    "operation": "mutate_convert_series",
                                    "results": convert_results
                                }
                                print(json.dumps(result, indent=2))
                                return
                    except Exception:
                        pass

                # Final fallback: use our own recursive analysis
                print("Using built-in folder structure analysis...")
                try:
                    folder_structure = analyze_folder_structure(str(source_path))
                    if folder_structure:
                        # Process each folder individually
                        convert_results = []
                        for item in folder_structure:
                            folder_type = item.get('folder_type')
                            folder_path = item.get('folder')
                            if folder_type and folder_path:
                                try:
                                    # Extract metadata first
                                    metadata_dict = extract_metadata_from_folder(folder_path, folder_type)
                                    # Then mutate
                                    mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                    # Move to temp directory
                                    temp_mutated_path = move_to_destination(mutated_path, temp_dir, folder_type)
                                    
                                    # Convert to M4B
                                    class MockArgs:
                                        def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None):
                                            self.source = source
                                            self.output = output
                                            self.sort_by = sort_by
                                            self.chapter_titles = chapter_titles
                                            self.series_name = series_name
                                    
                                    folder_name = os.path.basename(temp_mutated_path)
                                    m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))
                                    
                                    convert_args = MockArgs(temp_mutated_path, m4b_output_path, args.sort_by, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None))
                                    cmd_convert(convert_args, folder_path)  # Pass original folder path
                                    
                                    convert_results.append({
                                        "folder_type": folder_type,
                                        "original_folder": folder_path,
                                        "mutated_folder": temp_mutated_path,
                                        "m4b_file": m4b_output_path
                                    })
                                except Exception as e:
                                    convert_results.append({
                                        "folder_type": folder_type,
                                        "folder": folder_path,
                                        "error": str(e)
                                    })

                        result = {
                            "operation": "mutate_convert_batch_fallback",
                            "results": convert_results
                        }
                        print(json.dumps(result, indent=2))
                        return
                except Exception as e:
                    print("Fallback analysis failed: {}".format(e))

                print("Multi-folder processing not yet supported for mutate-convert")
                return
            else:
                print("No audio files found in source folder")
                return
        else:
            print("Source path does not exist: {}".format(source_path))
            return

    except Exception as e:
        logger.error("Error during mutate-convert operation: %s", e)
        import traceback
        traceback.print_exc()

    finally:
        # Clean up temporary directory
        try:
            logger.info("Cleaning up temporary files...")
            shutil.rmtree(temp_dir)
            logger.info("Temporary directory removed: %s", temp_dir)
        except Exception as e:
            logger.warning("Could not remove temporary directory %s: %s", temp_dir, e)


def cmd_info(args):
    logger.info('audiobook-p v1.0.0')

    # Show additional info if available
    try:
        # Try absolute import first, then relative
        try:
            from audiobook_p.config import get_config
        except ImportError:
            import sys
            import os
            script_dir = os.path.dirname(os.path.abspath(__file__))
            sys.path.insert(0, script_dir)
            from config import get_config
        config = get_config()
        logger.info('Configuration: %s', config.config_path or "Using defaults")
    except ImportError:
        pass

def cli(argv=None):
    parser = argparse.ArgumentParser(prog='audiobook-p', description='Audiobook processing utility')
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Info command
    info_parser = subparsers.add_parser('info', help='Show package info')
    info_parser.set_defaults(func=cmd_info)

    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract metadata from audio files (enclose paths with spaces in quotes)')
    extract_parser.add_argument('source', help='Path to audio file or folder (quotes required if path contains spaces)')
    extract_parser.set_defaults(func=cmd_extract)

    # Mutate command
    mutate_parser = subparsers.add_parser('mutate', help='Mutate metadata and move files (enclose paths with spaces in quotes)')
    mutate_parser.add_argument('source', help='Path to audio folder (quotes required if path contains spaces)')
    mutate_parser.add_argument('destination', help='Destination path for mutated files (quotes required if path contains spaces)')
    mutate_parser.add_argument('--album-sort-prefix', help='String to prefix album_sort with " : " separator')
    mutate_parser.add_argument('--album-suffix', help='String to suffix album with " - " separator')
    mutate_parser.add_argument('--chapter-titles', action='store_true', help='Use "BookName: Chapter X" format for track titles instead of existing titles')
    mutate_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    mutate_parser.set_defaults(func=cmd_mutate)

    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert folder of audio files to M4B with chapters (enclose paths with spaces in quotes)')
    convert_parser.add_argument('source', help='Path to folder containing audio files (quotes required if path contains spaces)')
    convert_parser.add_argument('output', help='Output directory or M4B file path (quotes required if path contains spaces)')
    convert_parser.add_argument('--sort-by', choices=['filename', 'track'], default='filename', help='Sort files by filename (default) or track number metadata')
    convert_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    convert_parser.set_defaults(func=cmd_convert)

    # Mutate-Convert command
    mutate_convert_parser = subparsers.add_parser('mutate-convert', help='Mutate metadata then convert to M4B in one operation (enclose paths with spaces in quotes)')
    mutate_convert_parser.add_argument('source', help='Path to audio folder (quotes required if path contains spaces)')
    mutate_convert_parser.add_argument('destination', help='Destination path for final M4B file (quotes required if path contains spaces)')
    mutate_convert_parser.add_argument('--album-sort-prefix', help='String to prefix album_sort with " : " separator')
    mutate_convert_parser.add_argument('--album-suffix', help='String to suffix album with " - " separator')
    mutate_convert_parser.add_argument('--sort-by', choices=['filename', 'track'], default='filename', help='Sort files by filename (default) or track number metadata')
    mutate_convert_parser.add_argument('--chapter-titles', action='store_true', help='Use "BookName: Chapter X" format for track titles instead of existing titles')
    mutate_convert_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    mutate_convert_parser.set_defaults(func=cmd_mutate_convert)

    # Config command
    config_parser = subparsers.add_parser('config', help='Manage configuration settings')
    config_group = config_parser.add_mutually_exclusive_group()
    config_group.add_argument('--show', action='store_true', help='Show current configuration')
    config_group.add_argument('--reset', action='store_true', help='Reset to default configuration')
    config_group.add_argument('--create-default', nargs='?', const=True, help='Create default config file (optionally specify path)')
    config_group.add_argument('--set', help='Set configuration value (format: key=value)')
    config_group.add_argument('--get', help='Get configuration value')
    config_parser.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    if hasattr(args, 'func'):
        args.func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    cli()
