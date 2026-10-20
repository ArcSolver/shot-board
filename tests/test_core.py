from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from PIL import Image
from shotboard.core import expand_shots, seed_for, workflow_for, PRESETS, sha256, export_board
from shotboard.server import Scene


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.config = Scene(scene="A traveler finds a compass").model_dump()

    def test_deterministic_coverage_and_shared_bible(self):
        shots = expand_shots(self.config)
        self.assertEqual(shots, expand_shots(deepcopy(self.config)))
        self.assertEqual(len(shots), 6)
        self.assertEqual(len({s["prompt"] for s in shots}), 6)
        self.assertEqual(len({s["id"] for s in shots}), 6)
        for shot in shots:
            self.assertIn(self.config["character"], shot["prompt"])
            self.assertIn(self.config["setting"], shot["prompt"])
            self.assertIn("35mm", shot["prompt"])

    def test_extended_coverage_keeps_first_six(self):
        six = expand_shots(self.config)
        self.config["count"] = 9
        nine = expand_shots(self.config)
        self.assertEqual(nine[:6], six)
        self.assertEqual(len(nine), 9)

    def test_chips_change_prompt_without_losing_identity(self):
        self.config.update(lens="85", angle="High angle", move="Lateral drift", lighting="Blue hour", look="Monochrome")
        prompt = expand_shots(self.config)[1]["prompt"]
        for text in ("85mm", "high angle", "blue hour", "black and white", "lateral camera drift", self.config["character"]):
            self.assertIn(text, prompt)

    def test_seed_reuse_and_families(self):
        self.assertNotEqual(seed_for(41, 0), seed_for(41, 1))
        self.assertEqual(seed_for(41, 12, locked=0), 0)
        self.assertEqual(seed_for(41, 2, locked=97), 97)
        self.assertLess(seed_for(2**32-1, 15), 2**32)

    def test_bounds_are_rejected(self):
        for field, value in (("count", 5), ("count", 10), ("seed", -1), ("lens", "300"), ("preset", "qwen-reference")):
            with self.assertRaises(ValueError):
                Scene(**(self.config | {field:value}))


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data = Path(self.temp.name)
        config = Scene(scene="A traveler finds a compass").model_dump()
        self.board = dict(id="testboard", title="Compass", config=config, shots=expand_shots(config))
        (self.data / "testboard").mkdir()
        for shot in self.board["shots"]:
            filename = shot["id"] + ".png"
            dest = self.data / "testboard" / filename
            Image.new("RGB", (16, 9), "olive").save(dest)
            take = dict(id="t01", status="succeeded", seed=41, settings=deepcopy(PRESETS["sdxl-base"]),
                        models=[dict(filename="sd_xl_base_1.0.safetensors", sha256="a"*64)],
                        workflow=workflow_for(shot, 41, PRESETS["sdxl-base"]), image=filename,
                        image_sha256=sha256(dest), elapsed_seconds=1.25)
            shot.update(picked="t01", takes=[take])

    def test_export_has_six_stills_workflows_and_exact_provenance(self):
        data = export_board(self.board, self.data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(len(archive.namelist()), 13)
            self.assertEqual(len(manifest["shots"]), 6)
            for item in manifest["shots"]:
                graph = json.loads(archive.read(item["workflow"]))
                self.assertEqual(graph["5"]["inputs"]["seed"], item["seed"])
                self.assertEqual(graph["5"]["inputs"]["steps"], item["settings"]["steps"])
                self.assertEqual(item["models"][0]["sha256"], "a"*64)
                import hashlib
                self.assertEqual(hashlib.sha256(archive.read(item["image"])).hexdigest(), item["image_sha256"])
                self.assertEqual(hashlib.sha256(archive.read(item["workflow"])).hexdigest(), item["workflow_sha256"])

    def test_later_prompt_edits_do_not_rewrite_picked_take(self):
        shot = self.board["shots"][0]
        original = shot["prompt"]
        shot["prompt"] = "A completely different scene"
        shot["locked_seed"] = 99
        with zipfile.ZipFile(io.BytesIO(export_board(self.board, self.data))) as archive:
            item = json.loads(archive.read("manifest.json"))["shots"][0]
            self.assertEqual(item["prompt"], original)
            self.assertEqual(item["seed"], 41)

    def test_incomplete_board_cannot_export(self):
        self.board["shots"][-1]["picked"] = None
        with self.assertRaisesRegex(ValueError, "Pick one"):
            export_board(self.board, self.data)

    def test_tampered_image_cannot_export(self):
        (self.data / "testboard/s01.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed on disk"):
            export_board(self.board, self.data)


if __name__ == "__main__":
    unittest.main()
