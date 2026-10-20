"""Explicit SDXL lock maintenance; never called by the downloader."""
import argparse
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def update(revision):
    if not re.fullmatch('[0-9a-f]{40}', revision):
        raise ValueError('Supply a full immutable revision')
    path = ROOT / 'workflows/model-lock.json'
    lock = json.loads(path.read_text())
    url = f"https://huggingface.co/api/models/{lock['repository']}/revision/{revision}?blobs=true"
    with urllib.request.urlopen(url, timeout=90) as response:
        info = json.load(response)
    if info['sha'] != revision:
        raise ValueError('Repository revision differs')
    file = next(item for item in info['siblings'] if item['rfilename'] == lock['filename'])
    digest, size = file['lfs']['sha256'], file['lfs']['size']
    if not re.fullmatch('[0-9a-f]{64}', digest) or not isinstance(size, int) or size <= 0:
        raise ValueError('Invalid upstream file metadata')
    lock.update(revision=revision, sha256=digest, bytes=size)
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(lock, indent=2) + '\n')
    temporary.replace(path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update-lock', action='store_true', required=True)
    parser.add_argument('--revision', required=True)
    update(parser.parse_args().revision)
