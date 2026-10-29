"""Download or verify the four pinned Qwen reference components, and Qwen-Image-2512 on request."""
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
IMAGE_LOCKS = {'Q8_0': 'qwen-image-model-lock.json', 'Q4_K_M': 'qwen-image-model-lock-q4_k_m.json'}


def setup(base, qwen_dir, download=False, quant='Q8_0', first_takes=False):
    items = json.loads((ROOT / 'workflows' / LOCKS[quant]).read_text())
    if first_takes:
        items += json.loads((ROOT / 'workflows' / IMAGE_LOCKS[quant]).read_text())
    for item in items:
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
    parser.add_argument('--first-takes', action='store_true',
                        help='Also get Qwen-Image-2512 for first takes; it shares the encoder and VAE.')
    args = parser.parse_args()
    setup(args.reference_model_dir, args.qwen_model_dir, args.download, args.quant, args.first_takes)


if __name__ == '__main__':
    main()
