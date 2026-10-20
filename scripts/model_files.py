"""Stream public pinned files; publish only after size and SHA-256 verification."""
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request


def verify_model(item, path):
    path = Path(path)
    if path.stat().st_size != item['bytes']:
        raise ValueError('Model size differs from lock: ' + item['filename'])
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != item['sha256']:
        raise ValueError('Model SHA-256 differs from lock: ' + item['filename'])
    return dict(filename=item['filename'], bytes=path.stat().st_size,
                sha256=digest, verified=True)


def ensure_model(item, target, download=False):
    target = Path(target)
    if target.exists():
        return verify_model(item, target)
    if not download:
        raise ValueError('Missing component: ' + item['filename'])
    target.parent.mkdir(parents=True, exist_ok=True)
    url = (f"https://huggingface.co/{item['repository']}/resolve/"
           f"{item['revision']}/{item.get('path', item['filename'])}")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=target.name + '.', suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            with urllib.request.urlopen(url, timeout=90) as source:
                total = 0
                while chunk := source.read(4 * 1024 * 1024):
                    total += len(chunk)
                    if total > item['bytes']:
                        raise ValueError('Model size exceeds lock: ' + item['filename'])
                    output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        report = verify_model(item, temporary)
        temporary.replace(target)
        return report
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
