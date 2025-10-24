from mutagen.mp4 import MP4, MP4Cover
import json
p='/Users/channingbogle/Desktop/Audiobooks/result/Seventh Son.m4b'
a=MP4(p)
tags = a.tags or {}

def norm(v):
    # Normalize a tag value into a JSON-serializable list representation.
    # Some MP4 tag values are scalars (bool, int) rather than iterable.
    out = []
    # Treat bytes and MP4Cover as single binary entries
    if isinstance(v, (bytes, MP4Cover)):
        return [f'<{len(v)} bytes>']

    # If it's not iterable (e.g., bool/int), return it as a single-item list
    try:
        iter(v)
    except TypeError:
        return [v]

    # Otherwise iterate and normalize each element
    for x in v:
        try:
            if isinstance(x, (bytes, MP4Cover)):
                out.append(f'<{len(x)} bytes>')
            else:
                out.append(x)
        except Exception:
            out.append(repr(x))
    return out

d = {k: norm(v) for k, v in tags.items()}
print(json.dumps(d, ensure_ascii=False, indent=2))
