"""Download exactly the committed SDXL lock without changing it."""
import argparse
import json
from pathlib import Path

if __package__:
    from .model_files import ensure_model
else:
    from model_files import ensure_model

ROOT = Path(__file__).resolve().parents[1]


def download(model_dir=None):
    lock = json.loads((ROOT / 'workflows/model-lock.json').read_text())
    target = Path(model_dir or ROOT / '.runtime/models/checkpoints') / lock['filename']
    ensure_model(lock, target, download=True)
    print('Verified ' + lock['filename'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-dir', default=None)
    download(parser.parse_args().model_dir)
