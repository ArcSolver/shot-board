"""Download or verify all four pinned Qwen reference components."""
import argparse
import json
import os
from pathlib import Path

if __package__:
    from .model_files import ensure_model
else:
    from model_files import ensure_model

ROOT = Path(__file__).resolve().parents[1]


def setup(base, qwen_dir, download=False):
    for item in json.loads((ROOT / 'workflows/qwen-model-lock.json').read_text()):
        dest = Path(qwen_dir) / item['filename'] if item['component'] == 'diffusion' else Path(base) / item['folder'] / item['filename']
        ensure_model(item, dest, download=download)
        print('Verified ' + item['filename'], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', '--download-q8', action='store_true',
                        help='Download all four missing components; existing files must match the lock.')
    parser.add_argument('--reference-model-dir', default=os.environ.get('SHOTBOARD_REFERENCE_MODEL_DIR', '../models'))
    parser.add_argument('--qwen-model-dir', default=os.environ.get('SHOTBOARD_QWEN_MODEL_DIR', ROOT / '.runtime/models/diffusion_models'))
    args = parser.parse_args()
    setup(args.reference_model_dir, args.qwen_model_dir, args.download)


if __name__ == '__main__':
    main()
