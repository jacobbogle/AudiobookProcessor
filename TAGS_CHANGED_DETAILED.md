# Tags changed — detailed mapping to functions and modes

This document lists the descriptive tags the AudiobookProcessor updates or copies, explains exactly how each is transformed, and shows which functions perform the change and in which CLI mode or option it's applied.

---

## title
- What: Chapter title / track title stored in the file.
- How: Set to the cleaned filename (filename stem without extension) using `book_title_logic` (removes leading numbers and normalizes capitalization). When converting, chapter titles prefer the file's `title` metadata; otherwise the cleaned filename is used.
- Functions: `mutate_metadata()` (assigns `title`), `apply_metadata_to_file()` (writes it), `convert_folder_to_m4b()` (uses `title` when building chapters).
- Modes / Options: `mutate`, `mutate-convert`, `convert` (conversion uses `title` if present; otherwise falls back to cleaned filename).

---

## sort_title
- What: Sort-friendly title used for stable ordering.
- How: Set to the raw filename stem (unchanged from the filename).
- Functions: `mutate_metadata()` (sets `sort_title`), `apply_metadata_to_file()` (writes it where supported).
- Modes / Options: `mutate`, `mutate-convert`.

---

## album
- What: Album name (book title / folder name).
- How: Set to the cleaned folder name via `book_title_logic`.
- Functions: `mutate_metadata()` (updates `album`), `apply_metadata_to_file()` (writes), `add_audiobook_metadata()` (copies to M4B after convert).
- Modes / Options: `mutate`, `mutate-convert`, `convert`.

---

## album_sort
- What: Sortable album value.
- How: Constructed by `mutate_metadata()`:
  - Novels: `album_sort = album`.
  - Series: `album_sort = "<Parent> - <Folder>"`.
  - Optional prefix via `--album-sort-prefix`: `"<prefix> : <album_sort>"`.
- Functions: `mutate_metadata()` (constructs), `apply_metadata_to_file()` (writes).
- Modes / Options: `mutate`, `mutate-convert`.

---

## track
- What: Track number (chapter index).
- How: Reassigned sequentially (stored as string, e.g. "1") according to chosen sort order.
- Functions: `mutate_metadata()` (computes index and sets `track`), `apply_metadata_to_file()` (writes ID3/MP4 track fields).
- Modes / Options: `mutate`, `mutate-convert`. Sorting controlled by `--sort-by` (`filename` or `track`).

---

## media_kind
- What: Numeric media type indicator.
- How: Set to `2` (Audiobook).
- Functions: `mutate_metadata()` (sets value), `apply_metadata_to_file()` (writes if mapping present).
- Modes / Options: `mutate`, `mutate-convert`.

---

## genre
- What: Genre tag.
- How: Set to `"Audiobook"`.
- Functions: `mutate_metadata()` (sets value), `apply_metadata_to_file()` (writes tag).
- Modes / Options: `mutate`, `mutate-convert`.

---

## picture / cover_art
- What: Embedded cover artwork.
- How: Preserved on mutation; copied to final M4B's MP4 `covr` tag during conversion if found.
- Functions: `apply_metadata_to_file()` (preserve/avoid overwrite), `add_audiobook_metadata()` (search & copy `covr`/`APIC`).
- Modes / Options: `mutate` (preserve), `convert`, `mutate-convert` (copy to M4B).

---

## comment (ID3 COMM frames)
- What: Free-form comments.
- How: Copied when available; best COMM frame chosen heuristically (prefer no-description, or longest text).
- Functions: `extract_metadata_from_file()` (collect COMM frames), `add_audiobook_metadata()` (select & copy best).
- Modes / Options: `extract`, `convert`, `mutate-convert`.

---

## track_number (MP4 representation)
- What: MP4 track stored as a tuple `(track, total)`.
- How / Use: Read from MP4 and used for sorting when `--sort-by track` is used. Mutation assigns `track` sequentially if `mutate` is run.
- Functions: `extract_metadata_from_file()` (reads tuple), `track_number_sort_key()` (interprets tuple), `extract_metadata_from_folder()` / `convert_folder_to_m4b()` when `--sort-by track`.
- Modes / Options: `--sort-by track` for `convert` and `mutate-convert`; visible in `extract`.

---

## other mapped fields (artist, album artist, composer, publisher, etc.)
- What: Additional standard metadata fields.
- How: Copied from source to destination when mappings exist in `combined-metadata-mapping.json`. Values reformatted for destination file type.
- Functions: `extract_metadata_from_file()` (reads), `reformat_tag_for_file_type()` (formats), `apply_metadata_to_file()` / `add_audiobook_metadata()` (writes).
- Modes / Options: `extract`, `mutate`, `convert`, `mutate-convert`.

---

## Fallback behaviors
- Missing metadata: fall back to filename-derived values (cleaned filename used for title/chapter title).
- Malformed/missing track: under `--sort-by track`, files lacking valid track numbers fall back to natural filename sorting (`natural_sort_key()`).
- Cover art conversion: MP3 `APIC` frames converted to MP4 `covr` where possible.

---

If you want this content merged into `DATA_FLOW_ANALYSIS.md`, I can append a concise "Tags changed" subsection there. Would you like that?"