"""Chapter parsing helpers for audiobook-p

Provides parse_chapter_spec and parse_time_to_seconds utilities.

Supported input forms (strings):
- "HH:MM:SS-HH:MM:SS:Title"
- "MM:SS-HH:MM:SS:Title" or seconds as integers/floats
- "start=00:00:00,end=00:05:00,title=Chapter 1"
- JSON object string like '{"start":"00:00:00","end":"00:05:00","title":"Chapter 1"}'
- Plain title ("Chapter 1") or shorthand like "ch1" or "1"

Outputs a dict: {"start_s": float or None, "end_s": float or None, "title": str}
"""
from __future__ import annotations

import json
import re
from typing import Optional, Dict, Any

_TIME_PATTERNS = [
    # HH:MM:SS(.ms?)
    re.compile(r'^(?P<h>\d+):(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:\.\d+)?)$'),
    # MM:SS(.ms?)
    re.compile(r'^(?P<m>\d{1,2}):(?P<s>\d{1,2}(?:\.\d+)?)$'),
    # seconds (float/int)
    re.compile(r'^(?P<s>\d+(?:\.\d+)?)$')
]


def parse_time_to_seconds(t: Optional[str]) -> Optional[float]:
    """Parse a time expression into seconds (float).

    Accepts HH:MM:SS, MM:SS, or plain seconds (integer or float). Returns
    None if input is falsy.
    """
    if t is None:
        return None
    try:
        s = str(t).strip()
    except Exception:
        return None
    if s == '':
        return None

    # Try numeric seconds first
    for pat in _TIME_PATTERNS:
        m = pat.match(s)
        if m:
            gd = m.groupdict()
            hours = float(gd.get('h') or 0)
            mins = float(gd.get('m') or 0)
            secs = float(gd.get('s') or 0)
            total = hours * 3600.0 + mins * 60.0 + secs
            return float(total)

    # Try to parse fractional seconds with comma as decimal
    if ',' in s:
        s2 = s.replace(',', '.')
        try:
            return float(s2)
        except Exception:
            pass

    # If nothing matched, return None
    return None


def _normalize_title(t: Optional[str]) -> Optional[str]:
    if t is None:
        return None
    try:
        st = str(t).strip()
    except Exception:
        return None
    if not st:
        return None

    # shorthand like ch1 or chapter1 -> Chapter N
    m = re.match(r'^(?:ch|c|chapter)\s*[-\.:]?\s*(\d+)(?:\s+(.+))?$', st, re.IGNORECASE)
    if m:
        try:
            n = int(m.group(1))
            suffix = m.group(2)
            if suffix:
                return f"Chapter {n} {suffix.strip()}"
            return f"Chapter {n}"
        except Exception:
            pass

    # numeric like '1' or '#1' -> Chapter 1
    m2 = re.match(r'^[#]?(\d+)(?:\s+(.+))?$', st)
    if m2:
        try:
            n = int(m2.group(1))
            suffix = m2.group(2)
            if suffix:
                return f"Chapter {n} {suffix.strip()}"
            return f"Chapter {n}"
        except Exception:
            pass

    return st


def parse_chapter_spec(spec: Any) -> Dict[str, Any]:
    """Parse a single chapter spec into normalized dict.

    Returns: {"start_s": Optional[float], "end_s": Optional[float], "title": Optional[str]}
    """
    # If it's already a dict-like object, normalize expected keys
    if isinstance(spec, dict):
        start = parse_time_to_seconds(spec.get('start') or spec.get('start_s') or spec.get('start_sec'))
        end = parse_time_to_seconds(spec.get('end') or spec.get('end_s') or spec.get('end_sec'))
        title = spec.get('title') or spec.get('t') or spec.get('name')
        title = _normalize_title(title)
        return {"start_s": start, "end_s": end, "title": title}

    # If it's JSON string representing an object, try to load
    if isinstance(spec, str):
        s = spec.strip()
        # JSON object string
        if s.startswith('{') and s.endswith('}'):
            try:
                obj = json.loads(s)
                return parse_chapter_spec(obj)
            except Exception:
                pass

        # Key=val comma-separated form: start=...,end=...,title=...
        if '=' in s and (',' in s or 'start' in s.lower()):
            # split by commas but allow commas inside quotes
            parts = re.split(r'\s*,\s*(?=(?:[^\']*\'[^\']*\')*[^\']*$)', s)
            kv = {}
            for p in parts:
                if '=' in p:
                    k, v = p.split('=', 1)
                    kv[k.strip().lower()] = v.strip().strip('"\'')
            if kv:
                return parse_chapter_spec(kv)

        # Range with optional title: "start-end:Title" where start/end are times or seconds
        # Examples: "00:00:00-00:05:00:Chapter 1" or "0-300:Intro"
        # We need to allow colons inside the time expressions. Strategy:
        # - Split on the first '-' to get start and the remainder
        # - From the remainder, match an end time at the beginning (HH:MM:SS, MM:SS, or seconds)
        #   and optionally a ':' followed by the title.
        if '-' in s:
            left, right = s.split('-', 1)
            start_raw = left.strip()
            rest = right.strip()
            # Match an end time at the start of rest
            m_end = re.match(r'^(?P<end>\d+(?::\d+){0,2}(?:\.\d+)?)(?:\s*:\s*(?P<title>.*))?$', rest)
            if m_end:
                end_raw = m_end.group('end')
                title_raw = m_end.group('title')
                start = parse_time_to_seconds(start_raw)
                end = parse_time_to_seconds(end_raw)
                title = _normalize_title(title_raw)
                return {"start_s": start, "end_s": end, "title": title}

        # If just a single time with optional title e.g. "00:00:00:Title" or "65.5:Intro"
        m_single = re.match(r'^([^:\n]+)\s*:\s*(.+)$', s)
        if m_single:
            start = parse_time_to_seconds(m_single.group(1))
            title = _normalize_title(m_single.group(2))
            return {"start_s": start, "end_s": None, "title": title}

        # Otherwise treat as a plain title or shorthand like 'ch1'
        title = _normalize_title(s)
        return {"start_s": None, "end_s": None, "title": title}

    # Unsupported type: return empty
    return {"start_s": None, "end_s": None, "title": None}


if __name__ == '__main__':
    # Quick manual smoke tests
    examples = [
        '00:00:00-00:05:00:Chapter 1',
        '0-300:Intro',
        '{"start":"00:05:00","title":"Part 1"}',
        'ch2',
        '1',
        '65.5:Quick'
    ]
    for e in examples:
        try:
            import logging
            logging.getLogger(__name__).info("%s -> %s", e, parse_chapter_spec(e))
        except Exception:
            pass
