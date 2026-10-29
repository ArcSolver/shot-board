from pathlib import Path
from copy import deepcopy
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from PIL import Image
from shotboard import server
from shotboard.core import PRESETS, sha256, workflow_for


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

    def test_scene_defaults_do_not_add_example_content(self):
        board = self.client.post('/api/boards', json={'scene': 'A robot repairs a spaceship engine.'}).json()
        self.assertEqual([board['config'][key] for key in ('character', 'prop', 'setting')], ['', '', ''])
        for shot in board['shots']:
            for token in ('traveler', 'greenhouse', 'compass', 'raincoat'):
                self.assertNotIn(token, shot['prompt'].lower())

    def test_board_title_truncation(self):
        scenes = [
            ('A traveler finds a compass', 'A traveler finds a compass'),
            ('x' * 80, 'x' * 80),
            ('A ' * 37 + 'compass appears', ('A ' * 37).rstrip() + '…'),
            ('A ' * 39 + 'x remains', 'A ' * 39 + 'x…'),
            ('x' * 81, 'x' * 79 + '…'),
        ]
        for scene, title in scenes:
            with self.subTest(scene=scene):
                board = self.client.post('/api/boards', json={'scene': scene}).json()
                self.assertEqual(board['title'], title)
                self.assertLessEqual(len(board['title']), 80)
                self.assertEqual(board['config']['scene'], scene)
                self.assertEqual(self.client.get('/api/boards/' + board['id']).json()['title'], title)
                saved = json.loads((Path(self.temp.name)/board['id']/'board.json').read_text())
                self.assertEqual(saved['title'], title)

    def add_completed_takes(self):
        board = server.store.boards[self.board['id']]
        for shot in board['shots']:
            shot['takes'] = []
            for tid, color in (('t01', 'olive'), ('t02', 'blue')):
                image = Path(self.temp.name) / board['id'] / f"{shot['id']}-{tid}.png"
                Image.new('RGB', (16, 9), color).save(image)
                shot['takes'].append(dict(id=tid, status='succeeded', seed=41,
                    settings=deepcopy(PRESETS['sdxl-base']), models=[], elapsed_seconds=0,
                    workflow=workflow_for(shot, 41, PRESETS['sdxl-base']),
                    image=image.name, image_sha256=sha256(image)))
            shot['picked'] = 't01'
        server.store.save(board)

    def test_manual_reviews_survive_picks_restart_and_export(self):
        self.add_completed_takes()
        path = self.base + '/shots/s01/takes/'
        for tid, verdict, note in (('t01', 'pass', 'Clear framing'), ('t02', 'fail', 'Too tight')):
            response = self.client.put(path + tid + '/review', json=dict(verdict=verdict, note=note))
            self.assertEqual(response.status_code, 200)
        for tid, verdict in (('t02', 'fail'), ('t01', 'pass')):
            self.assertEqual(self.client.post(self.base+'/shots/s01/pick', json={'take_id':tid}).status_code, 200)
            board = self.client.get(self.base).json()
            selected = next(r for r in board['review'] if r['shot']=='s01' and r['take']==board['shots'][0]['picked'])
            self.assertEqual(selected['verdict'], verdict)
        # Identical take IDs in other shots must not overwrite this shot's review.
        self.client.put(self.base+'/shots/s02/takes/t01/review', json={'verdict':'pending', 'note':'Check set'})
        response = self.client.put(path+'t02/review', json={'verdict':'pending', 'note':''})
        self.assertEqual(response.status_code, 200)
        board = self.client.get(self.base).json()
        self.assertEqual(len(board['review']), 3)
        with zipfile.ZipFile(io.BytesIO(self.client.get(self.base+'/export').content)) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['review'], board['review'])
            self.assertEqual(manifest['shots'][0]['review']['verdict'], 'pass')
            self.assertEqual(manifest['shots'][0]['review']['note'], 'Clear framing')
            self.assertEqual(manifest['shots'][2]['review']['verdict'], 'pending')
        restored = server.Store()
        restored.start()
        restored.stop.set()
        restored.thread.join(timeout=2)
        with patch.object(server, 'store', restored):
            self.assertEqual(self.client.get(self.base).json()['review'], board['review'])

    def test_review_validation_and_missing_targets(self):
        self.add_completed_takes()
        path = self.base+'/shots/s01/takes/t01/review'
        for body in ({'verdict':'unknown'}, {'verdict':'pass', 'note':'x'*401}, {'note':'No verdict'}):
            self.assertEqual(self.client.put(path, json=body).status_code, 422)
        for path in (self.base+'/shots/s01/takes/missing/review',
                     self.base+'/shots/missing/takes/t01/review',
                     '/api/boards/missing/shots/s01/takes/t01/review'):
            self.assertEqual(self.client.put(path, json={'verdict':'pass'}).status_code, 404)

    def test_cli_import_matches_explore_and_preserves_edits(self):
        for slug in server.EXAMPLES:
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as folder:
                command = [sys.executable, str(server.ROOT/'scripts/import_example.py'), '--example', slug]
                env = dict(os.environ, SHOTBOARD_DATA_DIR=folder)
                subprocess.run(command, env=env, check=True, capture_output=True)
                bid = self.client.post(f'/api/examples/{slug}/open').json()['id']
                explored = self.client.get('/api/boards/'+bid).json()
                path = Path(folder)/bid/'board.json'
                imported = json.loads(path.read_text())
                self.assertEqual(imported, explored)
                for shot in imported['shots']:
                    for take in shot['takes']:
                        if take.get('image'):
                            self.assertEqual(sha256(Path(folder)/bid/take['image']), take['image_sha256'])
                        else:
                            self.assertIn(take['status'], ('failed', 'cancelled'))
                # Backfill only a missing review on an older import, preserving picks.
                imported.pop('review')
                imported['shots'][0]['picked'] = 't01'
                path.write_text(json.dumps(imported))
                server.store.boards[bid] = deepcopy(imported)
                subprocess.run(command, env=env, check=True, capture_output=True)
                self.client.post(f'/api/examples/{slug}/open')
                imported = json.loads(path.read_text())
                self.assertEqual(imported, self.client.get('/api/boards/'+bid).json())
                self.assertEqual(imported, json.loads((server.DATA/bid/'board.json').read_text()))
                imported['review'] = [{'shot':'s01', 'take':'t01', 'verdict':'fail', 'note':'Keep this'}]
                path.write_text(json.dumps(imported))
                subprocess.run(command, env=env, check=True, capture_output=True)
                self.assertEqual(json.loads(path.read_text()), imported)

    def test_manual_review_preserves_bundled_observations(self):
        bid = self.client.post('/api/examples/greenhouse-continuity/open').json()['id']
        base = '/api/boards/'+bid
        board = self.client.get(base).json()
        original = deepcopy(board['review'][0])
        config = deepcopy(board['config'])
        self.client.put(base+f"/shots/{original['shot']}/takes/{original['take']}/review",
                        json={'verdict':'fail', 'note':'Recheck framing'})
        self.client.post('/api/examples/greenhouse-continuity/open')
        board = self.client.get(base).json()
        self.assertEqual(board['config'], config)
        review = board['review'][0]
        self.assertEqual(review, original | dict(verdict='fail', note='Recheck framing'))

    def test_incomplete_export_and_pick_rejected(self):
        self.assertEqual(self.client.get(self.base+"/export").status_code, 409)
        self.assertEqual(self.client.post(self.base+"/shots/s01/pick",json={"take_id":"t01"}).status_code, 409)

    def test_examples_open_without_generation_and_preserve_user_picks(self):
        examples = self.client.get("/api/examples").json()
        self.assertEqual(examples[0]["slug"], "greenhouse-continuity")
        slug = examples[0]["slug"]
        opened = self.client.post(f"/api/examples/{slug}/open").json()
        base = "/api/boards/" + opened["id"]
        board = self.client.get(base).json()
        self.assertEqual(board["review"], server.example_board(slug)["review"])
        self.assertEqual(board["shots"][0]["picked"], server.example_board(slug)["shots"][0]["picked"])
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
        slug = "greenhouse-continuity"
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
        self.assertEqual(board['title'], ' '.join(['A']*40) + '…')
        self.assertEqual(board['config']['character'], 'An adult traveler')
        self.assertEqual(self.client.post('/api/boards', json={'scene':' \n\t '}).status_code, 422)

    def test_export_succeeds_when_storyboards_fail(self):
        import io, json, zipfile
        bid = self.client.post('/api/examples/greenhouse-continuity/open').json()['id']
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
                if (shot.get('source') or {}).get('type') == 'imported':
                    self.assertIsNone(shot['workflow'])
                    self.assertIsNone(shot['seed'])
                    self.assertEqual(shot['models'], [])
                    self.assertNotIn('workflows/'+shot['id']+'.api.json', archive.namelist())
                else:
                    self.assertIn(shot['workflow'], archive.namelist())

    def test_seed_zero_and_unlock(self):
        self.client.post(self.base+"/shots/s01/seed",json={"seed":0})
        self.assertEqual(self.client.get(self.base).json()["shots"][0]["locked_seed"], 0)
        self.client.post(self.base+"/shots/s01/seed",json={"seed":None})
        self.assertIsNone(self.client.get(self.base).json()["shots"][0]["locked_seed"])

    def test_board_list_rows_say_what_each_board_is(self):
        rows = self.client.get("/api/boards").json()
        self.assertEqual(rows, [dict(id=self.board["id"], title="A traveler finds a compass", cuts=6, picked=0)])
        long = self.client.post("/api/boards", json={"scene": "A " * 39 + "x remains"}).json()
        self.assertEqual(self.client.get("/api/boards").json()[0]["title"], long["title"], "Titles already cut short keep one ellipsis")
        board = server.store.boards[self.board["id"]]
        board["title"] = "A traveler"
        self.assertEqual(server.board_row(board)["title"], "A traveler…", "A shortened title says so")

    def test_config_lists_every_cut_the_composer_offers(self):
        coverage = self.client.get("/api/config").json()["coverage"]
        self.assertEqual(len(coverage["person"]), 9)
        self.assertEqual(coverage["person"][6:], ["Profile", "High angle", "Closing"])
        self.assertEqual(coverage["object"][6], "Three-quarter")

    def test_removed_route_and_config(self):
        self.assertEqual(self.client.post(self.base+"/shots/s01/reframe").status_code, 404)
        self.assertNotIn("reframe", self.client.get("/api/config").json())
        self.assertTrue(server.store.tasks.empty())

    def test_invalid_shot_and_cross_origin(self):
        self.assertEqual(self.client.post(self.base+"/shots/missing/seed",json={"seed":1}).status_code, 404)
        self.assertEqual(self.client.post("/api/boards", headers={"Origin":"https://example.org"},json={"scene":"Another scene"}).status_code, 403)
        self.assertEqual(self.client.get("/api/boards",headers={"Host":"example.org"}).status_code, 403)

    def test_a_qwen_image_board_renders_first_takes_with_qwen_image(self):
        board = self.client.post('/api/boards', json={'scene': 'A traveler finds a compass', 'preset': 'qwen-image'}).json()
        self.assertEqual(board['config']['preset'], 'qwen-image')
        server.store.stop.set()
        with patch.object(server, 'verify_models', return_value=[]) as verify:
            response = self.client.post(f"/api/boards/{board['id']}/generate", json={'takes': 1, 'shot_id': 's02'})
        self.assertEqual(response.status_code, 202, response.text)
        verify.assert_called_once_with('qwen-image')
        take = server.store.boards[board['id']]['shots'][1]['takes'][0]
        self.assertEqual(take['settings']['preset_id'], 'qwen-image')
        self.assertEqual(take['workflow']['8']['inputs']['unet_name'], 'qwen-image-2512-Q8_0.gguf')
        self.assertEqual(self.client.post('/api/boards', json={'scene': 'A compass', 'preset': 'qwen-reference'}).status_code, 422)

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
