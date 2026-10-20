"""Copy the bundled example into private runtime state, without rendering."""
import argparse
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--example', default='greenhouse', choices=['greenhouse', 'greenhouse-a2', 'hangar'])
    args = parser.parse_args()
    example = ROOT / 'examples' / args.example
    board = json.loads((example / "board.json").read_text())
    review = example / "continuity-review.json"
    board["review"] = json.loads(review.read_text()) if review.exists() else []
    destination = Path(os.environ.get("SHOTBOARD_DATA_DIR", ROOT / ".runtime/boards")) / board["id"]
    if destination.exists():
        saved_path = destination / "board.json"
        saved = json.loads(saved_path.read_text())
        if "review" not in saved:
            saved["review"] = board["review"]
            saved_path.write_text(json.dumps(saved, indent=2)+"\n")
            print("Example review imported.")
            return
        print("Example board already present; no files changed.")
        return
    destination.mkdir(parents=True)
    for shot in board["shots"]:
        for take in shot["takes"]:
            if take.get("image"):
                shutil.copyfile(example / "takes" / take["image"], destination / take["image"])
    if (example / 'references').is_dir():
        shutil.copytree(example / 'references', destination / 'references')
    (destination / "board.json").write_text(json.dumps(board, indent=2)+"\n")
    print("Example imported. Start the app and choose My boards.")


if __name__ == "__main__":
    main()
