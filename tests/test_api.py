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
