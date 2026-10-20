"""Verify existing reference components; optionally download only the pinned Q8 diffusion weight."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download-q8', action='store_true')
    parser.add_argument('--reference-model-dir', default=os.environ.get('SHOTBOARD_REFERENCE_MODEL_DIR', '../models'))
    args = parser.parse_args()
    base = Path(args.reference_model_dir)
    qwen_dir = Path(os.environ.get('SHOTBOARD_QWEN_MODEL_DIR', ROOT / '.runtime/models/diffusion_models'))
    for item in json.loads((ROOT / 'workflows/qwen-model-lock.json').read_text()):
        dest = qwen_dir / item['filename'] if item['component'] == 'diffusion' else base / item['folder'] / item['filename']
        if not dest.is_file() and args.download_q8 and item['component'] == 'diffusion':
            dest.parent.mkdir(parents=True, exist_ok=True)
            temporary = dest.with_suffix('.gguf.part')
            url = f"https://huggingface.co/{item['repository']}/resolve/{item['revision']}/{item['filename']}"
            print('Downloading pinned public Q8_0 weight (21.76 GB). Existing models are not modified.', flush=True)
            # No login token or credential headers; stream directly to the private runtime.
            with urllib.request.urlopen(url, timeout=90) as source, temporary.open('wb') as output:
                import shutil
                shutil.copyfileobj(source, output, length=4*1024*1024)
            with temporary.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            if digest != item['sha256'] or temporary.stat().st_size != item['bytes']:
                raise SystemExit('Downloaded model hash or size differs from lock.')
            temporary.replace(dest)
        if not dest.is_file():
            raise SystemExit('Missing component: ' + item['filename'])
        with dest.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        if digest != item['sha256']:
            raise SystemExit('Model hash differs: ' + item['filename'])
        print('Verified ' + item['filename'], flush=True)


if __name__ == '__main__':
    main()
