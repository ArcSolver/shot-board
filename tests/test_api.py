from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from shotboard import server


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(server, "DATA", Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.store_patch = patch.object(server, "store", server.Store())
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)
        self.client = TestClient(server.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.board = self.client.post("/api/boards", json={"scene":"A traveler finds a compass"}).json()
        self.base = "/api/boards/" + self.board["id"]

    def test_create_reload_and_edit(self):
        self.assertEqual(len(self.client.get(self.base).json()["shots"]), 6)
        result = self.client.patch(self.base+"/shots/s01", json=dict(title="Opening", prompt="A quiet empty greenhouse", negative="logo"))
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get(self.base).json()["shots"][0]["title"], "Opening")
        self.assertTrue((Path(self.temp.name)/self.board["id"]/"board.json").is_file())

    def test_incomplete_export_and_pick_rejected(self):
        self.assertEqual(self.client.get(self.base+"/export").status_code, 409)
        self.assertEqual(self.client.post(self.base+"/shots/s01/pick",json={"take_id":"t01"}).status_code, 409)

    def test_examples_open_without_generation_and_preserve_user_picks(self):
        examples = self.client.get("/api/examples").json()
        self.assertEqual(examples[0]["slug"], "greenhouse-a2")
        slug = examples[0]["slug"]
        opened = self.client.post(f"/api/examples/{slug}/open").json()
        base = "/api/boards/" + opened["id"]
        board = self.client.get(base).json()
        self.assertEqual(len(board["review"]), 6)
        self.assertEqual(board["shots"][0]["picked"], "t03")
        self.client.post(base+"/shots/s01/pick", json={"take_id":"t01"})
        self.client.post(f"/api/examples/{slug}/open")
        self.assertEqual(self.client.get(base).json()["shots"][0]["picked"], "t01")
        self.assertTrue(server.store.tasks.empty())
        self.assertEqual(self.client.get(f"/api/examples/{slug}/images/missing.png").status_code, 404)
        self.assertEqual(self.client.post("/api/examples/unknown/open").status_code, 404)

    def test_storyboard_endpoint_and_download_match_zip(self):
        import io
        import json
        import zipfile
        slug = "greenhouse-a2"
        bid = self.client.post(f"/api/examples/{slug}/open").json()["id"]
        base = "/api/boards/" + bid
        for layout in ("portrait", "landscape"):
            response = self.client.get(base+f"/storyboard?layout={layout}")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/png")
            download = self.client.get(base+f"/storyboard?layout={layout}&download=true")
            self.assertEqual(response.content, download.content)
            self.assertIn("attachment", download.headers["content-disposition"])
            with zipfile.ZipFile(io.BytesIO(self.client.get(base+"/export").content)) as archive:
                self.assertEqual(response.content, archive.read(f"storyboard-{layout}.png"))
                self.assertEqual(len(json.loads(archive.read("manifest.json"))["storyboards"]), 2)
        self.assertEqual(self.client.get(base+"/storyboard?layout=square").status_code, 422)
        self.assertEqual(self.client.get(self.base+"/storyboard").status_code, 409)
        self.assertTrue(server.store.tasks.empty())

    def test_scene_input_normalizes_newlines_and_whitespace(self):
        response = self.client.post('/api/boards', json={'scene': 'A\n'*50, 'character': '  An\tadult  traveler\n'})
        self.assertEqual(response.status_code, 201)
        board = response.json()
        self.assertEqual(board['config']['scene'], ' '.join(['A']*50))
        self.assertEqual(board['title'], board['config']['scene'][:80])
        self.assertEqual(board['config']['character'], 'An adult traveler')
        self.assertEqual(self.client.post('/api/boards', json={'scene':' \n\t '}).status_code, 422)

    def test_export_succeeds_when_storyboards_fail(self):
        import io, json, zipfile
        bid = self.client.post('/api/examples/greenhouse-a2/open').json()['id']
        with patch('shotboard.core.storyboard_png', side_effect=ValueError('private renderer detail')):
            response = self.client.get('/api/boards/'+bid+'/export')
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(len(manifest['storyboard_errors']), 2)
            self.assertEqual(manifest['storyboards'], [])
            self.assertEqual(len(manifest['shots']), 6)
            self.assertNotIn('private renderer detail', archive.read('manifest.json').decode())
            for shot in manifest['shots']:
                self.assertIn(shot['image'], archive.namelist())
                self.assertIn(shot['workflow'], archive.namelist())

    def test_seed_zero_and_unlock(self):
        self.client.post(self.base+"/shots/s01/seed",json={"seed":0})
        self.assertEqual(self.client.get(self.base).json()["shots"][0]["locked_seed"], 0)
        self.client.post(self.base+"/shots/s01/seed",json={"seed":None})
        self.assertIsNone(self.client.get(self.base).json()["shots"][0]["locked_seed"])

    def test_removed_route_and_config(self):
        self.assertEqual(self.client.post(self.base+"/shots/s01/reframe").status_code, 404)
        self.assertNotIn("reframe", self.client.get("/api/config").json())
        self.assertTrue(server.store.tasks.empty())

    def test_invalid_shot_and_cross_origin(self):
        self.assertEqual(self.client.post(self.base+"/shots/missing/seed",json={"seed":1}).status_code, 404)
        self.assertEqual(self.client.post("/api/boards", headers={"Origin":"https://example.org"},json={"scene":"Another scene"}).status_code, 403)
        self.assertEqual(self.client.get("/api/boards",headers={"Host":"example.org"}).status_code, 403)

    def test_missing_model_and_invalid_generation_are_rejected(self):
        with patch.object(server, "MODEL_DIR", Path(self.temp.name)/"missing"):
            self.assertEqual(self.client.post(self.base+"/generate",json={"takes":2}).status_code,409)
        self.assertEqual(self.client.post(self.base+"/generate",json={"takes":99}).status_code,422)

    def test_reload_marks_unfinished_jobs_interrupted(self):
        board = server.store.boards[self.board["id"]]
        board["shots"][0]["takes"] = [dict(id="t01",status="queued"),dict(id="t02",status="running")]
        server.store.save(board)
        restored = server.Store()
        restored.start()
        restored.stop.set()
        restored.thread.join(timeout=2)
        statuses = [t["status"] for t in restored.boards[board["id"]]["shots"][0]["takes"]]
        self.assertEqual(statuses, ["interrupted","interrupted"])


if __name__ == "__main__":
    unittest.main()
