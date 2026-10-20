"""Copy the bundled example into private runtime state, without rendering."""
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    example = ROOT / "examples/greenhouse"
    board = json.loads((example / "board.json").read_text())
    destination = Path(os.environ.get("SHOTBOARD_DATA_DIR", ROOT / ".runtime/boards")) / board["id"]
    if destination.exists():
        print("Example board already present; no files changed.")
        return
    destination.mkdir(parents=True)
    for shot in board["shots"]:
        for take in shot["takes"]:
            shutil.copyfile(example / "takes" / take["image"], destination / take["image"])
    (destination / "board.json").write_text(json.dumps(board, indent=2)+"\n")
    print("Example imported. Start the app and choose Open a board.")


if __name__ == "__main__":
    main()
