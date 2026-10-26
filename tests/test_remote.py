import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from shotboard import server
from shotboard.core import ROOT
from shotboard.memory import MemoryGuard

class RemoteEngineTests(unittest.TestCase):
    def test_remote_report_requires_every_pinned_hash_and_size(self):
        lock=json.loads((ROOT/'workflows/qwen-model-lock.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'models.json'
            report=dict(schema_version=1,verified=True,models=[dict(m,verified=True) for m in lock])
            path.write_text(json.dumps(report))
            with patch.object(server,'ENGINE_MANIFEST',str(path)):
                self.assertEqual(server.verify_models('qwen-reference'),lock)
                for mutation in ('hash','size','missing','unverified'):
                    changed=json.loads(json.dumps(report))
                    if mutation=='hash': changed['models'][0]['sha256']='0'*64
                    elif mutation=='size': changed['models'][0]['bytes']=0
                    elif mutation=='missing': changed['models'].pop()
                    else: changed['verified']=False
                    path.write_text(json.dumps(changed))
                    with self.assertRaises(ValueError): server.verify_models('qwen-reference')
                path.unlink()
                with self.assertRaises(ValueError): server.verify_models('qwen-reference')

    def test_engine_control_uses_tunnel_and_rejects_external_hosts(self):
        with patch.dict('os.environ',{'COMFY_ENGINE_URL':'http://127.0.0.1:18188'}):
            guard=MemoryGuard()
            with patch('shotboard.memory.httpx.Client') as client:
                guard.prepare('sdxl-base')
                self.assertEqual(client.return_value.__enter__.return_value.post.call_args.args[0],'http://127.0.0.1:18188/free')
        with patch.dict('os.environ',{'COMFY_ENGINE_URL':'https://example.org'}):
            with self.assertRaises(ValueError): MemoryGuard()

    def test_sdxl_report_requires_size_even_when_hash_matches(self):
        lock = json.loads((ROOT/'workflows/model-lock.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'models.json'
            report = dict(schema_version=1, verified=True, models=[dict(lock, verified=True)])
            with patch.object(server, 'ENGINE_MANIFEST', str(path)):
                path.write_text(json.dumps(report))
                self.assertEqual(server.verify_models('sdxl-base')[0]['bytes'], lock['bytes'])
                for value in (None, 0, lock['bytes']-1):
                    changed = json.loads(json.dumps(report))
                    if value is None: changed['models'][0].pop('bytes')
                    else: changed['models'][0]['bytes'] = value
                    path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError, 'size differs'):
                        server.verify_models('sdxl-base')


class QwenQuantTests(unittest.TestCase):
    def preset(self, quant):
        code = "import json;from shotboard.core import PRESETS,QWEN_LOCK;p=PRESETS['qwen-reference'];print(json.dumps([p['unet'],p['encoder'],QWEN_LOCK.name]))"
        env = {"PATH": "/usr/bin:/bin", "SHOTBOARD_QWEN_QUANT": quant}
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True)

    def test_q4_k_m_lock_pins_the_same_repositories_with_smaller_files(self):
        q8 = json.loads((ROOT/'workflows/qwen-model-lock.json').read_text())
        q4 = json.loads((ROOT/'workflows/qwen-model-lock-q4_k_m.json').read_text())
        self.assertEqual([m['component'] for m in q4], [m['component'] for m in q8])
        for a, b in zip(q8, q4):
            self.assertEqual((a['repository'], a['revision'], a['folder'], a['license']), (b['repository'], b['revision'], b['folder'], b['license']))
            self.assertEqual(len(b['sha256']), 64)
        self.assertEqual(q8[2:], q4[2:])
        self.assertIn('Q4_K_M', q4[0]['filename']); self.assertIn('Q4_K_M', q4[1]['filename'])
        self.assertLess(sum(m['bytes'] for m in q4), 20.5e9)
        self.assertGreater(sum(m['bytes'] for m in q8), 31e9)

    def test_environment_selects_the_quantization(self):
        self.assertEqual(json.loads(self.preset('Q8_0').stdout),
                         ['qwen-image-edit-2511-Q8_0.gguf', 'Qwen2.5-VL-7B-Instruct-Q8_0.gguf', 'qwen-model-lock.json'])
        self.assertEqual(json.loads(self.preset('Q4_K_M').stdout),
                         ['qwen-image-edit-2511-Q4_K_M.gguf', 'Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf', 'qwen-model-lock-q4_k_m.json'])
        failed = self.preset('Q2_K')
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn('SHOTBOARD_QWEN_QUANT', failed.stderr)

    def test_engine_report_is_checked_against_the_selected_lock(self):
        q4_path = ROOT/'workflows/qwen-model-lock-q4_k_m.json'
        q4 = json.loads(q4_path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'models.json'
            path.write_text(json.dumps(dict(schema_version=1, verified=True, models=[dict(m, verified=True) for m in q4])))
            with patch.object(server, 'ENGINE_MANIFEST', str(path)):
                with self.assertRaises(ValueError):
                    server.verify_models('qwen-reference')
                with patch.object(server, 'QWEN_LOCK', q4_path):
                    self.assertEqual(server.verify_models('qwen-reference'), q4)
