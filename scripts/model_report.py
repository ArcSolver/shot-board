"""Hash worker files against both locks and emit a private verification report."""
import argparse
import json
import os
from pathlib import Path

if __package__:
    from .model_files import verify_model
else:
    from model_files import verify_model

ROOT = Path(__file__).resolve().parents[1]


LOCKS = {'Q8_0': 'qwen-model-lock.json', 'Q4_K_M': 'qwen-model-lock-q4_k_m.json'}
IMAGE_LOCKS = {'Q8_0': 'qwen-image-model-lock.json', 'Q4_K_M': 'qwen-image-model-lock-q4_k_m.json'}


def report(models_dir, quant='Q8_0', first_takes=False):
    sdxl = json.loads((ROOT / 'workflows/model-lock.json').read_text())
    qwen = json.loads((ROOT / 'workflows' / LOCKS[quant]).read_text())
    if first_takes:
        qwen += json.loads((ROOT / 'workflows' / IMAGE_LOCKS[quant]).read_text())
    return dict(schema_version=1, verified=True, models=[
        verify_model(item, Path(models_dir) / item.get('folder', 'checkpoints') / item['filename'])
        for item in [sdxl, *qwen]])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--models-dir', required=True)
    parser.add_argument('--quant', choices=sorted(LOCKS), default=os.environ.get('SHOTBOARD_QWEN_QUANT', 'Q8_0'))
    parser.add_argument('--first-takes', action='store_true', help='Also measure Qwen-Image-2512.')
    args = parser.parse_args()
    print(json.dumps(report(args.models_dir, args.quant, args.first_takes), indent=2))
