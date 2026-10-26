"""Download or verify all four pinned Qwen reference components for one quantization."""
import argparse
import json
import os
from pathlib import Path

if __package__:
    from .model_files import ensure_model
else:
    from model_files import ensure_model

ROOT = Path(__file__).resolve().parents[1]


LOCKS = {'Q8_0': 'qwen-model-lock.json', 'Q4_K_M': 'qwen-model-lock-q4_k_m.json'}


def setup(base, qwen_dir, download=False, quant='Q8_0'):
    for item in json.loads((ROOT / 'workflows' / LOCKS[quant]).read_text()):
        dest = Path(qwen_dir) / item['filename'] if item['component'] == 'diffusion' else Path(base) / item['folder'] / item['filename']
        ensure_model(item, dest, download=download)
        print('Verified ' + item['filename'], flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', '--download-q8', action='store_true',
                        help='Download all four missing components; existing files must match the lock.')
    parser.add_argument('--reference-model-dir', default=os.environ.get('SHOTBOARD_REFERENCE_MODEL_DIR', '../models'))
    parser.add_argument('--qwen-model-dir', default=os.environ.get('SHOTBOARD_QWEN_MODEL_DIR', ROOT / '.runtime/models/diffusion_models'))
    parser.add_argument('--quant', choices=sorted(LOCKS), default=os.environ.get('SHOTBOARD_QWEN_QUANT', 'Q8_0'),
                        help='Q4_K_M needs about 20 GB for the four files instead of about 31 GB.')
    args = parser.parse_args()
    setup(args.reference_model_dir, args.qwen_model_dir, args.download, args.quant)


if __name__ == '__main__':
    main()
