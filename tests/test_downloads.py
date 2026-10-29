"""Pinned download regression tests use tiny in-memory files, never models."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import download_model, model_report, setup_reference, update_model_lock
from scripts.model_files import ensure_model
from shotboard.core import ROOT


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'workflows').mkdir()
        self.payload = b'public test fixture'
        self.sdxl = json.loads((ROOT / 'workflows/model-lock.json').read_text())
        self.qwen = json.loads((ROOT / 'workflows/qwen-model-lock.json').read_text())
        for item in [self.sdxl, *self.qwen]:
            item.update(bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())
        for name, data in [('model-lock.json', self.sdxl), ('qwen-model-lock.json', self.qwen)]:
            (self.root / 'workflows' / name).write_text(json.dumps(data))
        self.lock_before = (self.root / 'workflows/model-lock.json').read_bytes()

    def test_sdxl_uses_only_locked_url_and_never_rewrites_lock(self):
        target = self.root / 'models/checkpoints' / self.sdxl['filename']
        def response(url, **kwargs):
            self.assertEqual(url, f"https://huggingface.co/{self.sdxl['repository']}/resolve/{self.sdxl['revision']}/{self.sdxl['filename']}")
            self.assertFalse(target.exists())
            return io.BytesIO(self.payload)
        with patch.object(download_model, 'ROOT', self.root), patch('urllib.request.urlopen', side_effect=response) as request:
            download_model.download(target.parent)
            download_model.download(target.parent)
            self.assertEqual(request.call_count, 1)
        self.assertEqual(target.read_bytes(), self.payload)
        self.assertEqual((self.root / 'workflows/model-lock.json').read_bytes(), self.lock_before)
        self.assertEqual(list(target.parent.glob('*.part')), [])

    def test_sdxl_bad_size_hash_or_interrupted_download_never_published(self):
        for payload in (self.payload[:-1], self.payload + b'x', b'x' * len(self.payload), None):
            with self.subTest(payload=payload):
                target = self.root / 'models' / self.sdxl['filename']
                response = patch('urllib.request.urlopen', side_effect=OSError('network interrupted')) if payload is None else patch('urllib.request.urlopen', return_value=io.BytesIO(payload))
                with patch.object(download_model, 'ROOT', self.root), response:
                    with self.assertRaises((OSError, ValueError)):
                        download_model.download(target.parent)
                self.assertFalse(target.exists())
                self.assertEqual(list(target.parent.glob('*.part')), [])
                self.assertEqual((self.root / 'workflows/model-lock.json').read_bytes(), self.lock_before)

    def test_corrupt_existing_file_is_never_overwritten(self):
        target = self.root / 'model'
        target.write_bytes(b'bad')
        with patch('urllib.request.urlopen') as request:
            with self.assertRaisesRegex(ValueError, 'size'):
                ensure_model(self.sdxl, target, download=True)
            request.assert_not_called()
        self.assertEqual(target.read_bytes(), b'bad')
        target.write_bytes(b'x' * len(self.payload))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            ensure_model(self.sdxl, target, download=True)

    def test_target_is_absent_until_entire_stream_is_verified(self):
        target = self.root / 'model'
        outer = self
        class Stream(io.BytesIO):
            def read(self, size=-1):
                outer.assertFalse(target.exists())
                return super().read(size)
        with patch('urllib.request.urlopen', return_value=Stream(self.payload)):
            ensure_model(self.sdxl, target, download=True)
        self.assertEqual(target.read_bytes(), self.payload)

    def test_qwen_downloads_and_verifies_all_four_source_paths(self):
        paths = ['qwen-image-edit-2511-Q8_0.gguf', 'Qwen2.5-VL-7B-Instruct-Q8_0.gguf',
                 'mmproj-F16.gguf', 'split_files/vae/qwen_image_vae.safetensors']
        self.assertEqual([m['path'] for m in self.qwen], paths)
        models = self.root / 'models'
        with patch.object(setup_reference, 'ROOT', self.root), patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(self.payload)) as request:
            setup_reference.setup(models, models / 'diffusion_models', download=True)
            self.assertEqual(request.call_count, 4)
            for item, call in zip(self.qwen, request.call_args_list):
                self.assertEqual(call.args[0], f"https://huggingface.co/{item['repository']}/resolve/{item['revision']}/{item['path']}")
                self.assertEqual((models / item['folder'] / item['filename']).read_bytes(), self.payload)
            request.reset_mock()
            setup_reference.setup(models, models / 'diffusion_models')
            request.assert_not_called()
            (models / self.qwen[2]['folder'] / self.qwen[2]['filename']).write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError, 'size'):
                setup_reference.setup(models, models / 'diffusion_models')

    def test_first_takes_add_only_the_qwen_image_file(self):
        image = json.loads((ROOT / 'workflows/qwen-image-model-lock.json').read_text())
        (self.root / 'workflows/qwen-image-model-lock.json').write_text(json.dumps([dict(m, bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest()) for m in image]))
        models = self.root / 'models'
        with patch.object(setup_reference, 'ROOT', self.root), patch('urllib.request.urlopen', side_effect=lambda *a, **k: io.BytesIO(self.payload)) as request:
            setup_reference.setup(models, models / 'diffusion_models', download=True, first_takes=True)
            self.assertEqual(request.call_count, 5)
            self.assertEqual(request.call_args.args[0], f"https://huggingface.co/unsloth/Qwen-Image-2512-GGUF/resolve/{image[0]['revision']}/qwen-image-2512-Q8_0.gguf")
        self.assertTrue((models / 'diffusion_models/qwen-image-2512-Q8_0.gguf').is_file())

    def test_worker_report_measures_all_five_files_and_rejects_mismatch(self):
        models = self.root / 'models'
        for item in [self.sdxl, *self.qwen]:
            target = models / item.get('folder', 'checkpoints') / item['filename']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.payload)
        with patch.object(model_report, 'ROOT', self.root):
            report = model_report.report(models)
            self.assertTrue(report['verified'])
            self.assertEqual(len(report['models']), 5)
            self.assertTrue(all(m['verified'] and m['bytes'] == len(self.payload) for m in report['models']))
            target.write_bytes(b'bad')
            with self.assertRaises(ValueError):
                model_report.report(models)

    def test_only_explicit_update_script_changes_sdxl_lock(self):
        revision = 'a' * 40
        info = dict(sha=revision, siblings=[dict(rfilename=self.sdxl['filename'], lfs=dict(sha256='b'*64, size=42))])
        with patch.object(update_model_lock, 'ROOT', self.root), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(info).encode())) as request:
            update_model_lock.update(revision)
            self.assertIn('/revision/' + revision, request.call_args.args[0])
        lock = json.loads((self.root / 'workflows/model-lock.json').read_text())
        self.assertEqual((lock['revision'], lock['bytes'], lock['sha256']), (revision, 42, 'b'*64))
        with self.assertRaises(ValueError):
            update_model_lock.update('main')
