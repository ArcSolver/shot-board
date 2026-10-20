"""Download the pinned public SDXL checkpoint; never use account credentials."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "stabilityai/stable-diffusion-xl-base-1.0"
FILENAME = "sd_xl_base_1.0.safetensors"


def download():
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{REPO}?blobs=true") as response:
        info = json.load(response)
    file = next(x for x in info["siblings"] if x["rfilename"] == FILENAME)
    expected = file["lfs"]["sha256"]
    revision = info["sha"]
    target = ROOT / ".runtime/models/checkpoints" / FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        partial = target.with_suffix(".partial")
        with urllib.request.urlopen(f"https://huggingface.co/{REPO}/resolve/{revision}/{FILENAME}") as source, partial.open("wb") as out:
            while chunk := source.read(8 * 1024 * 1024):
                out.write(chunk)
        partial.rename(target)
    digest = hashlib.file_digest(target.open("rb"), "sha256").hexdigest()
    if digest != expected:
        raise RuntimeError("Checkpoint SHA-256 mismatch; remove the invalid local download before retrying")
    record = dict(repository=REPO, revision=revision, filename=FILENAME, sha256=digest,
                  bytes=target.stat().st_size, license="CreativeML Open RAIL++-M")
    (ROOT / "workflows/model-lock.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    download()
