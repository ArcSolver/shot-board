from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from PIL import Image
from fastapi.testclient import TestClient
from shotboard import server
from shotboard.core import ROOT, PRESETS, expand_shots, settings_for, workflow_for, sha256, export_board


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.shots = expand_shots(server.Scene(scene="A traveler discovers a brass compass in a greenhouse",
                                              character="An adult traveler").model_dump())

    def test_framing_first_and_distinct_geometry_negative_cfg(self):
        for shot in self.shots:
            self.assertTrue(shot['prompt'].startswith('('+shot['direction']+':1.45)'))
            self.assertLess(shot['prompt'].index(shot['direction']), shot['prompt'].index('Character:'))
            settings = settings_for(shot, 'sdxl-base')
            graph = workflow_for(shot, 0, settings)
            self.assertEqual(graph['4']['inputs']['width'], settings['width'])
            self.assertEqual(graph['5']['inputs']['cfg'], settings['cfg'])
            self.assertEqual(graph['5']['inputs']['seed'], 0)
            self.assertEqual(settings['width'] % 64, 0)
        self.assertGreater(self.shots[0]['render_settings']['width'], self.shots[0]['render_settings']['height'])
        self.assertLess(self.shots[2]['render_settings']['width'], self.shots[2]['render_settings']['height'])
        self.assertIn('front view', self.shots[3]['negative'])
        self.assertIn('face', self.shots[4]['negative'])
        self.assertIn('eye level', self.shots[5]['negative'])
        self.assertGreater(len({s['negative'] for s in self.shots}), 5)
        self.assertNotEqual(settings_for(self.shots[0], 'sdxl-base')['cfg'], settings_for(self.shots[5], 'sdxl-base')['cfg'])

    def test_explicit_coverage_overrides_conflicting_angle(self):
        shots=expand_shots(server.Scene(scene="A traveler finds a compass", angle='High angle').model_dump())
        self.assertIn('high angle', shots[1]['prompt'])
        for i in (2,3,4,5):
            self.assertNotIn('high angle', shots[i]['prompt'])
        self.assertIn("worm's-eye", shots[5]['prompt'])

    def test_qwen_graph_has_reference_and_no_angle_lora(self):
        shot = self.shots[3]
        settings = settings_for(shot, 'qwen-reference')
        reference = {'image':'references/hero.png'}
        graph = workflow_for(shot, 41, settings, reference)
        self.assertEqual(graph['8']['inputs']['unet_name'], 'qwen-image-edit-2511-Q8_0.gguf')
        self.assertEqual(graph['9']['class_type'], 'CLIPLoaderGGUF')
        self.assertEqual(graph['9']['inputs']['clip_name'], 'Qwen2.5-VL-7B-Instruct-Q8_0.gguf')
        self.assertEqual(graph['2']['inputs']['image1'], ['14',0])
        self.assertEqual(graph['1']['inputs']['image'], reference['image'])
        self.assertIn('SAME scene', graph['2']['inputs']['prompt'])
        self.assertNotIn(':1.45', graph['2']['inputs']['prompt'])
        self.assertEqual(graph['4']['inputs']['width'], shot['reference_size']['width'])
        self.assertEqual(graph['5']['inputs']['steps'],24)
        self.assertEqual(graph['5']['inputs']['cfg'],4)
        loras=[n['inputs']['lora_name'] for n in graph.values() if n['class_type']=='LoraLoaderModelOnly']
        self.assertEqual(loras,[])
        with self.assertRaisesRegex(ValueError, 'hero'):
            workflow_for(shot, 0, settings)
        self.assertNotIn('preset_id', PRESETS['qwen-reference'])

    def test_templates_follow_explicit_subject_and_prop(self):
        config=server.Scene(scene='A robot inspects a silver key on a spaceship',
                            character='An adult robot, blue coat',setting='A spaceship cabin',prop='silver key').model_dump()
        shots=expand_shots(config)
        self.assertIn('silver key', shots[4]['direction'])
        self.assertIn('An adult robot', shots[0]['direction'])
        for shot in shots:
            self.assertNotIn('greenhouse', shot['prompt'])
            self.assertNotIn('compass', shot['prompt'])
        self.assertEqual(settings_for({},'sdxl-base')['width'],1024)

    def test_all_qwen_components_are_pinned_and_projector_included(self):
        lock=json.loads((ROOT/'workflows/qwen-model-lock.json').read_text())
        self.assertEqual(len(lock),4)
        self.assertTrue(any(m['component']=='vision projector' for m in lock))
        self.assertTrue(all(len(m['sha256'])==64 and len(m['revision'])==40 and m['license']=='Apache-2.0' for m in lock))
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            for m in lock:
                dest=base/m['folder']/m['filename'];dest.parent.mkdir(exist_ok=True);dest.write_bytes(b'test')
            with patch.object(server,'REFERENCE_MODEL_DIR',base), patch.object(server,'QWEN_MODEL_DIR',base/'diffusion_models'):
                with self.assertRaisesRegex(ValueError,'hash differs'):
                    server.verify_models('qwen-reference')


