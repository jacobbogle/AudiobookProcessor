import pytest
import subprocess
import tempfile
import os

def run_cli(mode, **kwargs):
    input_value = kwargs.pop('input', None)
    args = ["python", "-m", "audiobook_p.cli", "--mode", mode]
    for k, v in kwargs.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k.replace('_', '-')}")
        elif v is not None:
            args.extend([f"--{k.replace('_', '-')}", str(v)])
    if input_value is not None:
        args.append(str(input_value))
    return subprocess.run(args, capture_output=True, text=True)

    result2 = run_cli("mutate-convert", input=valid_audio_dir, output=os.path.join(valid_audio_dir, "out2.m4b"), album_sort_prefix="Prefix", author_fix=True)
    assert result2.returncode == 0
    result3 = run_cli("mutate-convert", input=valid_audio_dir, output=os.path.join(valid_audio_dir, "out3.m4b"), part_titles=True, narrator_name="Narrator")
    assert result3.returncode == 0
    result4 = run_cli("mutate-convert", input=valid_audio_dir, output=os.path.join(valid_audio_dir, "out4.m4b"), album_sort_prefix="Prefix", author_fix=True, part_titles=True, narrator_name="Narrator", author_name="Author")
    assert result4.returncode == 0
