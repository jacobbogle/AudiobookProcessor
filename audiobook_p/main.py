"""Audiobook P - Main CLI entrypoint for audiobook processing"""

import glob
import os
import argparse
import json
import shutil
import sys
import tempfile
import logging
import mutagen
from mutagen.mp3 import MP3
try:
    from mutagen.id3 import TIT2, TIT1, TPE1, TALB, TCON, TPE2, TCOM, TRCK, TPOS, TSOA, TSOT, TSOP, TSO2, TMED
except Exception:
    TIT2 = TIT1 = TPE1 = TALB = TCON = TPE2 = TCOM = TRCK = TPOS = TSOA = TSOT = TSOP = TSO2 = TMED = None

# Module logger
logger = logging.getLogger(__name__)


def sanitize_string(value, replace_underscores=True):
    """Normalize a string for display/storage.

    - Decodes to str where possible
    - Removes non-printable control characters
    - Optionally replaces runs of underscores with a single space
    - Collapses all whitespace (including newlines/tabs) to single spaces
    - Trims leading/trailing whitespace
    Idempotent on repeated calls and safe for non-string inputs (returns input).
    """
    if value is None:
        return value
    try:
        s = str(value)
    except Exception:
        return value
    try:
        import re
        # First, collapse any whitespace (spaces, newlines, tabs) to single space
        s = re.sub(r'\s+', ' ', s)
        # Remove remaining C0 control characters and DEL (excluding common whitespace we already normalized)
        s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+', '', s)
        if replace_underscores:
            s = re.sub(r'_+', ' ', s)
        # Final trim
        s = s.strip()
    except Exception:
        try:
            s = s.strip()
        except Exception:
            pass
    return s


def book_title_logic(name):
    """Normalize a book/title-like string.

    - Strips leading/trailing whitespace
    - Removes common numeric prefixes like '01 -', '(01) ', '1.'
    - Collapses extra spaces
    - Capitalizes the first alphabetic character (preserves the rest)
    """
    if not name:
        return name
    try:
        s = str(name).strip()
    except Exception:
        return name

    import re
    # Remove common leading numeric prefixes and surrounding punctuation
    s = re.sub(r'^\s*(?:\(|)?\d{1,3}(?:\)|)?(?:\s|-|\.|:)+', '', s)
    # Remove leading punctuation/underscores/spaces
    s = re.sub(r'^[\-\._\s]+', '', s)
    # Collapse multiple spaces
    s = re.sub(r'\s{2,}', ' ', s).strip()

    # Capitalize first alphabetic character only, leave remainder alone
    cleaned = s
    # Ensure sanitized output whenever we perform cleaning
    try:
        cleaned = sanitize_string(cleaned)
    except Exception:
        pass

    for i, ch in enumerate(cleaned):
        if ch.isalpha():
            return cleaned[:i] + ch.upper() + cleaned[i+1:]
    return cleaned


# Optional helpers that may be provided by audiobook_p.validation; import if available
try:
    from audiobook_p.validation import batch_verify, series_verify