class ContinuityAPITests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name)
        self.data_patch=patch.object(server,'DATA',self.data);self.data_patch.start();self.addCleanup(self.data_patch.stop)
        self.store_patch=patch.object(server,'store',server.Store());self.store_patch.start();self.addCleanup(self.store_patch.stop)
        self.client=TestClient(server.app);self.client.__enter__();self.addCleanup(self.client.__exit__,None,None,None)
        server.store.stop.set();server.store.thread.join(timeout=2)
        self.board=self.client.post('/api/boards',json={'scene':'A traveler finds a brass compass'}).json()
        self.bid=self.board['id'];self.base='/api/boards/'+self.bid
        self.board=server.store.boards[self.bid]
        self.shot=self.board['shots'][1]
        source=self.data/self.bid/'hero.png';Image.new('RGB',(32,24),'gold').save(source)
        self.take=dict(id='t01',status='succeeded',seed=0,image='hero.png',image_sha256=sha256(source),
                       settings=settings_for(self.shot,'sdxl-base'),models=[],elapsed_seconds=1,
                       workflow=workflow_for(self.shot,0,settings_for(self.shot,'sdxl-base')))
        self.shot.update(takes=[self.take],picked='t01')

    def enable(self):
        return self.client.post(self.base+'/continuity',json={'enabled':True,'shot_id':'s02','take_id':'t01'})

    def test_per_cut_settings_validation_and_immutable_existing_take(self):
        before=deepcopy(self.take)
        edit=dict(title='New medium',prompt='A medium photo',negative='illustration',
                  render_settings=dict(width=768,height=1024,cfg=7.2))
        self.assertEqual(self.client.patch(self.base+'/shots/s02',json=edit).status_code,200)
        self.assertEqual(settings_for(self.shot,'sdxl-base')['cfg'],7.2)
        self.assertEqual(self.take,before)
        for key,value in [('width',513),('height',0),('cfg',99)]:
            invalid=deepcopy(edit);invalid['render_settings'][key]=value
            self.assertEqual(self.client.patch(self.base+'/shots/s02',json=invalid).status_code,422)

    def test_hero_requires_pick_and_cannot_change_during_queue(self):
        self.assertEqual(self.client.post(self.base+'/generate',json={'preset':'qwen-reference'}).status_code,409)
        self.shot['picked']=None
        self.assertEqual(self.enable().status_code,409)
        self.shot['picked']='t01'
        self.assertEqual(self.enable().status_code,200)
        with patch.object(server,'verify_models',return_value=[]):
            response=self.client.post(self.base+'/generate',json={'takes':1})
        self.assertEqual(response.status_code,202)
        self.assertEqual(response.json()['queued'],5)
        self.assertEqual(self.enable().status_code,409)
        self.assertEqual(len(self.shot['takes']),1)

    def test_qwen_edit_or_non_sdxl_take_cannot_be_hero(self):
        original = deepcopy(self.take)
        for change in ('reference', 'preset', 'checkpoint', 'graph'):
            with self.subTest(change=change):
                self.take.clear(); self.take.update(deepcopy(original))
                if change == 'reference': self.take['reference'] = {'image': 'old-hero.png'}
                elif change == 'preset': self.take['settings'] = settings_for(self.shot, 'qwen-reference')
                elif change == 'checkpoint': self.take['settings']['checkpoint'] = 'unknown.safetensors'
                else: self.take['workflow']['1']['class_type'] = 'LoadImage'
                response = self.enable()
                self.assertEqual(response.status_code, 409)
                self.assertIn('Only an SDXL original', response.json()['detail'])
                self.assertFalse((self.data/self.bid/'references').exists())
                self.assertFalse(self.board['continuity']['enabled'])
        self.take.clear(); self.take.update(original)
        self.assertEqual(self.enable().status_code, 200)

    def test_frozen_hero_and_take_settings_survive_edits_and_disable(self):
        self.enable()
        with patch.object(server,'verify_models',return_value=[{'sha256':'a'*64}]):
            response=self.client.post(self.base+'/generate',json={'takes':1,'shot_id':'s03'})
        self.assertEqual(response.status_code,202)
        cut=self.board['shots'][2];take=deepcopy(cut['takes'][0])
        cut['prompt']='Completely new prompt';self.take['settings']['cfg']=99
        self.assertNotEqual(take['reference']['settings']['cfg'],99)
        self.assertNotEqual(take['workflow']['2']['inputs']['prompt'],cut['prompt'])
        self.assertTrue((self.data/self.bid/take['reference']['image']).is_file())
        self.assertEqual(take['reference']['image_sha256'],sha256(self.data/self.bid/take['reference']['image']))
        cut['takes'][0]['status']='succeeded'
        self.assertEqual(self.client.post(self.base+'/continuity',json={'enabled':False}).status_code,200)
        self.assertEqual(cut['takes'][0]['reference'],take['reference'])

    def test_tampered_hero_rejected_before_queue(self):
        self.enable()
        hero=self.board['continuity']['hero']
        (self.data/self.bid/hero['image']).write_bytes(b'corrupt')
        self.assertEqual(self.client.post(self.base+'/generate',json={'takes':1}).status_code,409)
        self.assertTrue(server.store.tasks.empty())

    def test_hero_cut_cannot_be_overwritten_or_regenerated(self):
        self.enable()
        self.shot['takes'].append(dict(self.take,id='t02'))
        self.assertEqual(self.client.post(self.base+'/shots/s02/pick',json={'take_id':'t02'}).status_code,409)
        self.assertEqual(self.client.post(self.base+'/generate',json={'shot_id':'s02'}).status_code,409)
        self.client.post(self.base+'/continuity',json={'enabled':False})
        self.assertEqual(self.client.post(self.base+'/shots/s02/pick',json={'take_id':'t02'}).status_code,200)

    def test_export_bundles_hash_checked_hero_and_two_graph_forms(self):
        self.enable()
        reference=deepcopy(self.board['continuity']['hero'])
        cut=self.board['shots'][0];settings=settings_for(cut,'qwen-reference')
        graph=workflow_for(cut,0,settings,reference)
        materialized=deepcopy(graph);materialized['1']['inputs']['image']={'comfy_asset':'local-test'}
        take=dict(self.take,settings=settings,workflow=graph,reference=reference,
                  submitted_workflow=materialized,submission_fingerprint_sha256=hashlib.sha256(json.dumps(materialized,sort_keys=True).encode()).hexdigest())
        for shot in self.board['shots']:
            shot.update(takes=[deepcopy(take)],picked='t01')
        with zipfile.ZipFile(io.BytesIO(export_board(self.board,self.data))) as archive:
            self.assertEqual(archive.read(reference['image']),(self.data/self.bid/'hero.png').read_bytes())
            manifest=json.loads(archive.read('manifest.json'))
            for item in manifest['shots']:
                self.assertEqual(item['reference']['image_sha256'],reference['image_sha256'])
                self.assertIn(item['submitted_workflow'],archive.namelist())
                submitted=json.loads(archive.read(item['submitted_workflow']))
                self.assertEqual(hashlib.sha256(archive.read(item['submitted_workflow'])).hexdigest(),item['submitted_workflow_sha256'])
                self.assertEqual(hashlib.sha256(json.dumps(submitted,sort_keys=True).encode()).hexdigest(),item['submission_fingerprint_sha256'])
        (self.data/self.bid/reference['image']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'reference changed'):
            export_board(self.board,self.data)


