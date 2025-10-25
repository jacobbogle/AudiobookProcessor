# File operation utilities for mutation
import shutil

def copy_file(src, dst, overwrite=False):
	"""Copy a file from src to dst. Overwrite if specified."""
	if overwrite and os.path.exists(dst):
		os.remove(dst)
	shutil.copy2(src, dst)

def move_file(src, dst, overwrite=False):
	"""Move a file from src to dst. Overwrite if specified."""
	print(f"[DIAG-move_file] src: {src}, dst: {dst}")
	print(f"[DIAG-move_file] src exists before: {os.path.exists(src)}, dst exists before: {os.path.exists(dst)}")
	if overwrite and os.path.exists(dst):
		os.remove(dst)
	shutil.move(src, dst)
	print(f"[DIAG-move_file] src exists after: {os.path.exists(src)}, dst exists after: {os.path.exists(dst)}")

def remove_path(path):
	"""Remove a file or directory at path."""
	if os.path.isdir(path):
		shutil.rmtree(path)
	elif os.path.exists(path):
		os.remove(path)
# Utility functions moved from main.py for modularity
import os
import re

def sanitize_string(value, replace_underscores=True):
	if value is None:
		return value
	try:
		s = str(value)
	except Exception:
		return value
	try:
		s = re.sub(r'\s+', ' ', s)
		s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+', '', s)
		if replace_underscores:
			s = re.sub(r'_+', ' ', s)
		s = s.strip()
	except Exception:
		try:
			s = s.strip()
		except Exception:
			pass
	return s

def book_title_logic(name):
	if not name:
		return name
	try:
		s = str(name).strip()
	except Exception:
		return name
	s = re.sub(r'^\s*(?:\(|)?\d{1,3}(?:\)|)?(?:\s|-|\.|:)+', '', s)
	s = re.sub(r'^[\-\._\s]+', '', s)
	s = re.sub(r'\s{2,}', ' ', s)
	if s:
		# Capitalize first non-numeric word after any leading numbers
		parts = s.split()
		for i, part in enumerate(parts):
			if not part.isdigit():
				parts[i] = part[0].upper() + part[1:]
				break
		s = ' '.join(parts)
	return s

def clean_album_name(name):
	if not name or not isinstance(name, str):
		return name
	cleaned = re.sub(r'^\s*(?:\(|)?\d{1,3}(?:\)|)?(?:\s|-|\.|:)+', '', name)
	cleaned = cleaned.strip()
	if not cleaned:
		return name.strip()
	try:
		cleaned = sanitize_string(cleaned)
	except Exception:
		pass
	try:
		return cleaned.title()
	except Exception:
		return cleaned

def sanitize_series_name(name):
	if not name:
		return None
	try:
		s = book_title_logic(name)
	except Exception:
		s = str(name)
	s = s.strip()
	if not s:
		return None
	s = re.sub(r'^[\-\._\s]+', '', s)
	s = re.sub(r'^\d{1,3}[\s\-:\._]+', '', s)
	s = re.sub(r'[-_]+', ' ', s)
	s = re.sub(r'\s{2,}', ' ', s).strip()
	try:
		s = sanitize_string(s)
	except Exception:
		pass
	try:
		s = s.title()
	except Exception:
		pass
	return s if s else None

def natural_sort_key(filename):
	parts = re.split(r'(\d+)', filename)
	return [int(part) if part.isdigit() else part.lower() for part in parts]

def track_number_sort_key(file_path, metadata_dict):
	track_number = metadata_dict.get('track_number')
	if track_number:
		if isinstance(track_number, tuple) and len(track_number) >= 1:
			return (0, track_number[0])
		elif isinstance(track_number, str):
			track_str = track_number.split('/')[0]
			try:
				return (0, int(track_str))
			except ValueError:
				pass
	filename = os.path.basename(file_path)
	return (1, natural_sort_key(filename))

