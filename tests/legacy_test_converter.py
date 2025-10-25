"""
legacy_test_converter.py

Provides a compatibility wrapper for legacy tests to adapt their inputs/outputs to the current mutate_metadata/cmd_mutate_convert API.
"""
import os
from audiobook_p import main as mainmod

def legacy_test_converter(metadata, *args, **kwargs):
    """
    Adapts legacy test metadata and arguments to the current mutate_metadata API.
    Returns a dict with expected legacy keys for assertions.
    """
    # If metadata is a dict with 'files', treat as legacy format
    if isinstance(metadata, dict) and 'files' in metadata:
        # Run mutate_metadata and adapt output
        result = mainmod.mutate_metadata(metadata, *args, **kwargs)
        # If result is a dict with 'files', return as legacy
        if isinstance(result, dict) and 'files' in result:
            return result
        # If result is a path, extract metadata from folder
        if isinstance(result, str) and os.path.isdir(result):
            # Try to extract metadata from folder
            meta = mainmod.extract_metadata_from_folder(result, metadata.get('folder_type', 'novel'))
            return {'files': meta.get('files', {})}
        return result
    # If metadata is a path, extract metadata
    if isinstance(metadata, str) and os.path.isdir(metadata):
        meta = mainmod.extract_metadata_from_folder(metadata, kwargs.get('folder_type', 'novel'))
        return {'files': meta.get('files', {})}
    # For legacy tests that pass invalid metadata, return a dict with 'files'
    return {'files': {}}