class SDKWorkerTests(unittest.TestCase):
    setUp = ContinuityAPITests.setUp
    enable = ContinuityAPITests.enable
    def test_worker_uploads_frozen_hero_through_sdk_and_keeps_portable_graph(self):
        from types import SimpleNamespace
        from comfy_sdk.workflows import Workflow
        self.enable()
        with patch.object(server,'verify_models',return_value=[]):
            self.client.post(self.base+'/generate',json={'takes':1,'shot_id':'s03'})
        take=self.board['shots'][2]['takes'][0]
        portable=deepcopy(take['workflow'])
        binding={'__type':'core/ASSET','info':{'id':'test-local-asset','hash':take['reference']['image_sha256'],'file_path':'hero.png'}}
        captured={}
        class Output:
            def to_file(inner,path):
                Image.new('RGB',(16,16),'green').save(path,format='PNG')
        class Job:
            status='succeeded'
            id='test-job'
            def get_outputs(inner,node):
                captured['output_node']=node
                server.store.stop.set()
                return [Output()]
        class Client:
            def __init__(inner,**kwargs):
                inner.workflows=SimpleNamespace(from_json=Workflow)
                def from_file(path):
                    captured['source']=path
                    return SimpleNamespace(as_reference=lambda:deepcopy(binding))
                inner.assets=SimpleNamespace(from_file=from_file)
            def __enter__(inner): return inner
            def __exit__(inner,*args): pass
            def submit(inner,workflow):
                captured['graph']=deepcopy(workflow.json)
                return Job()
        server.store.stop.clear()
        with patch.object(server,'Comfy',Client), patch.object(server.store.memory_guard,'prepare'):
            server.store.work()
        self.assertEqual(take['status'],'succeeded')
        self.assertEqual(captured['graph']['1']['inputs']['image'],binding)
        self.assertEqual(captured['source'],self.data/self.bid/take['reference']['image'])
        self.assertEqual(take['workflow'],portable)
        self.assertEqual(take['submitted_workflow'],captured['graph'])
        self.assertEqual(captured['output_node'],'7')
        self.assertEqual(take['image_sha256'],sha256(self.data/self.bid/take['image']))


