"""Hash worker files against both locks and emit a private verification report."""
import argparse
import json
from pathlib import Path

if __package__:
    from .model_files import verify_model
else:
    from model_files import verify_model

ROOT = Path(__file__).resolve().parents[1]


def report(models_dir):
    sdxl = json.loads((ROOT / 'workflows/model-lock.json').read_text())
    qwen = json.loads((ROOT / 'workflows/qwen-model-lock.json').read_text())
    return dict(schema_version=1, verified=True, models=[
        verify_model(item, Path(models_dir) / item.get('folder', 'checkpoints') / item['filename'])
        for item in [sdxl, *qwen]])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--models-dir', required=True)
    args = parser.parse_args()
    print(json.dumps(report(args.models_dir), indent=2))