def parse_series_index_from_folder_name(folder_name):
	if not folder_name or not isinstance(folder_name, str):
		return None
	s = folder_name
	# --- Written numbers mapping (up to 100+ for common cases) ---
	written_numbers = {
		'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9,
		'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
		'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
		'hundred': 100
	}
	def parse_written_number(text):
		# Handles e.g. 'twenty-one', 'one hundred', 'thirty four', etc.
		text = text.lower().replace('-', ' ')
		parts = text.split()
		total = 0
		current = 0
		for part in parts:
			if part in written_numbers:
				val = written_numbers[part]
				if val == 100:
					if current == 0:
						current = 1
					current *= 100
				else:
					current += val
			else:
				if current:
					total += current
					current = 0
		total += current
		return total if total > 0 else None

	# --- Roman numeral parser (up to 1000) ---
	roman_numerals = {
		'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000
	}
	def parse_roman(s):
		s = s.lower().strip()
		if not s or not all(c in roman_numerals for c in s):
			return None
		total = 0
		prev = 0
		for c in reversed(s):
			val = roman_numerals[c]
			if val < prev:
				total -= val
			else:
				total += val
			prev = val
		return total if total > 0 else None

	try:
		bracket_re = re.compile(r'\{([^}]*)\}|\[([^\]]*)\]|\(([^)]*)\)|<([^>]*)>')
		for m in bracket_re.finditer(s):
			inner = next((g for g in m.groups() if g), None)
			if inner:
				# Try digit
				mnum = re.search(r'(?:book|vol(?:ume)?|v)?\s*[:\.]?\s*(\d{1,3})', inner, re.IGNORECASE)
				if mnum:
					try:
						return int(mnum.group(1))
					except Exception:
						pass
				# Try roman numeral
				mroman = re.search(r'vol\.?\s*([ivxlcdm]+)', inner, re.IGNORECASE)
				if mroman:
					val = parse_roman(mroman.group(1))
					if val:
						return val
				# Try written number
				mwritten = re.search(r'(?:book|vol(?:ume)?|v)?\s*[:\.]?\s*([a-z\- ]+)', inner, re.IGNORECASE)
				if mwritten:
					val = parse_written_number(mwritten.group(1))
					if val:
						return val
		s = re.sub(r'\{[^}]*\}|\[[^\]]*\]|\([^)]*\)|<[^>]*>', ' ', s)
	except Exception:
		s = folder_name
	s = re.sub(r'[\._]', ' ', s)
	s = re.sub(r'[-]+', ' ', s)
	s = s.lower().strip()
	# Try digit patterns
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
	# Try roman numerals
	mroman = re.search(r'vol\.?\s*([ivxlcdm]+)', s, re.IGNORECASE)
	if mroman:
		val = parse_roman(mroman.group(1))
		if val:
			return val
	# Try written numbers
	mwritten = re.search(r'(?:book|vol(?:ume)?|v|part|episode|disc|volume)?\s*([a-z\- ]+)', s, re.IGNORECASE)
	if mwritten:
		text = mwritten.group(1).strip()
		# First try roman numerals
		val = parse_roman(text)
		if val:
			return val
		# Then try written numbers
		val = parse_written_number(text)
		if val:
			return val
	# Fallback: any digit
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


def discover_audiobook_folders(root_path, max_depth=5):
	"""
	Recursively scan a directory tree to find folders containing audio files.

	Args:
		root_path (str): Root directory to start scanning from
		max_depth (int): Maximum directory depth to scan

	Returns:
		list: List of dicts with folder info: {'path': str, 'type': 'series'|'novel', 'audio_files': int}
	"""
	import os
	import glob

	if not os.path.isdir(root_path):
		return []

	audio_extensions = ['*.m4a', '*.mp3', '*.m4b', '*.aac', '*.flac', '*.ogg', '*.wma']
	discovered_folders = []

	def scan_directory(current_path, current_depth=0):
		if current_depth > max_depth:
			return

		try:
			# Check if current directory has audio files directly
			audio_files = []
			for ext in audio_extensions:
				audio_files.extend(glob.glob(os.path.join(current_path, ext)))

			if audio_files:
				# This folder has audio files - determine if it's series or novel
				folder_type = detect_folder_type(current_path)
				discovered_folders.append({
					'path': current_path,
					'type': folder_type,
					'audio_files': len(audio_files),
					'audio_file_list': audio_files
				})
				return  # Don't scan subdirectories if this folder has audio files

			# No audio files in current directory, scan subdirectories
			try:
				subdirs = [d for d in os.listdir(current_path)
						  if os.path.isdir(os.path.join(current_path, d))]
			except (OSError, PermissionError):
				return

			for subdir in subdirs:
				subdir_path = os.path.join(current_path, subdir)
				scan_directory(subdir_path, current_depth + 1)

		except (OSError, PermissionError):
			pass  # Skip directories we can't access

	scan_directory(root_path, 0)
	return discovered_folders


def detect_folder_type(folder_path):
	"""
	Automatically detect if a folder is a series or novel based on its structure.

	Args:
		folder_path (str): Path to the folder to analyze

	Returns:
		str: 'series' if folder has subfolders with audio, 'novel' if audio files are direct
	"""
	import os
	import glob

	audio_extensions = ['*.m4a', '*.mp3', '*.m4b', '*.aac', '*.flac', '*.ogg', '*.wma']

	# Check if this folder has audio files directly
	direct_audio = []
	for ext in audio_extensions:
		direct_audio.extend(glob.glob(os.path.join(folder_path, ext)))

	if not direct_audio:
		return 'unknown'  # No audio files found

	# Check if there are subfolders with audio files (indicating series structure)
	try:
		subdirs = [d for d in os.listdir(folder_path)
				  if os.path.isdir(os.path.join(folder_path, d))]
	except (OSError, PermissionError):
		subdirs = []

	has_audio_subfolders = False
	for subdir in subdirs:
		subdir_path = os.path.join(folder_path, subdir)
		subdir_audio = []
		for ext in audio_extensions:
			subdir_audio.extend(glob.glob(os.path.join(subdir_path, ext)))
		if subdir_audio:
			has_audio_subfolders = True
			break

	if has_audio_subfolders:
		return 'series'  # Parent folder with child folders containing audio
	else:
		return 'novel'   # Single folder with audio files directly