except Exception:
    batch_verify = None
    series_verify = None



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
                    logger.debug("_determine_track_value_for_sources found MP4 trkn: %r on %s", fa.tags.get('trkn'), first)
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
                            logger.debug("_determine_track_value_for_sources found ID3 TRCK raw=%r on %s", raw, first)
                        except Exception:
                            pass
                        formatted = reformat_tag_for_file_type('track_number', raw, 'mp4')
                        try:
                            logger.debug("_determine_track_value_for_sources formatted TRCK -> %r", formatted)
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

    # Sanitize the cleaned result so album names are single-line and printable
    try:
        cleaned = sanitize_string(cleaned)
    except Exception:
        pass

    # Title-case the result (simple but effective for album names)
    try:
        return cleaned.title()
    except Exception:
        return cleaned


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
    # Replace hyphens/underscores with spaces and collapse multiple spaces
    s = re.sub(r'[-_]+', ' ', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()

    # Final sanitize pass to ensure consistent single-line output
    try:
        s = sanitize_string(s)
    except Exception:
        pass

    # Title-case for consistent appearance
    try:
        s = s.title()
    except Exception:
        pass

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

    # Prefer deterministic temp folder names in the system temp directory so
    # the copied folder is easier to locate and includes the original basename.
    try:
        base = os.path.basename(source_path) or "source"
        dest_base = f"temp-{base}"
        temp_root = tempfile.gettempdir()

        # Find a non-colliding candidate like /tmp/temp-Source or /tmp/temp-Source-1
        candidate = os.path.join(temp_root, dest_base)
        suffix = 0
        while os.path.exists(candidate):
            suffix += 1
            candidate = os.path.join(temp_root, f"{dest_base}-{suffix}")

        # Copy the tree directly into the candidate path
        shutil.copytree(source_path, candidate)
        return str(candidate)
    except Exception:
        # If the deterministic approach fails (permission issues, non-writable
        # temp dir, etc.), fall back to the previous retrying mkdtemp-based copy
        for attempt in range(max_attempts):
            try:
                # Create a temporary directory
                temp_dir = tempfile.mkdtemp(prefix="audiobook_copy_")
                temp_path = temp_dir

                # Copy the entire folder under the created temp dir
                dest_path = os.path.join(temp_path, os.path.basename(source_path))
                try:
                    # Try Python 3 version first
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                except TypeError:
                    # Older shutil.copytree doesn't accept dirs_exist_ok
                    shutil.copytree(source_path, dest_path)

                # Return the path to the copied folder
                return str(dest_path)

            except Exception:
                # Clean up failed temp directory if it was created
                try:
                    if 'temp_path' in locals() and os.path.exists(temp_path):
                        shutil.rmtree(temp_path)
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


def mutate_metadata(metadata_dict, album_sort_prefix=None, album_suffix=None, sort_by='filename', chapter_titles=False, series_name=None, part_titles=False, author_name=None, narrator_name=None, author_fix=False, in_place=False):
    """
    Mutate metadata for all files in a folder based on folder type.

    Args:
        metadata_dict: Dict with:
            - folder_type: "novel" or "series"
            - folder: path to source folder
            - files: dict of {file_path: metadata_dict}
        album_sort_prefix: Optional string to prefix album_sort with " - " separator
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

    # Copy folder to temp location unless in_place is requested
    if in_place:
        temp_path = source_folder
    else:
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
    
    # Collect per-file rename operations when part_titles is enabled, then
    # perform them after metadata is written to avoid missing files when
    # names are changed mid-iteration.
    rename_ops = []
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
        # NOTE: do not append suffix to the actual ©alb value for series folders
        # because that can introduce universe/branding suffixes (e.g. " - Warhammer 40K").
        # Instead, apply any provided suffix to album_sort so sorting reflects the
        # desired prefix/suffix without contaminating the album display value.
        if album_suffix:
            try:
                current_album_sort = updated_metadata.get('album_sort', '')
                if current_album_sort:
                    updated_metadata['album_sort'] = "{} - {}".format(current_album_sort, album_suffix)
                else:
                    # If no album_sort exists yet, fall back to using album as base
                    current_album = updated_metadata.get('album', '')
                    updated_metadata['album_sort'] = "{} - {}".format(current_album, album_suffix)
            except Exception:
                # On any failure, avoid mutating the display album and skip suffix
                pass

        # If an explicit author/artist name was provided on the CLI, sanitize it and
        # set it on the per-file metadata as the 'artist' tag.
        cleaned_author_input = None
        if author_name:
            try:
                cleaned_author_input = book_title_logic(author_name).strip()
            except Exception:
                try:
                    cleaned_author_input = str(author_name).strip()
                except Exception:
                    cleaned_author_input = None

        if cleaned_author_input:
            try:
                updated_metadata['artist'] = cleaned_author_input
            except Exception:
                pass

        # Respect author_fix flag: apply Last, First -> First Last to any artist/author-like fields
        if author_fix:
            try:
                if updated_metadata.get('artist'):
                    updated_metadata['artist'] = _maybe_fix_author(updated_metadata.get('artist'), True)
                if updated_metadata.get('album_artist'):
                    updated_metadata['album_artist'] = _maybe_fix_author(updated_metadata.get('album_artist'), True)
                if updated_metadata.get('composer'):
                    updated_metadata['composer'] = _maybe_fix_author(updated_metadata.get('composer'), True)
            except Exception:
                pass

        # If an explicit narrator/composer name was provided on the CLI, sanitize it and
        # set it on the per-file metadata as the 'composer' tag.
        cleaned_narrator_input = None
        if narrator_name:
            try:
                cleaned_narrator_input = book_title_logic(narrator_name).strip()
            except Exception:
                try:
                    cleaned_narrator_input = str(narrator_name).strip()
                except Exception:
                    cleaned_narrator_input = None

        if cleaned_narrator_input:
            try:
                updated_metadata['composer'] = cleaned_narrator_input
            except Exception:
                pass

        # Set title: use existing title metadata if available, otherwise use filename as written
        file_stem = os.path.splitext(os.path.basename(source_file))[0]
        if chapter_titles:
            # Primary prefix: use the parent folder name of the file being processed
            # (i.e., the folder that contains the file). This allows titles like
            # "Inkheart - Chapter 1" even when the overall source folder name is
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

            # Use deterministic folder-based chapter titles when chapter_titles is requested.
            # Do not preserve per-file embedded titles in this mode - user requested
            # a consistent "Folder Name - Chapter N" layout.
            if book_name_for_title:
                cleaned_title = "{} - Chapter {}".format(book_name_for_title, index)
            else:
                cleaned_title = "Chapter {}".format(index)

            # If chapter_titles requested, schedule a filename rename to match the cleaned title.
            # This keeps renaming deferred until after metadata is written (via rename_ops).
            try:
                import re
                # Use centralized sanitizer first to remove control chars/underscores
                safe_title = sanitize_string(cleaned_title, replace_underscores=True)
                # Replace filesystem-illegal chars with a neutral separator
                safe_title = re.sub(r'[\\/:\*\?"<>\|]+', ' - ', safe_title)
                safe_title = re.sub(r'^[\-\._\s]+', '', safe_title)
                safe_title = re.sub(r'\s{2,}', ' ', safe_title).strip()
            except Exception:
                safe_title = sanitize_string(str(cleaned_title), replace_underscores=True)

            try:
                _, ext = os.path.splitext(temp_file)
            except Exception:
                ext = ''

            # Build candidate path and ensure we don't clobber other files; append counter on collision
            new_basename = f"{safe_title}{ext}"
            candidate = os.path.join(temp_path, new_basename)
            cnt = 1
            original_basename = new_basename
            while os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(temp_file):
                name_only, e = os.path.splitext(original_basename)
                candidate = os.path.join(temp_path, f"{name_only} ({cnt}){e}")
                cnt += 1

            rename_ops.append((temp_file, candidate))
        elif processed_metadata.get('title') and processed_metadata['title'].strip():
            # Use existing title metadata and apply book_title_logic
            cleaned_title = book_title_logic(processed_metadata['title'])
        else:
            # Use filename as written (without book_title_logic)
            cleaned_title = file_stem
        updated_metadata['title'] = cleaned_title

        # If part_titles option is requested, override title and schedule rename
        if part_titles:
            try:
                logger.debug(f"part_titles active index={index} temp_file={temp_file} temp_path={temp_path}")
                # Part number increments every 10 files: 1 for 1-10, 2 for 11-20, etc.
                part_num = 1 + ((index - 1) // 10)
                # Use 'Part {part} - {index}' format for part titles (no zero-padding)
                # and include the cleaned folder name as a prefix in the per-file title
                # so filesystem metadata/filenames preserve the folder context.
                # part number increments every 10 files: 1 for 1-10, 2 for 11-20, etc.
                # For the initial metadata write (before renaming), set a
                # grouped title like "<Cleaned>: Part {part}" so files in the
                # same part share a consistent title. The detailed per-file
                # title (with index) is enforced later after renames.
                try:
                    group_prefix = f"{cleaned_folder_name}: " if cleaned_folder_name else ''
                except Exception:
                    group_prefix = ''
                grouped_part_title = f"{group_prefix}Part {part_num}"
                updated_metadata['title'] = grouped_part_title

                # Sanitize a filename-friendly base from the cleaned folder name
                try:
                    import re
                    safe_base = re.sub(r'[\\/:\*\?"<>|]+', ' - ', cleaned_folder_name)
                    safe_base = re.sub(r'^[\-\._\s]+', '', safe_base)
                    safe_base = re.sub(r'^\d{1,3}[\s\-:\._]+', '', safe_base)
                    safe_base = re.sub(r'\s{2,}', ' ', safe_base).strip()
                except Exception:
                    # Fallback: very simple safe base
                    safe_base = str(cleaned_folder_name).strip().replace('/', ' - ').replace('\\', ' - ')

                # Keep extension and build candidate
                _, ext = os.path.splitext(temp_file)
                # Use Chapter {part} - ### zero-padded format for filename title component
                new_basename = f"{safe_base}: Part {part_num} - {str(index).zfill(3)}{ext}"
                candidate = os.path.join(temp_path, new_basename)
                # If a file with the target name already exists, append a short counter
                cnt = 1
                original_basename = new_basename
                while os.path.exists(candidate) and os.path.abspath(candidate) != os.path.abspath(temp_file):
                    name_only, e = os.path.splitext(original_basename)
                    candidate = os.path.join(temp_path, f"{name_only} ({cnt}){e}")
                    cnt += 1

                rename_ops.append((temp_file, candidate))
                logger.debug("appended rename %s -> %s", temp_file, candidate)
            except Exception:
                # Non-fatal: continue processing other files
                pass

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
        try:
            logger.debug("Applying metadata to %s", temp_file)
        except Exception:
            pass
        # (Previously had a debug print here for test diagnostics.)
        apply_metadata_to_file(str(temp_file), updated_metadata)
        # If part_titles is requested, ensure the per-file title was actually written.
        # Some toolchains or race conditions can cause the title to be missing; attempt one retry.
        if part_titles:
            # Determine extension to decide which verification to run
            try:
                _, _ext = os.path.splitext(str(temp_file))
                ext_lower = _ext.lower()
            except Exception:
                ext_lower = ''

            # MP4-style verification (©nam)
            if ext_lower in ['.m4a', '.m4b', '.mp4']:
                try:
                    from mutagen.mp4 import MP4
                    try:
                        audio_check = MP4(str(temp_file))
                        tags = getattr(audio_check, 'tags', None)
                        has_title = False
                        if tags is not None:
                            # MP4 atom for title is '\xa9nam'
                            if '\u00a9nam' in tags or '\xa9nam' in tags:
                                val = tags.get('\u00a9nam') or tags.get('\xa9nam')
                                if val:
                                    has_title = True
                        if not has_title:
                            try:
                                apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                            except Exception:
                                logger.debug("Retry apply MP4 title failed for %s", temp_file)
                    except Exception:
                        try:
                            apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                        except Exception:
                            logger.debug("Retry apply MP4 title failed for %s (read error)", temp_file)
                except Exception:
                    # Mutagen.mp4 may not be available; continue
                    pass

            # MP3-style verification (ID3 TIT2)
            if ext_lower == '.mp3':
                # Try a direct ID3 TIT2 write to be deterministic (bypass generic apply path)
                try:
                    from mutagen.id3 import ID3, TIT2, ID3NoHeaderError
                    try:
                        # Load existing ID3 tags or create new
                        try:
                            id3 = ID3(str(temp_file))
                        except ID3NoHeaderError:
                            id3 = ID3()

                        desired_title = updated_metadata.get('title')
                        if desired_title is not None:
                            # Normalize to plain string
                            try:
                                desired_title_str = str(desired_title)
                            except Exception:
                                desired_title_str = repr(desired_title)

                            # Set TIT2 explicitly
                            try:
                                id3.delall('TIT2')
                            except Exception:
                                pass
                            try:
                                id3.add(TIT2(encoding=3, text=desired_title_str))
                                id3.save(str(temp_file))
                            except Exception:
                                # If direct save fails, fall back to generic apply
                                try:
                                    apply_metadata_to_file(str(temp_file), {'title': desired_title})
                                except Exception:
                                    logger.debug("Direct ID3 write failed and fallback apply failed for %s", temp_file)

                        # Verify the write succeeded
                        try:
                            id3_check = ID3(str(temp_file))
                            if 'TIT2' not in id3_check or not id3_check.getall('TIT2'):
                                # Retry via generic apply as last resort
                                try:
                                    apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                                except Exception:
                                    logger.debug("Final retry apply MP3 title failed for %s", temp_file)
                        except Exception:
                            # If verify read fails, attempt generic apply
                            try:
                                apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                            except Exception:
                                logger.debug("Verify/read after ID3 write failed for %s", temp_file)
                    except Exception:
                        # If anything goes wrong with ID3 direct path, fallback to generic apply
                        try:
                            apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                        except Exception:
                            logger.debug("Fallback apply MP3 title failed for %s", temp_file)
                except Exception:
                    # Mutagen.id3 may not be available; fallback to generic apply
                    try:
                        apply_metadata_to_file(str(temp_file), {'title': updated_metadata.get('title')})
                    except Exception:
                        logger.debug("Mutagen.id3 not available and fallback apply failed for %s", temp_file)
    except Exception as e:
        logger.warning("Failed to update metadata for %s: %s", temp_file, e)

    # After writing metadata for each file, perform any scheduled renames
    if rename_ops:
        try:
            # Log planned renames for debug visibility
            logger.debug("rename_ops count=%d", len(rename_ops))
            for src_old, dst_new in rename_ops:
                logger.debug("planned rename %s -> %s", src_old, dst_new)
        except Exception:
            pass

        for src_old, dst_new in rename_ops:
            try:
                exists_src = os.path.exists(src_old)
                exists_dst = os.path.exists(dst_new)
                logger.debug("rename check src_exists=%s dst_exists=%s src=%s dst=%s", exists_src, exists_dst, src_old, dst_new)
                # If the source exists, perform a replace so we explicitly overwrite any existing destination.
                if exists_src:
                    try:
                        # os.replace will atomically replace the destination if it exists
                        os.replace(src_old, dst_new)
                        logger.debug("renamed %s -> %s (replaced if existed)", src_old, dst_new)
                    except Exception as e_replace:
                        # Fallback: try removing destination then rename
                        try:
                            if os.path.exists(dst_new):
                                os.remove(dst_new)
                            os.rename(src_old, dst_new)
                            logger.debug("renamed %s -> %s (removed existing dst)", src_old, dst_new)
                        except Exception as e2:
                            logger.debug("rename failed for %s -> %s: %s", src_old, dst_new, e2)
                else:
                    logger.debug("skipping rename because source missing %s -> %s", src_old, dst_new)
            except Exception as e:
                # Non-fatal; continue with others
                logger.debug("rename failed for %s -> %s: %s", src_old, dst_new, e)

    # Clean up the folder name in temp directory (only when not operating in-place)
    cleaned_temp_folder_name = book_title_logic(os.path.basename(temp_path))
    # Additional sanitization to avoid leading punctuation / numeric prefixes
    import re
    if cleaned_temp_folder_name:
        cleaned_temp_folder_name = re.sub(r'^[\-\._\s]+', '', cleaned_temp_folder_name)
        cleaned_temp_folder_name = re.sub(r'^\d{1,3}[\s\-:\._]+', '', cleaned_temp_folder_name)
        cleaned_temp_folder_name = re.sub(r'\s{2,}', ' ', cleaned_temp_folder_name).strip()
    new_temp_path = os.path.join(os.path.dirname(temp_path), cleaned_temp_folder_name)

    # Rename the folder if name changed (skip when operating in-place)
    if not in_place:
        if cleaned_temp_folder_name != os.path.basename(temp_path):
            os.rename(temp_path, new_temp_path)
            temp_folder = str(new_temp_path)

    # If part_titles requested, enforce deterministic per-file title tags after renames
    if part_titles:
        try:
            target_folder = temp_folder if not in_place else temp_path
            # Find audio files and sort naturally
            files = []
            for ext in ('*.mp3', '*.m4a'):
                files.extend(glob.glob(os.path.join(target_folder, ext)))
            files = sorted(files, key=natural_sort_key)

            # Compute and write titles deterministically from cleaned folder name and index
            for idx, fpath in enumerate(files, 1):
                try:
                    part_num = 1 + ((idx - 1) // 10)
                    try:
                        # Use the cleaned source folder name (the user's original
                        # album/book title) as the prefix so chapter/title atoms
                        # reflect the original folder context instead of the
                        # temporary copy's basename.
                        prefix = f"{cleaned_folder_name} - " if cleaned_folder_name else ''
                    except Exception:
                        prefix = ''
                    per_file_title = f"{prefix}Part {part_num} - {idx}"

                    _, ext = os.path.splitext(fpath)
                    ext = ext.lower()
                    if ext == '.mp3':
                        try:
                            from mutagen.id3 import ID3, TIT2, ID3NoHeaderError
                            try:
                                id3 = ID3(fpath)
                            except ID3NoHeaderError:
                                id3 = ID3()
                            try:
                                id3.delall('TIT2')
                            except Exception:
                                pass
                            id3.add(TIT2(encoding=3, text=str(per_file_title)))
                            id3.save(fpath)
                        except Exception:
                            # Fallback to generic apply
                            try:
                                apply_metadata_to_file(fpath, {'title': per_file_title})
                            except Exception:
                                logger.debug("Failed to write MP3 title for %s", fpath)
                    else:
                        # MP4 family
                        try:
                            from mutagen.mp4 import MP4
                            m = MP4(fpath)
                            m.tags['\u00a9nam'] = [str(per_file_title)]
                            m.save()
                        except Exception:
                            try:
                                apply_metadata_to_file(fpath, {'title': per_file_title})
                            except Exception:
                                logger.debug("Failed to write MP4 title for %s", fpath)
                except Exception:
                    logger.debug("Failed to compute/write per-file title for %s", fpath)
        except Exception:
            # Non-fatal; continue
            pass

    # Return the path where metadata was written. If in_place, this is the original folder.
    return temp_folder if not in_place else temp_path


def _author_last_first_to_first_last(name):
    """Convert a name like "Last, First" into "First Last".

    - Handles simple comma-separated "Last, First Middle" cases by moving
      the first comma-separated element to the end.
    - Uses book_title_logic for sensible capitalization when available.
    """
    if not name:
        return name
    try:
        s = str(name).strip()
    except Exception:
        return name

    # If it contains a comma, assume Last, First [Suffix?]
    if ',' in s:
        parts = [p.strip() for p in s.split(',') if p.strip()]
        if len(parts) >= 2:
            last = parts[0]
            first = ' '.join(parts[1:])
            combined = f"{first} {last}".strip()
            try:
                return book_title_logic(combined)
            except Exception:
                try:
                    return combined.title()
                except Exception:
                    return combined

    # No comma: just return cleaned/title-cased form
    try:
        return book_title_logic(s)
    except Exception:
        try:
            return s.title()
        except Exception:
            return s


def _maybe_fix_author(name, flag):
    """If flag is true and name looks like 'Last, First', return fixed name.

    This helper is defensive: the incoming `name` may be a list, bytes,
    or a mutagen frame-like object. Normalize into a plain string first
    so the Last, First -> First Last logic is applied reliably.
    """
    if not name:
        return name

    # Normalize common container/wrapper types into a plain string
    try:
        val = name
        # Unwrap single-element lists
        if isinstance(val, list) and len(val) > 0:
            val = val[0]

        # If it's bytes, decode sensibly
        if isinstance(val, (bytes, bytearray)):
            try:
                val = val.decode('utf-8')
            except Exception:
                try:
                    val = val.decode('latin-1')
                except Exception:
                    val = str(val)

        # Mutagen frames sometimes expose .text or .data
        if hasattr(val, 'text'):
            try:
                t = val.text
                if isinstance(t, list) and len(t) > 0:
                    val = t[0]
                else:
                    val = t
            except Exception:
                try:
                    val = str(val)
                except Exception:
                    pass

        if hasattr(val, 'data') and not isinstance(val, (str, bytes, bytearray)):
            try:
                # prefer text-like representation when possible
                val = val.data
                if isinstance(val, (bytes, bytearray)):
                    try:
                        val = val.decode('utf-8')
                    except Exception:
                        val = val.decode('latin-1', errors='ignore')
            except Exception:
                pass

        name_str = str(val).strip()
    except Exception:
        try:
            name_str = str(name).strip()
        except Exception:
            return name

    if flag:
        try:
            return _author_last_first_to_first_last(name_str)
        except Exception:
            return name_str
    return name_str


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


def convert_folder_to_m4b(folder_path, output_path, config=None, sort_by='filename', original_source_path=None, chapter_titles=False, series_name=None, temp_copy_path=None, author_fix=False, cli_author=None, album_names=False):
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

            # Default chapter title
            chapter_title = None

            # If chapter_titles mode is requested, keep minimal chapter names for players
            if chapter_titles:
                try:
                    base_for_name = os.path.basename(original_source_path) if original_source_path else os.path.basename(folder_path)
                    book_name = clean_album_name(base_for_name) or folder_basename
                except Exception:
                    book_name = folder_basename
                try:
                    import re
                    book_name = re.sub(r'^Temp-[\w\d\-]*\s*', '', str(book_name), flags=re.IGNORECASE).strip()
                except Exception:
                    pass
                chapter_title = f"Chapter {i+1}"
            else:
                # Prefer the embedded title tag (MP4 ©nam or ID3 TIT2) when present
                try:
                    a = mutagen.File(audio_file)
                    if a is not None and getattr(a, 'tags', None):
                        tags = a.tags
                        # MP4 atom
                        if '\u00a9nam' in tags and tags.get('\u00a9nam'):
                            t = tags.get('\u00a9nam')
                            chapter_title = t[0] if isinstance(t, (list, tuple)) else t
                        elif '\xa9nam' in tags and tags.get('\xa9nam'):
                            t = tags.get('\xa9nam')
                            chapter_title = t[0] if isinstance(t, (list, tuple)) else t
                        # ID3 TIT2 frame
                        elif 'TIT2' in tags and tags.get('TIT2'):
                            t = tags.get('TIT2')
                            try:
                                chapter_title = t.text[0]
                            except Exception:
                                chapter_title = str(t)
                        else:
                            # Try common textual keys as a last resort
                            for candidate in ['title', 'TIT2', 'TIT1', 'TPE1']:
                                if candidate in tags and tags.get(candidate):
                                    v = tags.get(candidate)
                                    chapter_title = v[0] if isinstance(v, (list, tuple)) else v
                                    break
                    # Normalize to string and sanitize
                    if chapter_title is not None:
                        if isinstance(chapter_title, bytes):
                            try:
                                chapter_title = chapter_title.decode('utf-8', errors='ignore')
                            except Exception:
                                chapter_title = str(chapter_title)
                        chapter_title = str(chapter_title).strip()
                        chapter_title = re.sub(r'\.(m4a|m4b|mp3|wav)$', '', chapter_title, flags=re.IGNORECASE)
                        try:
                            chapter_title = sanitize_string(chapter_title, replace_underscores=True)
                        except Exception:
                            pass
                except Exception:
                    chapter_title = None

                # Fallback: attempt to use extracted metadata mapping if direct tags yielded nothing
                if not chapter_title:
                    try:
                        source_metadata = extract_metadata_from_file(audio_file)
                        if source_metadata.get('title'):
                            chapter_title = book_title_logic(source_metadata['title'])
                    except Exception:
                        chapter_title = None

                # Final fallback to filename stem
                if not chapter_title:
                    file_stem = os.path.splitext(os.path.basename(audio_file))[0]
                    chapter_title = book_title_logic(file_stem)

            # Ensure a sanitized title string
            try:
                chapter_title = sanitize_string(chapter_title, replace_underscores=True)
            except Exception:
                try:
                    chapter_title = str(chapter_title)
                except Exception:
                    chapter_title = ''

            # Write chapter metadata
            f.write("\n[CHAPTER]\n")
            f.write("TIMEBASE=1/1000\n")
            f.write("START={}\n".format(current_time))
            f.write("END={}\n".format(current_time + duration_ms))

            # Normalize part/chapter patterns to remove zero-padding in the
            # written chapter title while preserving any leading prefix.
            try:
                import re
                m = re.search(r'^(?:([^:\-\u2013\u2014]+)[:\-\u2013\u2014]\s*)?(?:Chapter|Part)\s*(\d+)\s*-\s*(\d+)\s*$', chapter_title, flags=re.IGNORECASE)
                if m:
                    raw_index = int(m.group(3))
                    computed_part = 1 + ((raw_index - 1) // 10)
                    chapter_title = f"Part {computed_part} - {raw_index}"
            except Exception:
                pass

            f.write("title={}\n".format(chapter_title))

            # Collect chapter info for post-processing (convert to seconds)
            ci = {
                'start': current_time / 1000.0,  # Convert milliseconds to seconds
                'end': (current_time + duration_ms) / 1000.0,
                'title': chapter_title,
                'start_ms': current_time,
                'end_ms': current_time + duration_ms
            }
            if chapter_titles:
                try:
                    ci['book_name'] = book_name
                except Exception:
                    ci['book_name'] = folder_basename
            chapters_info.append(ci)

            current_time += duration_ms

    # Wrap the ffmpeg invocation and post-processing in a single try/finally to
    # ensure temporary files are removed even on error. We intentionally let
    # exceptions propagate after cleanup so callers can detect failures.
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

        # Handle sleep prevention for different platforms
        import platform
        system = platform.system().lower()
        if system == 'windows':
            try:
                result = subprocess.run(['where', 'powershell'], capture_output=True, text=True)
                if result.returncode == 0:
                    ffmpeg_args = ' '.join([f'"{arg}"' if ' ' in arg or '"' in arg else arg for arg in cmd])
                    powershell_script = f'''$code = @"using System;using System.Runtime.InteropServices;public class Power {{[DllImport(\"kernel32.dll\")]public static extern uint SetThreadExecutionState(uint esFlags);public const uint ES_CONTINUOUS = 0x80000000;public const uint ES_SYSTEM_REQUIRED = 0x00000001;public const uint ES_DISPLAY_REQUIRED = 0x00000002;}}"@;Add-Type -TypeDefinition $code;[Power]::SetThreadExecutionState([Power]::ES_CONTINUOUS -bor [Power]::ES_SYSTEM_REQUIRED -bor [Power]::ES_DISPLAY_REQUIRED);try {{ & ffmpeg.exe {ffmpeg_args} }} finally {{ [Power]::SetThreadExecutionState([Power]::ES_CONTINUOUS); }}'''
                    cmd = ['powershell', '-ExecutionPolicy', 'Bypass', '-Command', powershell_script]
            except Exception:
                logger.debug("Error checking for PowerShell, continuing without special sleep prevention")
        else:
            sleep_prevention_cmd = get_sleep_prevention_command()
            if sleep_prevention_cmd:
                cmd = sleep_prevention_cmd + cmd

        # Initialize progress tracker for M4B conversion (optional)
        try:
            from audiobook_p.progress import ProgressTracker
            try:
                total_duration = int(max(1, current_time / 1000.0))
            except Exception:
                total_duration = 1
            progress = ProgressTracker(total_duration, "Converting to M4B")
            progress.update(0, "Starting conversion...")
        except Exception:
            progress = None
            logger.info("Converting to M4B...")

        # Run ffmpeg and monitor progress
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=1, universal_newlines=True)
        import re
        time_re = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
        try:
            total_secs = float(max(1.0, current_time / 1000.0))
        except Exception:
            total_secs = 1.0

        if proc.stderr is not None:
            for raw_line in proc.stderr:
                line = raw_line.strip()
                m = time_re.search(line)
                if m and progress:
                    hh = int(m.group(1)); mm = int(m.group(2)); ss = float(m.group(3))
                    elapsed = hh * 3600 + mm * 60 + ss
                    cur = int(min(elapsed, total_secs))
                    progress.set_progress(cur, "Converting: {}s/{:.0f}s".format(int(elapsed), total_secs))

        retcode = proc.wait()
        if retcode != 0:
            try:
                out = proc.communicate(timeout=2)
            except Exception:
                pass
            raise Exception("ffmpeg failed with exit code {}".format(retcode))

        if progress:
            progress.finish("M4B conversion complete")
        else:
            logger.info("M4B conversion complete")

        # Verify output exists
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise Exception("Output file was not created or is empty")

        # Try to add chapters with mutagen
        if chapters_info:
            try:
                from mutagen.mp4 import MP4, MP4Chapters, Chapter
                audio = MP4(str(output_path))
                chapter_objects = []
                for chapter in chapters_info:
                    chapter_obj = Chapter(start=chapter['start'], title=chapter['title'])
                    chapter_objects.append(chapter_obj)
                mp4_chapters = MP4Chapters(); mp4_chapters._chapters = chapter_objects
                audio.chapters = mp4_chapters
                audio.save()
                logger.info("Chapters added to M4B file")
            except Exception as e:
                logger.warning("Failed to add chapters to M4B: %s", e)

        # Attempt to locate original source files for cover art, then add metadata
        original_audio_files = None
        try:
            if original_source_path and os.path.exists(original_source_path):
                original_files = []
                for ext in ['*.m4a', '*.mp3']:
                    original_files.extend(glob.glob(os.path.join(original_source_path, ext)))
                if original_files:
                    original_files.sort(key=natural_sort_key)
                    original_audio_files = original_files
                    logger.info("Found %d original source files from explicit path", len(original_files))
            elif "audiobook_copy_" in folder_path:
                folder_dir = os.path.dirname(folder_path)
                folder_name = os.path.basename(folder_path)
                for item in os.listdir(folder_dir):
                    item_path = os.path.join(folder_dir, item)
                    if os.path.isdir(item_path) and item != folder_name:
                        test_files = []
                        for ext in ['*.m4a', '*.mp3']:
                            test_files.extend(glob.glob(os.path.join(item_path, ext)))
                        if test_files:
                            original_files = []
                            for temp_file in audio_files:
                                temp_stem = os.path.splitext(os.path.basename(temp_file))[0]
                                for test_file in test_files:
                                    test_stem = os.path.splitext(os.path.basename(test_file))[0]
                                    if temp_stem == test_stem:
                                        original_files.append(test_file); break
                            if len(original_files) > 0:
                                original_audio_files = original_files
                                logger.info("Found %d original source files for cover art", len(original_files))
                                break
        except Exception as e:
            logger.warning("Failed to find original source files: %s", e)

        # Add audiobook metadata to the output file (copy tags, cover art, series)
        add_audiobook_metadata(str(output_path), audio_files, original_audio_files, series_name=series_name, chapters_info=chapters_info, chapter_titles=chapter_titles, author_fix=author_fix, cli_author=cli_author, album_names=album_names)

        return str(output_path)
    finally:
        # Clean up temporary files
        try:
            if os.path.exists(file_list_path):
                os.remove(file_list_path)
        except Exception as e:
            logger.debug("Failed to remove file_list_path %s: %s", file_list_path, e)
        try:
            if os.path.exists(metadata_path):
                os.remove(metadata_path)
        except Exception as e:
            logger.debug("Failed to remove metadata_path %s: %s", metadata_path, e)

        # Remove explicit temp_copy_path when safe
        try:
            if temp_copy_path:
                try:
                    temp_root = os.path.abspath(tempfile.gettempdir())
                except Exception:
                    temp_root = None
                try:
                    remove_ok = False
                    if os.path.exists(temp_copy_path):
                        if temp_root and os.path.commonpath([os.path.abspath(temp_copy_path), temp_root]) == temp_root:
                            remove_ok = True
                        base = os.path.basename(temp_copy_path)
                        if base.startswith('temp-') or base.startswith('audiobook_copy_'):
                            remove_ok = True
                    if remove_ok and os.path.exists(temp_copy_path):
                        try:
                            shutil.rmtree(temp_copy_path)
                            logger.debug("Removed explicit temp_copy_path %s", temp_copy_path)
                        except Exception as e:
                            logger.debug("Failed to remove explicit temp_copy_path %s: %s", temp_copy_path, e)
                except Exception:
                    pass

            # Fallback heuristic: remove folder_path when it's under system temp dir
            if not temp_copy_path or not (os.path.exists(temp_copy_path) and base.startswith(('temp-', 'audiobook_copy_'))):
                try:
                    try:
                        temp_root = os.path.abspath(tempfile.gettempdir())
                    except Exception:
                        temp_root = None
                    try:
                        folder_abspath = os.path.abspath(folder_path)
                    except Exception:
                        folder_abspath = None
                    if folder_abspath and temp_root and folder_abspath.startswith(temp_root + os.sep):
                        base2 = os.path.basename(folder_abspath)
                        if base2.startswith('audiobook_copy_') or base2.startswith('temp-'):
                            try:
                                shutil.rmtree(folder_abspath, ignore_errors=True)
                                logger.debug("Removed temporary folder %s", folder_abspath)
                            except Exception as e:
                                logger.debug("Failed to remove temporary folder %s: %s", folder_abspath, e)
                except Exception:
                    pass
        except Exception:
            pass


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


def ffmpeg_inject_chapters(m4b_path, chapters, timebase=1000):
    """Create an ffmetadata file and remux it into m4b_path using ffmpeg.

    chapters: iterable of dicts with keys 'start_ms', 'end_ms', 'title'.
    Returns a dict: {'status': 'ok'|'no_ffmpeg'|'error', 'note': str}
    """
    import shutil
    import tempfile
    import subprocess
    import os

    ffmpeg_path = shutil.which('ffmpeg')
    if not ffmpeg_path:
        return {'status': 'no_ffmpeg', 'note': 'ffmpeg not found on PATH'}

    meta_fd, meta_path = tempfile.mkstemp(prefix='ffmeta_', suffix='.txt')
    try:
        with os.fdopen(meta_fd, 'w', encoding='utf-8') as mfd:
            mfd.write(';FFMETADATA1\n')
            for ch in chapters:
                s_ms = ch.get('start_ms') if ch.get('start_ms') is not None else 0
                e_ms = ch.get('end_ms') if ch.get('end_ms') is not None else (s_ms + 1000)
                try:
                    s_ms = int(round(float(s_ms)))
                except Exception:
                    s_ms = 0
                try:
                    e_ms = int(round(float(e_ms)))
                except Exception:
                    e_ms = s_ms + 1000

                mfd.write('[CHAPTER]\n')
                mfd.write('TIMEBASE=1/1000\n')
                mfd.write(f'START={s_ms}\n')
                mfd.write(f'END={e_ms}\n')
                title_safe = (ch.get('title') or '').replace('\n', ' ')
                mfd.write(f'title={title_safe}\n')

        tmp_out = m4b_path + '.tmp.m4b'
        cmd = [ffmpeg_path, '-y', '-i', m4b_path, '-i', meta_path, '-map_metadata', '1', '-c', 'copy', tmp_out]
        subprocess.run(cmd, check=True, capture_output=True)
        os.replace(tmp_out, m4b_path)
        return {'status': 'ok', 'note': 'created chapters (ffmpeg)'}
    except Exception as e:
        return {'status': 'error', 'note': f'ffmpeg chapter injection failed: {e}'}
    finally:
        try:
            if os.path.exists(meta_path):
                os.remove(meta_path)
        except Exception:
            pass


def add_audiobook_metadata(m4b_path, source_files, original_source_files=None, series_name=None, mp4_class=None, mutagen_file_func=None, chapters_info=None, chapter_titles=False, author_fix=False, cli_author=None, album_names=False):
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
            # Detect whether source files include an explicit grouping/series
            grouping_in_source = False
            try:
                if first_audio and hasattr(first_audio, 'tags') and first_audio.tags:
                    if '\u00a9grp' in first_audio.tags or '\xa9grp' in first_audio.tags or '----:com.apple.iTunes:SERIES' in first_audio.tags:
                        grouping_in_source = True
                    else:
                        # Check for ID3 TIT1 as grouping on MP3 sources
                        try:
                            for ak in list(first_audio.tags.keys()):
                                if isinstance(ak, str) and ak.upper().startswith('TIT1'):
                                    grouping_in_source = True
                                    break
                        except Exception:
                            pass
            except Exception:
                grouping_in_source = False
            # Best-effort introspection of the first source file to help
            # diagnose missing tag copy issues in integration tests.
            try:
                logger.debug("add_audiobook_metadata: first_file=%s, cli_author=%r, author_fix=%r", first_file, cli_author, author_fix)
                if first_audio and hasattr(first_audio, 'tags') and first_audio.tags:
                    try:
                        logger.debug("first_audio.tags.keys() = %s", list(first_audio.tags.keys()))
                    except Exception:
                        logger.debug("first_audio.tags present but failed to list keys", exc_info=True)
                else:
                    logger.debug("first_audio has no tags or could not be loaded")
            except Exception:
                logger.debug("add_audiobook_metadata: failed to inspect first_audio", exc_info=True)

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

                            # Respect CLI author_fix: if requested, normalize artist-like fields
                            try:
                                if author_fix and desc_key in ('artist', 'album_artist', 'composer'):
                                    source_value = _maybe_fix_author(source_value, True)
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
                                    logger.debug("set %s = %r (from source %s)", write_key, formatted_value, first_file)
                            except Exception:
                                pass
                            # If we just wrote a track/disc tuple, mark it so later
                            # default logic doesn't overwrite the explicitly set value.
                            try:
                                if write_key in ('trkn', 'disk') or (isinstance(decoded_mp4_key, str) and decoded_mp4_key in ('trkn', 'disk')):
                                    track_written = True
                                    try:
                                        logger.debug("track_written set True after writing %s", write_key)
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
            # Final safety: ensure artist/author is present on the final M4B.
            # Some source->destination copy paths may miss ©ART; explicitly
            # copy a sensible author-like value from the first source file or
            # from the CLI-provided author if available.
            try:
                src_val = None
                if first_audio and hasattr(first_audio, 'tags') and first_audio.tags:
                    # Prefer decoded MP4 atom name (\xa9ART -> '©ART')
                    try:
                        decoded_key = '\\xa9ART'.encode('ascii').decode('unicode_escape')
                    except Exception:
                        decoded_key = '\u00A9ART'

                    for candidate in (decoded_key, '©ART', 'aART'):
                        try:
                            if candidate in first_audio.tags:
                                raw = first_audio.tags[candidate]
                                src_val = raw[0] if isinstance(raw, list) and raw else raw
                                break
                        except Exception:
                            continue

                    # Fallback: look for ID3 TPE1 frames (artist)
                    if not src_val:
                        try:
                            for ak in first_audio.tags.keys():
                                try:
                                    if isinstance(ak, str) and ak.upper().startswith('TPE1'):
                                        raw = first_audio.tags[ak]
                                        src_val = raw[0] if isinstance(raw, list) and raw else raw
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                # If still not found, but the CLI provided an explicit author, use it
                if not src_val and cli_author:
                    try:
                        src_val = cli_author
                    except Exception:
                        src_val = None

                # If we now have a source value, write it to common artist atoms
                if src_val:
                    try:
                        if author_fix:
                            try:
                                src_val = _maybe_fix_author(src_val, True)
                            except Exception:
                                pass

                        try:
                            formatted = reformat_tag_for_file_type('artist', src_val, 'mp4')
                        except Exception:
                            formatted = [str(src_val)]

                        # Write to decoded ©ART and aART when possible
                        try:
                            audio.tags[decoded_key] = formatted
                        except Exception:
                            try:
                                audio.tags['\u00A9ART'] = formatted
                            except Exception:
                                pass
                        try:
                            audio.tags['aART'] = formatted
                        except Exception:
                            pass

                        try:
                            audio.save()
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

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

        # If we have a series name (either from CLI or copied grouping), prefer
        # to write explicit series-related atoms: album (cleaned folder name),
        # album_sort ("Series - Album"), soal (series), and sonm (title_sort)
        try:
            series_value = None
            # Prefer explicit CLI-provided series_name
            if series_name:
                try:
                    series_value = sanitize_series_name(series_name)
                except Exception:
                    series_value = series_name

            # Fall back to copied grouping atom if present
            if not series_value:
                try:
                    grp = audio.tags.get('\xa9grp')
                    if grp:
                        series_value = grp[0] if isinstance(grp, list) else grp
                except Exception:
                    series_value = None

            # Fall back to freeform SERIES atom
            if not series_value:
                try:
                    ff = audio.tags.get('----:com.apple.iTunes:SERIES')
                    if ff and len(ff) > 0:
                        v = ff[0]
                        # MP4FreeForm or raw bytes: try decode
                        try:
                            if isinstance(v, bytes):
                                series_value = v.decode('utf-8')
                            else:
                                # Some MP4FreeForm expose .value or str()
                                series_value = str(v)
                        except Exception:
                            series_value = str(v)
                except Exception:
                    pass

            # Final fallback: try to infer series name from folder structure of
            # the provided source files (grandparent folder for series child).
            # Use sanitize_series_name to normalize hyphens and spacing into a
            # natural series representation (e.g., 'Night-Lords' -> 'Night Lords').
            if not series_value:
                try:
                    # Prefer original source files (pre-mutate) when available
                    lookup_files = original_source_files if original_source_files and len(original_source_files) > 0 else source_files
                    if lookup_files and len(lookup_files) > 0:
                        first_guess = lookup_files[0]
                        gp = os.path.basename(os.path.dirname(os.path.dirname(first_guess)))
                        if gp:
                            sv = sanitize_series_name(gp)
                            if sv:
                                series_value = sv
                                # Mark that this series value was inferred from folder structure
                                series_inferred_from_structure = True
                except Exception:
                    pass

            # Determine cleaned_album from original source files.
            # If the folder name looks like a temporary copy (e.g. 'temp-...','Temp-...','audiobook_copy_...'),
            # strip that prefix before cleaning so album_sort/©alb do not contain temp prefixes.
            cleaned_album = None
            # Default flag for whether series_value was inferred from structure
            try:
                series_inferred_from_structure
            except NameError:
                series_inferred_from_structure = False
            if original_source_files or (source_files and len(source_files) > 0):
                try:
                    first_src = original_source_files[0] if original_source_files and len(original_source_files) > 0 else source_files[0]
                    album_folder = os.path.basename(os.path.dirname(first_src))
                    # Remove common temp-copy prefixes used by copy_folder and mkdtemp heuristics
                    try:
                        import re
                        album_folder = re.sub(r'^(?:temp[-_]?|Temp[-_]?|audiobook_copy[_-]?)[\w\d\-]*\s*', '', album_folder, flags=re.IGNORECASE)
                    except Exception:
                        pass
                    cleaned_album = clean_album_name(album_folder)
                    # Strip suffix (keep primary part before any ' - ' separators)
                    try:
                        primary_album = cleaned_album.split(' - ')[0].strip()
                        if primary_album:
                            cleaned_album = primary_album
                    except Exception:
                        pass
                except Exception:
                    pass

            # If we have a cleaned album folder name, ensure the ©alb atom exists
            # on the final M4B. Respect the album_names flag (which forces overwrite)
            # but otherwise only set if not already present.
            try:
                if cleaned_album:
                    try:
                        existing = audio.tags.get('\xa9alb') or audio.tags.get('\u00A9alb') or audio.tags.get('©alb')
                    except Exception:
                        existing = None

                    if album_names or not existing:
                        try:
                            audio.tags['\xa9alb'] = [cleaned_album]
                            try:
                                audio.save()
                            except Exception:
                                pass
                        except Exception:
                            try:
                                audio.tags['\u00A9alb'] = [cleaned_album]
                            except Exception:
                                pass
            except Exception:
                pass

            # If we found a series value, set album and sorting atoms accordingly
            if (series_name or series_value) and (original_source_files or (source_files and len(source_files) > 0)):
                try:
                    # Set album to cleaned album folder name (child folder)
                    # If caller requested explicit album names, force the album to cleaned folder name
                    if album_names and cleaned_album:
                        audio.tags['\xa9alb'] = [cleaned_album]
                    else:
                        audio.tags['\xa9alb'] = [cleaned_album]

                    # Set freeform series to the series value (leave sonm alone)
                    try:
                        from mutagen.mp4 import MP4FreeForm
                        audio.tags['----:com.apple.iTunes:SERIES'] = [MP4FreeForm(str(series_value).encode('utf-8'))]
                    except Exception:
                        try:
                            audio.tags['----:com.apple.iTunes:SERIES'] = [str(series_value).encode('utf-8')]
                        except Exception:
                            pass

                    # Persist these changes early
                    try:
                        audio.save()
                    except Exception:
                        pass
                except Exception:
                    pass

            # If caller explicitly requested album_names, force the ©alb atom to the cleaned folder name
            try:
                if album_names and cleaned_album:
                    audio.tags['\xa9alb'] = [cleaned_album]
                    try:
                        audio.save()
                    except Exception:
                        pass
            except Exception:
                pass

            # Set album_sort (soal) to the cleaned album name.
            # If a series was provided explicitly (via CLI or present in source tags),
            # include it as a prefix. If the series value was merely inferred from
            # folder structure and there was no explicit grouping in the source and
            # no CLI-provided series_name, prefer to omit the prefix (treat as novel).
            try:
                if cleaned_album:
                    try:
                        use_series_prefix = False
                        if series_value:
                            # Prefer prefix when the series value is explicit or when the user supplied it
                            if series_name:
                                use_series_prefix = True
                            elif grouping_in_source:
                                use_series_prefix = True
                            elif not series_inferred_from_structure:
                                # Series was discovered by tags/freeform earlier
                                use_series_prefix = True
                            else:
                                # Series was inferred from folder structure only; omit prefix for novels
                                use_series_prefix = False

                        if series_value and use_series_prefix:
                            audio.tags['soal'] = [f"{series_value} - {cleaned_album}"]
                        else:
                            audio.tags['soal'] = [cleaned_album]
                    except Exception:
                        audio.tags['soal'] = [cleaned_album]
                try:
                    audio.save()
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

                        # Final adjustments: when --chapter-titles was used, set the main title atom
                        # (©nam / '\xa9nam') to the cleaned first chapter title so the M4B main
                        # title reflects the chapter naming mode. Also, when --author-fix was
                        # requested, normalize any artist-like atoms to First Last form and persist
                        # them explicitly. Finally, ensure START/END chapter boundaries are
                        # persisted in the container by invoking ffmpeg remux of ffmetadata if
                        # chapters_info was provided (this guarantees both START and END are stored).
                        try:
                            try:
                                audio = MP4(m4b_path)
                                if audio.tags is None:
                                    audio.tags = MP4Tags()
                            except Exception:
                                audio = None

                            modified = False
                            # Set ©nam from first chapter when chapter_titles mode was active
                            try:
                                if chapter_titles and chapters_info and len(chapters_info) > 0:
                                    # Prefer an explicit book_name attached to chapters_info
                                    first_ch = chapters_info[0]
                                    book_name = first_ch.get('book_name') or ''
                                    # Build ©nam as "BookName - Chapter 1" when possible
                                    try:
                                        if book_name:
                                            cleaned_book = book_title_logic(book_name).strip()
                                            cleaned_first = f"{cleaned_book} - Chapter 1"
                                        else:
                                            # Fall back to old behavior: use cleaned first chapter title
                                            first_title = first_ch.get('title') or ''
                                            cleaned_first = book_title_logic(first_title).strip() if first_title else first_title
                                    except Exception:
                                        cleaned_first = str(first_ch.get('title', '')).strip()

                                    if audio is not None and cleaned_first:
                                        audio.tags['\xa9nam'] = [cleaned_first]
                                        modified = True
                            except Exception:
                                pass

                            # Normalize artist/album-artist/composer if author_fix requested
                            try:
                                if author_fix and audio is not None:
                                    for art_key in ('\xa9ART', 'aART', 'composer'):
                                        try:
                                            if art_key in audio.tags and audio.tags.get(art_key):
                                                val = audio.tags[art_key]
                                                if isinstance(val, list) and len(val) > 0:
                                                    fixed = _maybe_fix_author(val[0], True)
                                                    audio.tags[art_key] = [fixed]
                                                    modified = True
                                        except Exception:
                                            continue
                            except Exception:
                                pass

                            if modified and audio is not None:
                                try:
                                    audio.save()
                                except Exception:
                                    pass

                            # Ensure START/END chapter boundaries are persisted by remuxing ffmetadata
                            try:
                                if chapters_info and len(chapters_info) > 0:
                                    # Build ffmetadata-friendly list of dicts with start_ms/end_ms/title
                                    ff_chs = []
                                    for ch in chapters_info:
                                        try:
                                            s_ms = ch.get('start_ms') if ch.get('start_ms') is not None else int(round(float(ch.get('start', 0)) * 1000))
                                        except Exception:
                                            s_ms = 0
                                        try:
                                            e_ms = ch.get('end_ms') if ch.get('end_ms') is not None else int(round(float(ch.get('end', (ch.get('start', 0) or 0) + 1)) * 1000))
                                        except Exception:
                                            e_ms = int(s_ms + 1000)
                                        ff_chs.append({'start_ms': int(s_ms), 'end_ms': int(e_ms), 'title': ch.get('title') or ''})

                                    # Attempt ffmpeg injection; ignore failure (we still keep mutagen tags)
                                    try:
                                        res = ffmpeg_inject_chapters(m4b_path, ff_chs)
                                        # If ffmpeg succeeded, re-apply mutagen chapters (start/title)
                                        if res.get('status') == 'ok':
                                            try:
                                                add_chapters_to_m4b(m4b_path, chapters_info)
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        except Exception:
                            pass
                        logger.info("Copied original trkn from %s to %s", first_src, m4b_path)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # Final safety: ensure sonm (title_sort) equals the uncleaned filename stem
    try:
        if original_source_files and len(original_source_files) > 0:
            first_src = original_source_files[0]
        elif source_files and len(source_files) > 0:
            first_src = source_files[0]
        else:
            first_src = None

        if first_src:
            file_stem = os.path.splitext(os.path.basename(first_src))[0]
            try:
                audio = MP4(m4b_path)
                if audio.tags is None:
                    audio.tags = MP4Tags()
                # Always set/override sonm to ensure deterministic title_sort
                audio.tags['sonm'] = [str(file_stem)]
                try:
                    logger.debug("Setting final sonm=%r on %s", audio.tags.get('sonm'), m4b_path)
                except Exception:
                    pass
                audio.save()
            except Exception:
                pass
    except Exception:
        pass

    # Aggressive normalization pass: if author_fix requested, scan all MP4
    # tag keys that look like artist/author fields and convert any value that
    # appears to be in 'Last, First' form (contains a comma) to 'First Last'.
    try:
        if author_fix:
            from mutagen.mp4 import MP4, MP4Tags, MP4FreeForm
            audio = MP4(m4b_path)
            if audio.tags is None:
                audio.tags = MP4Tags()
            # Explicitly normalize the common MP4 author-like keys to avoid
            # missing targets due to atom naming edge cases.
            explicit_keys = ['\xa9ART', 'aART', '\xa9wrt']
            modified = False
            for k in explicit_keys:
                try:
                    if k in audio.tags and audio.tags.get(k):
                        v = audio.tags.get(k)
                        candidate = v[0] if isinstance(v, list) and len(v) > 0 else v
                        # Unwrap MP4FreeForm/bytes if present
                        # Unwrap various container types into a plain string
                        try:
                            # MP4FreeForm and similar may expose .value or .data
                            if hasattr(candidate, 'value'):
                                candidate = candidate.value
                        except Exception:
                            pass
                        try:
                            if hasattr(candidate, 'data'):
                                candidate = candidate.data
                        except Exception:
                            pass

                        # Decode bytes to string
                        if isinstance(candidate, (bytes, bytearray)):
                            try:
                                candidate = candidate.decode('utf-8')
                            except Exception:
                                try:
                                    candidate = candidate.decode('latin-1', errors='ignore')
                                except Exception:
                                    candidate = str(candidate)

                        # If it's a list (nested), pick first element and repeat decode
                        if isinstance(candidate, list) and len(candidate) > 0:
                            candidate = candidate[0]

                        # Final string coercion
                        try:
                            cand_str = str(candidate).strip()
                        except Exception:
                            cand_str = None

                        if isinstance(cand_str, str) and ',' in cand_str:
                            fixed = _maybe_fix_author(cand_str, True)
                            if fixed and fixed != cand_str:
                                try:
                                    audio.tags[k] = [fixed]
                                    modified = True
                                except Exception:
                                    try:
                                        audio.tags[k] = [fixed.encode('utf-8')]
                                        modified = True
                                    except Exception:
                                        pass
                except Exception:
                    continue

            if modified:
                try:
                    audio.save()
                    logger.info('Applied explicit author_fix normalization to %s', m4b_path)
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

    # Ensure ©nam (main title) reflects the cleaned first chapter title when
    # chapter_titles mode was active. Do this unconditionally if chapters_info
    # was provided so the final M4B has the main title atom set for players.
    try:
        if chapter_titles and chapters_info and len(chapters_info) > 0:
            first_ch = chapters_info[0]
            book_name = first_ch.get('book_name') or ''
            try:
                if book_name:
                    cleaned_book = book_title_logic(book_name).strip()
                    cleaned_first = f"{cleaned_book} - Chapter 1"
                else:
                    first_title = first_ch.get('title') or ''
                    cleaned_first = book_title_logic(first_title).strip() if first_title else first_title
            except Exception:
                cleaned_first = str(first_ch.get('title', '')).strip()

            if cleaned_first:
                try:
                    from mutagen.mp4 import MP4, MP4Tags
                    audio = MP4(m4b_path)
                    if audio.tags is None:
                        audio.tags = MP4Tags()
                    audio.tags['\xa9nam'] = [cleaned_first]
                    audio.save()
                    logger.info("Set ©nam from first chapter title: %s", cleaned_first)
                except Exception:
                    pass
    except Exception:
        pass

    # As a final safety-net, ensure author-like atoms are normalized when
    # author_fix was requested. Do this unconditionally here to catch any
    # earlier code-paths that may have missed normalization.
    try:
        if author_fix:
            from mutagen.mp4 import MP4, MP4Tags
            audio = MP4(m4b_path)
            if audio.tags is None:
                audio.tags = MP4Tags()

            modified = False
            for art_key in ('\xa9ART', 'aART', '\xa9wrt'):
                try:
                    if art_key in audio.tags and audio.tags.get(art_key):
                        val = audio.tags[art_key]
                        if isinstance(val, list) and len(val) > 0:
                            fixed = _maybe_fix_author(val[0], True)
                            # Only write if changed
                            if fixed and fixed != val[0]:
                                audio.tags[art_key] = [fixed]
                                modified = True
                except Exception:
                    continue

            if modified:
                try:
                    audio.save()
                    logger.info("Applied final author_fix normalization to %s", m4b_path)
                except Exception:
                    pass
    except Exception:
        pass

    # Definitive final normalization: run one more pass after everything
    # above to ensure no later write reintroduced 'Last, First' values.
    try:
        if author_fix:
            from mutagen.mp4 import MP4, MP4Tags
            audio = MP4(m4b_path)
            if audio.tags is None:
                audio.tags = MP4Tags()

            modified = False
            # Iterate over all possible artist-like keys and normalize any value that
            # appears to be in 'Last, First' form (contains a comma).
            for art_key in list(audio.tags.keys()):
                try:
                    if art_key in ('\xa9ART', 'aART', '\xa9wrt') or art_key.lower().endswith('art'):
                        raw = audio.tags.get(art_key)
                        if not raw:
                            continue
                        # Use _maybe_fix_author which handles all unwrapping internally
                        fixed = _maybe_fix_author(raw, True)
                        print(f'Definitive normalization for {m4b_path}: art_key={art_key!r}, raw={raw!r}, fixed={fixed!r}')
                        if fixed and fixed != raw:
                            audio.tags[art_key] = [fixed]
                            modified = True
                except Exception:
                    continue

            print(f'Definitive normalization for {m4b_path}: modified={modified!r}')
            if modified:
                try:
                    audio.save()
                    logger.info('Applied definitive final normalization to %s', m4b_path)
                except Exception:
                    logger.debug('Failed to save definitive normalization for %s', m4b_path, exc_info=True)
    except Exception:
        pass


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
                logger.error("Dependency check failed: %s", e)
            else:
                logger.warning("Dependency check failed: %s", e)
        
        # Validate source path
        if not os.path.isdir(source_path):
            error_msg = "Error: Source must be a directory: {}".format(source_path)
            # Always log via module logger to ensure output is captured
            logging.getLogger(__name__).error(error_msg)
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
                logger.error(error_msg)
            return

        # If output_path is a directory, generate filename from original source folder name
        if os.path.isdir(output_path):
            # Prefer the original source folder name when available (mutate-convert passes it as original_source_path)
            src_for_name = original_source_path if original_source_path else source_path
            source_folder_name = os.path.basename(src_for_name.rstrip('/\\'))

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
            logging.getLogger(__name__).error(error_msg)
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
            # Pass the folder being converted as temp_copy_path so cleanup can remove
            # the exact folder we created during mutate/convert flows.
            return convert_folder_to_m4b(str(source_path), str(final_output_path), config, args.sort_by, original_source_path, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), temp_copy_path=str(source_path), author_fix=getattr(args, 'author_fix', False), cli_author=getattr(args, 'author_name', None), album_names=getattr(args, 'album_names', False))
        
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
                series_name=getattr(args, 'series_name', None),
                temp_copy_path=str(source_path),
                author_fix=getattr(args, 'author_fix', False),
                cli_author=getattr(args, 'author_name', None),
                album_names=getattr(args, 'album_names', False)
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
        
        logger.info(json.dumps(result, indent=2))

    except Exception as e:
        error_msg = "Error: {}".format(e)
        logging.getLogger(__name__).error(error_msg)


def cmd_extract(args):
    """Extract metadata from audio files"""
    source_path = args.source

    try:
        if os.path.isfile(source_path):
            # Process single file
            if os.path.splitext(source_path)[1].lower() not in ['.m4a', '.mp3', '.m4b']:
                logging.getLogger(__name__).error("File is not an audio file: {}".format(source_path))
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
            logger.info(json.dumps(result, indent=2))

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
                # Log JSON output instead of printing to stdout
                logging.getLogger(__name__).info(json.dumps(results, indent=2))
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

                            logger.info(json.dumps(all_results, indent=2))
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
                                logger.info(json.dumps(all_results, indent=2))
                                return
                    except Exception:
                        pass

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        logger.error("Error: %s", e)


def cmd_change(args):
    """Change metadata on one or more audio files or a folder of audio files.

    Supports mp3, m4a, and m4b files. If a folder is provided, all audio files
    in the folder will be updated. For folders, use --chapter-title to supply
    a list of titles that will be mapped to files in natural filename order.
    """
    path = args.path

    # Validate input path
    if not os.path.exists(path):
        logger.error("Error: Path does not exist: %s", path)
        return

    # Determine list of files to operate on
    def _is_audio(p):
        ext = os.path.splitext(p)[1].lower()
        return ext in ('.mp3', '.m4a', '.m4b')

    targets = []
    if os.path.isdir(path):
        # collect audio files in directory
        for ext in ['*.m4a', '*.mp3', '*.m4b']:
            targets.extend(glob.glob(os.path.join(path, ext)))
        targets = sorted(set(targets), key=natural_sort_key)
        if not targets:
            logger.error("Error: No audio files found in folder: %s", path)
            return
    else:
        # Single file provided
        if not _is_audio(path):
            logger.error("Error: Unsupported file type: %s", path)
            return
        targets = [path]

    # Read chapter titles file if provided
    def _read_chapter_file(path):
        """Read chapter definitions from a file.

        Supported formats:
        - JSON array of strings: ["Title1", "Title2"]
        - JSON array of objects: [{"start":"00:00:00","end":"00:05:00","title":"Chapter 1"}, ...]
        - ffmetadata file (starts with ;FFMETADATA1) with [CHAPTER] sections
        - Plain text: one title per line
        Returns list of items: either strings (titles) or dicts with keys start_ms,end_ms,title
        """
        import json
        if not os.path.exists(path):
            raise ValueError(f"Chapter titles file not found: {path}")

        text = None
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()

        # Try JSON first
        try:
            obj = json.loads(text)
            results = []
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str):
                        results.append(item)
                    elif isinstance(item, dict):
                        # normalize start/end if present; accept strings
                        d = dict(item)
                        results.append(d)
                return results
        except Exception:
            pass

        # ffmetadata detection
        if text.startswith(';FFMETADATA1'):
            # crude parser: split by [CHAPTER] sections
            res = []
            parts = text.split('[CHAPTER]')
            for part in parts[1:]:
                lines = [l.strip() for l in part.splitlines() if l.strip()]
                data = {}
                for ln in lines:
                    if '=' in ln:
                        k, v = ln.split('=', 1)
                        data[k.strip().lower()] = v.strip()
                # expect TIMEBASE, START, END, title
                start = data.get('start')
                end = data.get('end')
                title = data.get('title')
                try:
                    start_ms = int(start) if start is not None else None
                except Exception:
                    start_ms = None
                try:
                    end_ms = int(end) if end is not None else None
                except Exception:
                    end_ms = None
                res.append({'start_ms': start_ms, 'end_ms': end_ms, 'title': title})
            return res

        # Plain text fallback
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return lines

    chap_titles = None
    chap_file = getattr(args, 'chapter_titles_file', None)
    # Backwards compatibility: accept legacy args.chapter_titles set by tests or callers
    if not chap_file and hasattr(args, 'chapter_titles'):
        chap_titles = getattr(args, 'chapter_titles')
    if chap_file:
        try:
            chap_titles = _read_chapter_file(chap_file)
        except Exception as e:
            logger.error("Error reading chapter titles file: %s", e)
            return
    if chap_titles:
        # If operating on a folder, require one title per file.
        if os.path.isdir(path):
            if len(targets) != len(chap_titles):
                logger.error("Error: --chapter-titles-file provided %d titles but %d files found", len(chap_titles), len(targets))
                return

    # Normalize common shorthand chapter inputs like 'ch1', 'ch 1', 'chapter1' -> 'Chapter 1'
    def _normalize_chapter_title(s):
        if not s:
            return s
        try:
            st = str(s).strip()
        except Exception:
            return s

        import re
        # Match forms like: ch1, ch 1, chapter1, ch1 slowly
        m = re.match(r'^(?:ch|c|chapter)\s*[-\.:]?\s*(\d+)(?:\s+(.+))?$', st, re.IGNORECASE)
        if m:
            try:
                n = int(m.group(1))
                suffix = m.group(2)
                if suffix:
                    try:
                        suffix_clean = book_title_logic(suffix.strip())
                    except Exception:
                        suffix_clean = suffix.strip()
                    return f"Chapter {n} {suffix_clean}"
                return f"Chapter {n}"
            except Exception:
                pass

        # If it's like '1' or '#1' or '1 something', convert to 'Chapter 1 [suffix]'
        m2 = re.match(r'^[#]?(\d+)(?:\s+(.+))?$', st)
        if m2:
            try:
                n = int(m2.group(1))
                suffix = m2.group(2)
                if suffix:
                    try:
                        suffix_clean = book_title_logic(suffix.strip())
                    except Exception:
                        suffix_clean = suffix.strip()
                    return f"Chapter {n} {suffix_clean}"
                return f"Chapter {n}"
            except Exception:
                pass

        # If it already seems like 'Chapter X ...', return cleaned title
        if st.lower().startswith('chapter'):
            try:
                return book_title_logic(st)
            except Exception:
                return st

        # Fallback to book_title_logic for other normalization
        try:
            return book_title_logic(st)
        except Exception:
            return st

    # Flatten chap_titles (nargs may produce a list) and normalize shorthand like 'ch1'
    if chap_titles:
        # If user passed multiple --chapter-titles flags previously, chap_titles could be nested
        if any(isinstance(x, (list, tuple)) for x in chap_titles):
            flat = []
            for item in chap_titles:
                if isinstance(item, (list, tuple)):
                    flat.extend(item)
                else:
                    flat.append(item)
            chap_titles = flat

        # Normalize string entries immediately (e.g., ch1 -> Chapter 1).
        # Also attempt to parse timed-spec strings (e.g. "00:00:00-00:05:00:Title")
        # into dicts with start_ms/end_ms/title using the chapters parser.
        try:
            from audiobook_p.chapters import parse_chapter_spec
        except Exception:
            parse_chapter_spec = None

        normed = []
        for x in chap_titles:
            # If it's a dict, normalize its title if present and keep as-is;
            # later code will handle 'start'/'start_ms' keys.
            if isinstance(x, dict):
                d = dict(x)
                if 'title' in d and isinstance(d['title'], str):
                    d['title'] = _normalize_chapter_title(d['title'])
                normed.append(d)
                continue

            # Strings: try to parse timed spec if parser available
            if isinstance(x, str) and parse_chapter_spec:
                try:
                    parsed = parse_chapter_spec(x)
                except Exception:
                    parsed = None
                if parsed and (parsed.get('start_s') is not None or parsed.get('end_s') is not None):
                    # Convert seconds to milliseconds and normalize title
                    start_ms = None if parsed.get('start_s') is None else int(round(parsed.get('start_s') * 1000))
                    end_ms = None if parsed.get('end_s') is None else int(round(parsed.get('end_s') * 1000))
                    title_norm = _normalize_chapter_title(parsed.get('title')) if parsed.get('title') else None
                    normed.append({'start_ms': start_ms, 'end_ms': end_ms, 'title': title_norm})
                    continue

            # Fallback: treat as a plain title and normalize shorthand
            if isinstance(x, str):
                normed.append(_normalize_chapter_title(x))
            else:
                normed.append(x)

        chap_titles = normed

    # For .m4b files we can change embedded chapter titles using --chapter-titles
    change_titles = chap_titles if chap_titles else None

    # Helper: parse time strings like HH:MM:SS or MM:SS or seconds to milliseconds
    def _time_to_ms(t):
        if t is None:
            return None
        # Already int/float representing ms
        if isinstance(t, int):
            return t
        if isinstance(t, float):
            # assume seconds
            return int(round(t * 1000))
        s = str(t).strip()
        # If purely numeric, treat as seconds
        try:
            if '.' in s or s.isdigit():
                # numeric string -> seconds
                return int(round(float(s) * 1000))
        except Exception:
            pass
        # If contains colons, parse H:M:S
        try:
            parts = [p for p in s.split(':') if p != '']
            parts = [float(p) for p in parts]
            # rightmost is seconds, next is minutes, then hours
            ms = 0
            if len(parts) == 1:
                ms = int(round(parts[0] * 1000))
            elif len(parts) == 2:
                ms = int(round((parts[0] * 60 + parts[1]) * 1000))
            elif len(parts) >= 3:
                h = parts[-3]
                m = parts[-2]
                ssec = parts[-1]
                ms = int(round((h * 3600 + m * 60 + ssec) * 1000))
            return ms
        except Exception:
            return None

    # Build base metadata updates from args
    # Cleaning helper
    def _clean(s):
        try:
            return book_title_logic(s).strip()
        except Exception:
            return str(s).strip()

    base_updates = {}
    if args.album is not None:
        base_updates['album'] = _clean(args.album)
    if args.album_sort is not None:
        base_updates['album_sort'] = _clean(args.album_sort)
    if args.author is not None:
        # Respect --author-fix flag: if set, convert "Last, First" -> "First Last"
        try:
            author_val = _maybe_fix_author(getattr(args, 'author', None), getattr(args, 'author_fix', False))
        except Exception:
            author_val = getattr(args, 'author', None)
        base_updates['artist'] = _clean(author_val)
    if args.narrator is not None:
        base_updates['composer'] = _clean(args.narrator)
    if args.series is not None:
        base_updates['grouping'] = _clean(args.series)
    if args.genre is not None:
        base_updates['genre'] = _clean(args.genre)
    if args.year is not None:
        # store as number/string depending on mapping expectations
        base_updates['year'] = int(args.year)
    if args.title is not None:
        # For m4b files, the user asked to error on title changes
        base_updates['_requested_title'] = args.title

    results = []
    for i, f in enumerate(targets):
        try:
            ext = os.path.splitext(f)[1].lower()

            # If title requested and file is .m4b, error as requested
            if 'title' in base_updates or '_requested_title' in base_updates:
                requested_title = base_updates.get('title') or base_updates.get('_requested_title')
                if ext == '.m4b' and requested_title:
                    logging.getLogger(__name__).error(f"Error: cannot set --title on .m4b file: {f}")
                    results.append({'file': f, 'status': 'error', 'error': 'title not allowed for m4b'})
                    continue

            # Build per-file metadata updates
            upd = {}
            # Start with base updates (excluding reserved key)
            for k, v in base_updates.items():
                if k == '_requested_title':
                    continue
                upd[k] = v

            # Apply chapter-titles mapping if provided (folder mode) for per-file titles
            if chap_titles:
                # Normalize shorthand like ch1 -> Chapter 1, then apply cleaning
                upd['title'] = _clean(_normalize_chapter_title(chap_titles[i]))
            else:
                # If a single title was provided, apply to all non-m4b files (unless error above)
                if args.title is not None and ext != '.m4b':
                    upd['title'] = _clean(args.title)
            # If the file is an M4B and chapter-titles-file was provided for single-file m4b, update embedded chapters
            if ext == '.m4b' and len(targets) == 1 and change_titles:
                try:
                    # Load MP4 and update chapters
                    from mutagen.mp4 import MP4, MP4Chapters, Chapter
                    mp4 = MP4(f)
                    existing_chapters = []
                    try:
                        if hasattr(mp4, 'chapters') and mp4.chapters is not None:
                            for ch in mp4.chapters:
                                # MP4Chapters yields Chapter objects with .start and .title
                                existing_chapters.append(ch)
                    except Exception:
                        # Older mutagen stores chapters differently; attempt to read via mp4.chapters._chapters
                        try:
                            existing_chapters = list(mp4.chapters._chapters)
                        except Exception:
                            existing_chapters = []
                    # Detect if user provided timed entries (dicts) in change_titles
                    timed_mode = any(isinstance(x, dict) for x in change_titles)

                    if timed_mode:
                        # Build new chapters from the provided dicts (start_ms/end_ms/title)
                        new_ch_objs = []
                        # Normalize entries into dicts with start_ms, end_ms, title
                        parsed = []
                        for item in change_titles:
                            if not isinstance(item, dict):
                                # plain title only -> keep title and no times
                                parsed.append({'start_ms': None, 'end_ms': None, 'title': str(item)})
                                continue
                            d = dict(item)
                            start_ms = None
                            end_ms = None
                            if 'start_ms' in d:
                                start_ms = _time_to_ms(d.get('start_ms'))
                            elif 'start' in d:
                                start_ms = _time_to_ms(d.get('start'))
                            if 'end_ms' in d:
                                end_ms = _time_to_ms(d.get('end_ms'))
                            elif 'end' in d:
                                end_ms = _time_to_ms(d.get('end'))
                            parsed.append({'start_ms': start_ms, 'end_ms': end_ms, 'title': d.get('title')})

                        # If starts are missing, attempt to infer by spacing across duration
                        try:
                            duration_ms = int(round(float(mp4.info.length) * 1000)) if hasattr(mp4, 'info') and mp4.info and getattr(mp4.info, 'length', None) else None
                        except Exception:
                            duration_ms = None

                        # Fill missing starts by distributing evenly where necessary
                        # First, collect explicit starts positions
                        explicit_starts = [p['start_ms'] for p in parsed if p['start_ms'] is not None]
                        if (not explicit_starts) and duration_ms and len(parsed) > 0:
                            # evenly space
                            num = len(parsed)
                            for idx, p in enumerate(parsed):
                                p['start_ms'] = int(round((duration_ms * idx) / float(num)))

                        # Infer end_ms where missing (next start or duration)
                        for idx, p in enumerate(parsed):
                            if p['end_ms'] is None:
                                if idx + 1 < len(parsed) and parsed[idx+1].get('start_ms') is not None:
                                    p['end_ms'] = parsed[idx+1]['start_ms']
                                else:
                                    p['end_ms'] = duration_ms if duration_ms is not None else (p['start_ms'] + 1000 if p['start_ms'] is not None else None)

                        # Validate ordering and non-overlap
                        last_end = -1
                        for p in parsed:
                            s = p['start_ms']
                            e = p['end_ms']
                            if s is None:
                                logger.error("Error: chapter missing start time: %s", p)
                                results.append({'file': f, 'status': 'error', 'error': 'missing start time'})
                                raise ValueError('missing start time')
                            if e is not None and e <= s:
                                logger.error("Error: chapter end <= start: %s", p)
                                results.append({'file': f, 'status': 'error', 'error': 'invalid chapter times'})
                                raise ValueError('invalid chapter times')
                            if last_end != -1 and s < last_end:
                                logger.error("Error: chapter start overlaps previous: %s", p)
                                results.append({'file': f, 'status': 'error', 'error': 'chapter overlap'})
                                raise ValueError('chapter overlap')
                            last_end = e if e is not None else s

                        # Create Chapter objects
                        for p in parsed:
                            title = _clean(p.get('title') or '')
                            s_ms = p.get('start_ms')
                            try:
                                new_ch = Chapter(start=s_ms, title=title)
                            except Exception:
                                try:
                                    new_ch = Chapter(start=(s_ms / 1000.0 if s_ms is not None else 0), title=title)
                                except Exception:
                                    new_ch = type('C', (), {})()
                                    setattr(new_ch, 'start', s_ms)
                                    setattr(new_ch, 'title', title)
                            new_ch_objs.append(new_ch)

                        # Assign and save, reusing ffmpeg fallback logic
                        try:
                            mp4_chapters = MP4Chapters()
                            mp4_chapters._chapters = new_ch_objs
                            mp4.chapters = mp4_chapters
                            mp4.save()
                            # verify persistence
                            mp4_reload = MP4(f)
                            if hasattr(mp4_reload, 'chapters') and mp4_reload.chapters:
                                results.append({'file': f, 'status': 'ok'})
                            else:
                                # Fall back to ffmpeg injection using helper
                                try:
                                    ff_res = ffmpeg_inject_chapters(f, parsed)
                                    if ff_res.get('status') == 'ok':
                                        results.append({'file': f, 'status': 'ok', 'note': ff_res.get('note')})
                                    elif ff_res.get('status') == 'no_ffmpeg':
                                        results.append({'file': f, 'status': 'ok', 'note': 'created chapters (in-memory only)'})
                                    else:
                                        results.append({'file': f, 'status': 'error', 'error': ff_res.get('note')})
                                except Exception as e_meta:
                                    results.append({'file': f, 'status': 'error', 'error': f'ffmpeg chapter injection failed: {e_meta}'})
                        except Exception as e:
                            results.append({'file': f, 'status': 'error', 'error': str(e)})
                        # done timed_mode processing for this file
                        continue

                    if not existing_chapters:
                        # Attempt to create chapters if the MP4 has no chapters but the
                        # user provided --chapter-titles. Use the file duration to
                        # space chapters evenly. If we can't determine duration,
                        # fall back to previous behavior (ignore).
                        try:
                            duration = None
                            try:
                                duration = float(mp4.info.length)
                            except Exception:
                                duration = None

                            if duration and duration > 0 and len(change_titles) > 0:
                                # Compute start times in milliseconds, evenly spaced
                                num = len(change_titles)
                                interval = duration / float(num)
                                new_ch_objs = []
                                for idx in range(num):
                                    start_sec = idx * interval
                                    start_ms = int(round(start_sec * 1000))
                                    title = _clean(_normalize_chapter_title(change_titles[idx]))
                                    try:
                                        new_ch = Chapter(start=start_ms, title=title)
                                    except Exception:
                                        # If Chapter constructor expects seconds instead
                                        # of ms, try seconds
                                        try:
                                            new_ch = Chapter(start=start_sec, title=title)
                                        except Exception:
                                            # Last resort: create a simple namespace-like object
                                            new_ch = type('C', (), {})()
                                            setattr(new_ch, 'start', start_ms)
                                            setattr(new_ch, 'title', title)
                                    new_ch_objs.append(new_ch)

                                try:
                                    mp4_chapters = MP4Chapters()
                                    mp4_chapters._chapters = new_ch_objs
                                    mp4.chapters = mp4_chapters
                                    mp4.save()
                                    # Verify persistence; reload and check
                                    try:
                                        mp4_reload = MP4(f)
                                        if hasattr(mp4_reload, 'chapters') and mp4_reload.chapters:
                                            results.append({'file': f, 'status': 'ok', 'note': 'created chapters'})
                                        else:
                                            # If mutagen didn't persist chapters, try ffmpeg metadata injection
                                            import shutil, tempfile, subprocess
                                            ffmpeg_path = shutil.which('ffmpeg')
                                            # Fall back to ffmpeg injection using helper
                                            try:
                                                # Build a helper-friendly chapters list (start_ms/end_ms/title)
                                                helper_chs = []
                                                for idx in range(len(new_ch_objs)):
                                                    start = getattr(new_ch_objs[idx], 'start', 0)
                                                    # normalize to milliseconds
                                                    if isinstance(start, (int,)) and start > 1000:
                                                        s_ms = int(round(start))
                                                    else:
                                                        try:
                                                            s_ms = int(round(float(start) * 1000))
                                                        except Exception:
                                                            s_ms = 0
                                                    # end is next start or +1000ms
                                                    if idx + 1 < len(new_ch_objs):
                                                        nxt = getattr(new_ch_objs[idx+1], 'start', None)
                                                        if isinstance(nxt, int) and nxt > 1000:
                                                            e_ms = int(round(nxt))
                                                        else:
                                                            try:
                                                                e_ms = int(round(float(nxt) * 1000)) if nxt is not None else s_ms + 1000
                                                            except Exception:
                                                                e_ms = s_ms + 1000
                                                    else:
                                                        e_ms = s_ms + 1000
                                                    title = getattr(new_ch_objs[idx], 'title', '') or ''
                                                    helper_chs.append({'start_ms': s_ms, 'end_ms': e_ms, 'title': title})

                                                ff_res = ffmpeg_inject_chapters(f, helper_chs)
                                                if ff_res.get('status') == 'ok':
                                                    results.append({'file': f, 'status': 'ok', 'note': ff_res.get('note')})
                                                elif ff_res.get('status') == 'no_ffmpeg':
                                                    results.append({'file': f, 'status': 'ok', 'note': 'created chapters (in-memory only)'})
                                                else:
                                                    results.append({'file': f, 'status': 'error', 'error': ff_res.get('note')})
                                            except Exception as e_meta:
                                                results.append({'file': f, 'status': 'error', 'error': f'ffmpeg chapter injection failed: {e_meta}'})
                                    except Exception:
                                        results.append({'file': f, 'status': 'ok', 'note': 'created chapters'})
                                except Exception as e:
                                    # Could not create chapters; fallback to ignore
                                    logger.warning("Could not create chapters for %s: %s", f, e)
                                    results.append({'file': f, 'status': 'ok', 'note': 'no chapters'})
                            else:
                                logger.warning("No chapters found in %s; --chapter-titles ignored", f)
                                results.append({'file': f, 'status': 'ok', 'note': 'no chapters'})
                        except Exception as e:
                            # Any unexpected error -> ignore chapter change for this file
                            logger.warning("Failed while creating chapters for %s: %s", f, e)
                            results.append({'file': f, 'status': 'ok', 'note': 'no chapters'})
                    else:
                        if len(existing_chapters) != len(change_titles):
                            logger.error("Error: --chapter-titles provided %d titles but %d chapters found in %s", len(change_titles), len(existing_chapters), f)
                            results.append({'file': f, 'status': 'error', 'error': 'chapter count mismatch'})
                        else:
                            # Replace titles while preserving start times
                            new_ch_objs = []
                            for idx, ch in enumerate(existing_chapters):
                                try:
                                    start = getattr(ch, 'start', None)
                                except Exception:
                                    start = None
                                title = _clean(_normalize_chapter_title(change_titles[idx]))
                                # Create new Chapter object if possible
                                try:
                                    new_ch = Chapter(start=start, title=title)
                                except Exception:
                                    # Fallback: mutate existing object's title attribute
                                    try:
                                        ch.title = title
                                        new_ch = ch
                                    except Exception:
                                        new_ch = ch
                                new_ch_objs.append(new_ch)

                            # Assign chapters back
                            try:
                                mp4_chapters = MP4Chapters()
                                mp4_chapters._chapters = new_ch_objs
                                mp4.chapters = mp4_chapters
                                mp4.save()
                                results.append({'file': f, 'status': 'ok'})
                            except Exception as e:
                                results.append({'file': f, 'status': 'error', 'error': str(e)})
                except Exception as e:
                    results.append({'file': f, 'status': 'error', 'error': str(e)})
            else:
                # Finally, apply metadata to file (non-m4b or regular updates)
                apply_metadata_to_file(f, upd)
                results.append({'file': f, 'status': 'ok'})
        except Exception as e:
            results.append({'file': f, 'status': 'error', 'error': str(e)})

    # Print JSON summary to stdout for CLI consumers/tests, and also log it
    summary = json.dumps({'operation': 'change', 'path': path, 'results': results}, indent=2)
    # Write the JSON summary explicitly to stdout so callers/tests that capture
    # stdout receive only the JSON payload. Also emit the same summary to the
    # logger for structured logging consumers.
    try:
        sys.stdout.write(summary + "\n")
        sys.stdout.flush()
    except Exception:
        # Fallback to print if stdout isn't writable for some reason
        try:
            print(summary)
        except Exception:
            pass
    logging.getLogger(__name__).info(summary)


def cmd_mutate(args):
    """Mutate metadata and move files"""
    source_path = args.source
    destination_path = args.destination

    try:
        if os.path.isfile(source_path):
            logging.getLogger(__name__).error("Mutate operation requires a folder. Use extract for single files.")
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
                mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False))
                final_path = move_to_destination(mutated_path, str(destination_path), "novel")
                result = {
                    "operation": "mutate",
                    "original_folder": str(source_path),
                    "mutated_folder": mutated_path,
                    "final_destination": final_path,
                    "folder_type": "novel"
                }
                logger.info(json.dumps(result, indent=2))
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
                                        mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False))
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
                            logger.info(json.dumps(result, indent=2))
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
                                            mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False))
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
                                logger.info(json.dumps(result, indent=2))
                                return
                    except Exception:
                        pass

                # Final fallback: use our own recursive analysis
                logger.info("Using built-in folder structure analysis...")
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
                                    mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False))
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
                        logger.info(json.dumps(result, indent=2))
                        return
                except Exception as e:
                    logger.error("Fallback analysis failed: %s", e)

                raise ValueError("Could not process folder structure: {}".format(source_path))
            else:
                raise ValueError("Folder {} contains no audio files".format(source_path))

    except Exception as e:
        logger.error("Error: %s", e)


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
            logger.info("Configuration reset to defaults and saved.")
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
                logger.info("Set %s = %s", key, parsed_value)
            except ValueError:
                logger.error("Error: --set requires format key=value")
        elif args.get:
            value = config.get(args.get)
            logger.info("%s = %s", args.get, value)
        else:
            logger.info("Configuration file location: %s", config.config_path or "Not found")
            logger.info("Use --help for configuration options")
            
    except ImportError:
        logger.error("Configuration management not available")


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
            logger.error("Mutate-convert operation requires a folder. Use extract for single files.")
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
                # Mutate metadata in-place (do not copy into a temp folder)
                mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False), in_place=True)
                temp_mutated_path = mutated_path
                
                logger.info("Mutated files created in: %s", temp_mutated_path)
                
                # Step 2: Convert the mutated files to M4B
                logger.info("Step 2: Converting mutated files to M4B...")
                
                # Create a mock args object for cmd_convert
                class MockArgs:
                    def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None, author_name=None, author_fix=False, album_names=False):
                        self.source = source
                        self.output = output
                        self.sort_by = sort_by
                        self.chapter_titles = chapter_titles
                        self.series_name = series_name
                        self.author_name = author_name
                        self.author_fix = author_fix
                        self.album_names = album_names

                convert_args = MockArgs(
                    temp_mutated_path,
                    destination_path,
                    args.sort_by,
                    getattr(args, 'chapter_titles', False),
                    series_name=getattr(args, 'series_name', None),
                    author_name=getattr(args, 'author_name', None),
                    author_fix=getattr(args, 'author_fix', False),
                    album_names=getattr(args, 'album_names', False)
                )
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
                                        # Mutate metadata in-place (use original folder directly)
                                        mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False), in_place=True)
                                        temp_mutated_path = mutated_path
                                        
                                        # Convert to M4B
                                        # Create a mock args object for cmd_convert
                                        class MockArgs:
                                            def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None, author_name=None, author_fix=False, album_names=False):
                                                self.source = source
                                                self.output = output
                                                self.sort_by = sort_by
                                                self.chapter_titles = chapter_titles
                                                self.series_name = series_name
                                                self.author_name = author_name
                                                self.author_fix = author_fix
                                                self.album_names = album_names

                                        # Generate output filename from the original folder name (not the temp mutated folder)
                                        raw_name = os.path.basename(folder_path.rstrip('/\\'))
                                        folder_name = clean_album_name(raw_name) or raw_name
                                        m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))

                                        convert_args = MockArgs(
                                            temp_mutated_path,
                                            m4b_output_path,
                                            args.sort_by,
                                            getattr(args, 'chapter_titles', False),
                                            series_name=getattr(args, 'series_name', None),
                                            author_name=getattr(args, 'author_name', None),
                                            author_fix=getattr(args, 'author_fix', False),
                                            album_names=getattr(args, 'album_names', False)
                                        )
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
                            logger.info(json.dumps(result, indent=2))
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
                                            # Mutate metadata in-place (use original folder directly)
                                            mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False), in_place=True)
                                            temp_mutated_path = mutated_path
                                            
                                            # Convert to M4B
                                            class MockArgs:
                                                def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None, author_fix=False, album_names=False):
                                                    self.source = source
                                                    self.output = output
                                                    self.sort_by = sort_by
                                                    self.chapter_titles = chapter_titles
                                                    self.series_name = series_name
                                                    self.author_fix = author_fix
                                                    self.album_names = album_names
                                            
                                            # Use the original path provided by series_verify to derive the output filename
                                            raw_name = os.path.basename(path.rstrip('/\\'))
                                            folder_name = clean_album_name(raw_name) or raw_name
                                            m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))
                                            
                                            convert_args = MockArgs(temp_mutated_path, m4b_output_path, args.sort_by, getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), author_fix=getattr(args, 'author_fix', False), album_names=getattr(args, 'album_names', False))
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
                                    logger.info(json.dumps(result, indent=2))
                                    return
                    except Exception:
                        pass

                # Final fallback: use our own recursive analysis
                logger.info("Using built-in folder structure analysis...")
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
                                    mutated_path = mutate_metadata(metadata_dict, args.album_sort_prefix, args.album_suffix, sort_by='filename', chapter_titles=getattr(args, 'chapter_titles', False), series_name=getattr(args, 'series_name', None), part_titles=getattr(args, 'part_titles', False), author_name=_maybe_fix_author(getattr(args, 'author_name', None), getattr(args, 'author_fix', False)), narrator_name=getattr(args, 'narrator_name', None), author_fix=getattr(args, 'author_fix', False))
                                    # Move to temp directory
                                    temp_mutated_path = move_to_destination(mutated_path, temp_dir, folder_type)

                                    # Convert to M4B
                                    class MockArgs:
                                            def __init__(self, source, output, sort_by, chapter_titles=False, series_name=None, author_fix=False, album_names=False):
                                                self.source = source
                                                self.output = output
                                                self.sort_by = sort_by
                                                self.chapter_titles = chapter_titles
                                                self.series_name = series_name
                                                self.author_fix = author_fix
                                                self.album_names = album_names

                                    # Use the original folder path from folder_structure to derive the output filename
                                    raw_name = os.path.basename(folder_path.rstrip('/\\'))
                                    folder_name = clean_album_name(raw_name) or raw_name
                                    m4b_output_path = os.path.join(destination_path, "{}.m4b".format(folder_name))

                                    convert_args = MockArgs(
                                        temp_mutated_path,
                                        m4b_output_path,
                                        args.sort_by,
                                        getattr(args, 'chapter_titles', False),
                                        series_name=getattr(args, 'series_name', None),
                                        author_fix=getattr(args, 'author_fix', False),
                                        album_names=getattr(args, 'album_names', False)
                                    )
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
                        logger.info(json.dumps(result, indent=2))
                        return
                except Exception as e:
                    logger.error("Fallback analysis failed: %s", e)

                logger.error("Multi-folder processing not yet supported for mutate-convert")
                return
            else:
                logger.error("No audio files found in source folder")
                return
        else:
            logger.error("Source path does not exist: %s", source_path)
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
    mutate_parser.add_argument('--album-sort-prefix', help='String to prefix album_sort with " - " separator')
    mutate_parser.add_argument('--album-suffix', help='String to suffix album with " - " separator')
    mutate_parser.add_argument('--chapter-titles', action='store_true', help='Use "BookName - Chapter X" format for track titles instead of existing titles')
    mutate_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    mutate_parser.add_argument('--part-titles', action='store_true', help='Set titles and filenames to "<Cleaned Folder Name>: Part N" grouping every 10 files')
    mutate_parser.add_argument('--author-name', help='Explicit author/artist name to apply to artist tag (will be cleaned)')
    mutate_parser.add_argument('--author-fix', action='store_true', help='If set, treat provided author name as "Last, First" and convert to "First Last"')
    mutate_parser.add_argument('--narrator-name', help='Explicit narrator/composer name to apply to composer tag (will be cleaned)')
    mutate_parser.add_argument('--album-names', action='store_true', help='Force album name to cleaned folder name')
    mutate_parser.set_defaults(func=cmd_mutate)

    # Convert command
    convert_parser = subparsers.add_parser('convert', help='Convert folder of audio files to M4B with chapters (enclose paths with spaces in quotes)')
    convert_parser.add_argument('source', help='Path to folder containing audio files (quotes required if path contains spaces)')
    convert_parser.add_argument('output', help='Output directory or M4B file path (quotes required if path contains spaces)')
    convert_parser.add_argument('--sort-by', choices=['filename', 'track'], default='filename', help='Sort files by filename (default) or track number metadata')
    convert_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    convert_parser.add_argument('--album-names', action='store_true', help='Force album name to cleaned folder name')
    convert_parser.set_defaults(func=cmd_convert)

    # Mutate-Convert command
    mutate_convert_parser = subparsers.add_parser('mutate-convert', help='Mutate metadata then convert to M4B in one operation (enclose paths with spaces in quotes)')
    mutate_convert_parser.add_argument('source', help='Path to audio folder (quotes required if path contains spaces)')
    mutate_convert_parser.add_argument('destination', help='Destination path for final M4B file (quotes required if path contains spaces)')
    mutate_convert_parser.add_argument('--album-sort-prefix', help='String to prefix album_sort with " - " separator')
    mutate_convert_parser.add_argument('--album-suffix', help='String to suffix album with " - " separator')
    mutate_convert_parser.add_argument('--sort-by', choices=['filename', 'track'], default='filename', help='Sort files by filename (default) or track number metadata')
    mutate_convert_parser.add_argument('--chapter-titles', action='store_true', help='Use "BookName - Chapter X" format for track titles instead of existing titles')
    mutate_convert_parser.add_argument('--series-name', help='Explicit series name to apply to grouping and series freeform')
    mutate_convert_parser.add_argument('--part-titles', action='store_true', help='Set titles and filenames to "<Cleaned Folder Name>: Part N" grouping every 10 files')
    mutate_convert_parser.add_argument('--author-name', help='Explicit author/artist name to apply to artist tag (will be cleaned)')
    mutate_convert_parser.add_argument('--author-fix', action='store_true', help='If set, treat provided author name as "Last, First" and convert to "First Last"')
    mutate_convert_parser.add_argument('--narrator-name', help='Explicit narrator/composer name to apply to composer tag (will be cleaned)')
    mutate_convert_parser.add_argument('--album-names', action='store_true', help='Force album name to cleaned folder name')
    mutate_convert_parser.set_defaults(func=cmd_mutate_convert)

    # Change command - update metadata on files or a folder of files
    change_parser = subparsers.add_parser('change', help='Change metadata on a single audio file or all audio files in a folder')
    change_parser.add_argument('path', help='Path to audio file or folder (quotes required if path contains spaces)')
    change_parser.add_argument('--album', help='Set album tag')
    change_parser.add_argument('--album-sort', help='Set album_sort tag')
    change_parser.add_argument('--author', help='Set artist/author tag')
    change_parser.add_argument('--author-fix', action='store_true', help='If set, treat provided --author value as "Last, First" and convert to "First Last"')
    change_parser.add_argument('--narrator', help='Set composer/narrator tag')
    change_parser.add_argument('--series', help='Set series/grouping tag')
    change_parser.add_argument('--genre', help='Set genre tag')
    change_parser.add_argument('--year', help='Set year tag')
    change_parser.add_argument('--title', help='Set title for files (not allowed for .m4b)')
    change_parser.add_argument(
        '--chapter-titles-file',
        help=(
            'Path to a chapter titles file. Supported formats:\n'
            '- JSON array of strings: ["Title 1", "Title 2"]\n'
            '- JSON array of objects for timed chapters: [{"start":"00:00:00","end":"00:05:00","title":"Chapter 1"}, ...]\n'
            '- ffmetadata (ffmpeg) files starting with ";FFMETADATA1" and containing [CHAPTER] sections\n'
            '- Plain text: one title per line\n\n'
            'Usage notes:\n'
            '- For folders: provide a list/array of titles (one per audio file, in filename order).\n'
            "- For a single .m4b: you may provide timed entries (start/end/title) to set chapter boundaries.\n"
            'Examples:\n'
            '  audiobook-p change /path/to/book.m4b --chapter-titles-file chapters.json\n'
            '  audiobook-p change /path/to/folder --chapter-titles-file titles.txt\n'
            'Times may be in HH:MM:SS, MM:SS or seconds (e.g. "65.5").'
        )
    )
    change_parser.set_defaults(func=cmd_change)

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