class EngineRetryTests(unittest.TestCase):
    setUp = ContinuityAPITests.setUp
    enable = ContinuityAPITests.enable

    def run_take(self, failures, engine_up=True):
        """Queue one Qwen edit; `failures` lists what each submit raises before a success."""
        from types import SimpleNamespace
        import httpx
        from comfy_sdk.workflows import Workflow
        self.enable()
        with patch.object(server,'verify_models',return_value=[]):
            self.client.post(self.base+'/generate',json={'takes':1,'shot_id':'s03'})
        take=self.board['shots'][2]['takes'][0]
        calls=[]
        class Output:
            def to_file(inner,path):
                Image.new('RGB',(16,16),'green').save(path,format='PNG')
        class Job:
            status='succeeded'
            id='test-job'
            def get_outputs(inner,node):
                return [Output()]
        class Client:
            def __init__(inner,**kwargs):
                inner.workflows=SimpleNamespace(from_json=Workflow)
                inner.assets=SimpleNamespace(from_file=lambda path:SimpleNamespace(as_reference=lambda:{'__type':'core/ASSET'}))
            def __enter__(inner): return inner
            def __exit__(inner,*args): pass
            def submit(inner,workflow):
                calls.append(1)
                if len(calls)<=len(failures):
                    raise failures[len(calls)-1]
                return Job()
        health=SimpleNamespace(get=lambda url:SimpleNamespace(status_code=200 if engine_up else 503))
        probe=MagicMock()
        probe.return_value.__enter__.return_value=health
        done=server.store.tasks.task_done
        def finish():
            done();server.store.stop.set()
        server.store.stop.clear()
        with patch.object(server.store.tasks,'task_done',finish), \
             patch.object(server,'Comfy',Client), patch.object(server.store.memory_guard,'prepare'), \
             patch.object(server.httpx,'Client',probe), patch.object(server,'RETRY_WAIT_SECONDS',0.01):
            server.store.work()
        return take, calls, probe

    def test_dropped_engine_is_retried_once_and_succeeds(self):
        import httpx
        take, calls, probe = self.run_take([httpx.ReadError('engine closed the connection')])
        self.assertEqual(len(calls), 2)
        self.assertEqual(take['status'], 'succeeded')
        self.assertTrue(take['retried'])
        self.assertTrue(probe.call_count >= 1)

    def test_second_drop_fails_the_take(self):
        import httpx
        take, calls, _ = self.run_take([httpx.ConnectError('refused'), httpx.ConnectError('refused')])
        self.assertEqual(len(calls), 2)
        self.assertEqual(take['status'], 'failed')
        self.assertTrue(take['retried'])

    def test_no_retry_when_the_engine_does_not_come_back(self):
        import httpx
        take, calls, _ = self.run_take([httpx.ConnectError('refused')], engine_up=False)
        self.assertEqual(len(calls), 1)
        self.assertEqual(take['status'], 'failed')
        self.assertTrue(take['error'].startswith('ConnectError'))

    def test_other_errors_are_not_retried(self):
        take, calls, probe = self.run_take([ValueError('bad graph')])
        self.assertEqual(len(calls), 1)
        self.assertEqual(take['status'], 'failed')
        self.assertNotIn('retried', take)
        probe.assert_not_called()

if __name__=='__main__':
    unittest.main()
