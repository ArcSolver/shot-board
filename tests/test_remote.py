import json
from pathlib import Path
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
