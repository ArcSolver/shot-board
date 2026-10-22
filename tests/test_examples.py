"""Bundled examples must match their recorded hashes and the current storyboard renderer."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from shotboard.core import ROOT
from shotboard.storyboard import storyboard_png

EXAMPLES = ROOT / "examples"


def read(folder, name):
    if "!" in name:
        archive, member = name.split("!", 1)
        with zipfile.ZipFile(folder / archive) as z:
            return z.read(member)
    return (folder / name).read_bytes()


class ExampleTests(unittest.TestCase):
    def test_provenance_hashes_match_files_and_zip_members(self):
        for path in sorted(EXAMPLES.glob("*/provenance.json")):
            for item in json.loads(path.read_text())["images"]:
                with self.subTest(example=path.parent.name, file=item["file"]):
                    self.assertEqual(hashlib.sha256(read(path.parent, item["file"])).hexdigest(), item["sha256"])

    def test_storyboards_and_export_copies_match_the_renderer(self):
        for folder in sorted(p.parent for p in EXAMPLES.glob("*/board.json")):
            board = json.loads((folder / "board.json").read_text())
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / board["id"]).symlink_to((folder / "takes").resolve())
                for layout in ("landscape", "portrait"):
                    name = f"storyboard-{layout}.png"
                    with self.subTest(example=folder.name, layout=layout):
                        expected = storyboard_png(board, tmp, layout)
                        self.assertEqual(read(folder, name), expected)
                        self.assertEqual(read(folder, f"export/{name}"), expected)
                        self.assertEqual(read(folder, f"selects.zip!{name}"), expected)
                        manifest = json.loads(read(folder, "selects.zip!manifest.json"))
                        self.assertIn(hashlib.sha256(expected).hexdigest(), [s["sha256"] for s in manifest["storyboards"]])
                        self.assertEqual(read(folder, "export/manifest.json"), read(folder, "selects.zip!manifest.json"))


if __name__ == "__main__":
    unittest.main()
