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
        self.config = Scene(scene="A technician repairs an engine", character="a technician in silver gloves",
                            setting="an orbital workshop", prop="a pressure gauge").model_dump()

    def test_new_scene_has_no_example_defaults(self):
        for extras in ({}, dict(character="", setting="", prop=""),
                       dict(character=" \t ", setting="\n", prop=" ")):
            config = Scene(scene="A robot repairs a spaceship engine.", **extras).model_dump()
            for key in ("character", "setting", "prop"):
                self.assertEqual(config[key], "")
            for shot in expand_shots(config):
                self.assertIn(config["scene"].rstrip("."), shot["prompt"])
                for token in ("traveler", "greenhouse", "compass", "raincoat", "Character:", "Set:", "Key prop:"):
                    self.assertNotIn(token.lower(), shot["prompt"].lower())

    def test_each_optional_extra_is_used_only_when_supplied(self):
        for key, value, label in (("character", "a robot", "Character"), ("setting", "a spaceship", "Set"),
                                  ("prop", "a wrench", "Key prop")):
            config = Scene(scene="Repairs begin", **{key: value}).model_dump()
            for shot in expand_shots(config):
                self.assertIn(f"{label}: {value}", shot["prompt"])

    def test_prompt_assembly_has_no_empty_or_doubled_separators(self):
        for ending in ("", ".", ",", ";"):
            config = Scene(scene="A traveler discovers a compass in a greenhouse" + ending,
                           character="a traveler.", setting="a greenhouse,", prop="a compass;").model_dump()
            config["count"] = 9
            for shot in expand_shots(config):
                with self.subTest(ending=ending, title=shot["title"]):
                    self.assertNotRegex(shot["prompt"], r"[.,;]\s*,|,\s*,|\.\s*\.")
                    self.assertIn("Character: a traveler. Set: a greenhouse. Key prop: a compass, 35mm lens", shot["prompt"])
                    if shot["title"] in ("Medium", "Profile", "Three-quarter"):
                        self.assertIn(", eye level, ", shot["prompt"])
                    else:
                        self.assertNotIn("eye level", shot["prompt"])

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

    def test_scene_with_a_person_keeps_the_face_and_shoulder_cuts(self):
        person = ["Establishing", "Medium", "Close-up", "Over shoulder", "Insert", "Low angle"]
        for extras in (dict(scene="She reads a letter by the window."),
                       dict(scene="A traveler finds a compass."),
                       dict(scene="Rain on a quiet street.", character="a courier in a red coat")):
            with self.subTest(**extras):
                shots = expand_shots(Scene(**extras).model_dump())
                self.assertEqual([s["title"] for s in shots], person)
                self.assertIn("face", shots[2]["direction"])

    def test_scene_without_a_person_drops_faces_hands_and_shoulders(self):
        config = Scene(scene="A lighthouse in a winter storm.", prop="a cracked lamp lens").model_dump()
        shots = expand_shots(config)
        self.assertEqual([s["title"] for s in shots],
                         ["Establishing", "Medium", "Detail", "Side angle", "Insert", "Low angle"])
        self.assertEqual(len({s["prompt"] for s in shots}), 6)
        for shot in shots:
            for word in ("face", "hands", "fingers", "shoulder", "figure", "portrait"):
                self.assertNotRegex(shot["direction"], rf"\b{word}\b")
            self.assertIn("person, people", shot["negative"])
            self.assertIn(config["scene"].rstrip("."), shot["prompt"])
        config["count"] = 9
        nine = expand_shots(config)
        self.assertEqual(nine[:6], shots)
        self.assertNotRegex(" ".join(s["direction"] for s in nine), r"\bface\b")

    def test_person_words_match_whole_words_only(self):
        for scene in ("A manhole cover steams at night.", "Here the old herbarium sits empty."):
            with self.subTest(scene=scene):
                self.assertEqual(expand_shots(Scene(scene=scene).model_dump())[2]["title"], "Detail")

    def test_config_lists_both_coverage_templates(self):
        from shotboard import server
        coverage = server.config()["coverage"]
        self.assertEqual(coverage["person"][2:4], ["Close-up", "Over shoulder"])
        self.assertEqual(coverage["object"][2:4], ["Detail", "Side angle"])
        self.assertIn("traveler", coverage["person_words"])

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
            self.assertEqual(len(archive.namelist()), 15)
            self.assertEqual(len(manifest["shots"]), 6)
            for item in manifest["shots"]:
                graph = json.loads(archive.read(item["workflow"]))
                self.assertEqual(graph["5"]["inputs"]["seed"], item["seed"])
                self.assertEqual(graph["5"]["inputs"]["steps"], item["settings"]["steps"])
                self.assertEqual(item["models"][0]["sha256"], "a"*64)
                import hashlib
                self.assertEqual(hashlib.sha256(archive.read(item["image"])).hexdigest(), item["image_sha256"])
                self.assertEqual(hashlib.sha256(archive.read(item["workflow"])).hexdigest(), item["workflow_sha256"])

    def test_storyboards_are_deterministic_and_match_manifest(self):
        import hashlib
        from shotboard.storyboard import storyboard_png, SIZES
        with zipfile.ZipFile(io.BytesIO(export_board(self.board, self.data))) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(len(manifest["storyboards"]), 2)
            for item in manifest["storyboards"]:
                layout = "portrait" if item["width"] == 1080 else "landscape"
                first = storyboard_png(self.board, self.data, layout)
                self.assertEqual(first, storyboard_png(self.board, self.data, layout))
                self.assertEqual(first, archive.read(item["file"]))
                self.assertEqual(hashlib.sha256(first).hexdigest(), item["sha256"])
                self.assertEqual(len(item["selections"]), 6)
                with Image.open(io.BytesIO(first)) as image:
                    self.assertEqual(image.size, SIZES[layout])
                    self.assertEqual(image.info, {})

    def test_storyboard_depends_on_picks_and_rejects_tampering(self):
        from shotboard.storyboard import storyboard_png
        original = storyboard_png(self.board, self.data)
        shot = self.board["shots"][0]
        alternate = deepcopy(shot["takes"][0])
        path = self.data / "testboard/alternate.png"
        Image.new("RGB", (9, 16), "blue").save(path)
        alternate.update(id="t02", image=path.name, image_sha256=sha256(path))
        shot["takes"].append(alternate)
        shot["picked"] = "t02"
        self.assertNotEqual(original, storyboard_png(self.board, self.data))
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "changed on disk"):
            storyboard_png(self.board, self.data)

    def test_storyboard_contains_portrait_without_cropping(self):
        from shotboard.storyboard import storyboard_png
        path = self.data / "testboard/s01.png"
        image = Image.new("RGB", (20, 100), "red")
        image.paste("blue", (0, 0, 20, 10))
        image.paste((0, 255, 0), (0, 90, 20, 100))
        image.save(path)
        self.board["shots"][0]["takes"][0]["image_sha256"] = sha256(path)
        with Image.open(io.BytesIO(storyboard_png(self.board, self.data))) as result:
            colors = result.getcolors(result.width*result.height)
            for color in [(255,0,0), (0,0,255), (0,255,0)]:
                self.assertTrue(any(rgb == color and count > 20 for count, rgb in colors))

    def test_valid_multiline_and_max_length_scenes_render_both_layouts(self):
        from shotboard.storyboard import storyboard_png, SIZES
        for scene in ('A\n'*50, 'W'*600, ('wide scene \n\t'*60)[:600], '界'*600):
            for count in (6, 9):
                with self.subTest(scene=scene[:20], count=count):
                    self.board['config'].update(scene=scene, count=count)
                    self.board['shots'] = (self.board['shots'][:6] + deepcopy(self.board['shots'][:3]))[:count]
                    for i, shot in enumerate(self.board['shots']): shot['id'] = f's{i+1:02}'
                    for layout, size in SIZES.items():
                        with Image.open(io.BytesIO(storyboard_png(self.board, self.data, layout))) as image:
                            self.assertEqual(image.size, size)
        with zipfile.ZipFile(io.BytesIO(export_board(self.board, self.data))) as archive:
            self.assertEqual(len(json.loads(archive.read('manifest.json'))['storyboards']), 2)

    def test_one_failed_layout_does_not_block_other_storyboard_or_recipes(self):
        from unittest.mock import patch
        from shotboard.storyboard import storyboard_png
        def render(board, data, layout):
            if layout == 'landscape': raise OSError('private detail')
            return storyboard_png(board, data, layout)
        with patch('shotboard.core.storyboard_png', side_effect=render):
            payload = export_board(self.board, self.data)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['shots']), 6)
            self.assertEqual([s['file'] for s in manifest['storyboards']], ['storyboard-portrait.png'])
            self.assertEqual(manifest['storyboard_errors'][0]['layout'], 'landscape')
            self.assertEqual(manifest['storyboard_errors'][0]['error'], 'OSError')
            self.assertNotIn('private detail', archive.read('manifest.json').decode())

    def test_later_prompt_edits_do_not_rewrite_picked_take(self):
        shot = self.board["shots"][0]
        original = shot["prompt"]
        shot["prompt"] = "A completely different scene"
        shot["locked_seed"] = 99
        with zipfile.ZipFile(io.BytesIO(export_board(self.board, self.data))) as archive:
            item = json.loads(archive.read("manifest.json"))["shots"][0]
            self.assertEqual(item["prompt"], original)
            self.assertEqual(item["seed"], 41)
            # A lock on another take's seed does not make the pick's seed locked.
            self.assertFalse(item["seed_locked"])
        shot["locked_seed"] = 41
        with zipfile.ZipFile(io.BytesIO(export_board(self.board, self.data))) as archive:
            self.assertTrue(json.loads(archive.read("manifest.json"))["shots"][0]["seed_locked"])

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
