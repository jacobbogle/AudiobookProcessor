import os
import json

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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    mapping_path = os.path.join(script_dir, 'combined-metadata-mapping.json')
    with open(mapping_path, 'r') as f:
        mapping = json.load(f)
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
            return python_value
        elif dt == 'numeric_string':
            return str(python_value)
        else:
            return python_value
    elif file_type.lower() == 'mp4':
        dt = data_types.get('mp4', 'utf8_text')
        if dt == 'utf8_text':
            return [str(python_value)]
        elif dt == 'integer':
            try:
                if isinstance(python_value, list) and len(python_value) > 0:
                    python_value = python_value[0]
                if isinstance(python_value, bytes):
                    try:
                        s = python_value.decode('utf-8')
                    except Exception:
                        s = python_value.decode('latin-1', errors='ignore')
                else:
                    s = str(python_value)
                import re
                m = re.search(r"(\d+)", s)
                if m:
                    return [int(m.group(1))]
                try:
                    return [int(python_value)]
                except Exception:
                    return [0]
            except Exception:
                return [0]
        elif dt == 'boolean':
            return [bool(python_value)]
        elif dt == 'tuple_of_ints':
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
                try:
                    return [(int(python_value), 0)]
                except ValueError:
                    return [(0, 0)]
        elif dt == 'list_of_mp4cover':
            return python_value
        else:
            return [str(python_value)]
    else:
        return python_value
