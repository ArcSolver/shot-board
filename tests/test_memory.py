import subprocess
import unittest
from unittest.mock import patch
from shotboard.memory import MemoryGuard, MemorySafetyError, memory_sample

class MemoryTests(unittest.TestCase):
    def test_pressure_and_swap_parsing(self):
        with patch('shotboard.memory.subprocess.check_output', side_effect=[
            'System-wide memory free percentage: 61%',
            'vm.swapusage: total = 1024.00M  used = 12.50M  free = 1011.50M']):
            self.assertEqual(memory_sample(), (61, 12.5))

    def test_model_switch_frees_both_directions(self):
        guard = MemoryGuard()
        with patch('shotboard.memory.httpx.Client') as client, patch.object(guard, 'sample') as sample, patch('shotboard.memory.sys.platform','darwin'):
            for preset in ('sdxl-base','qwen-reference','qwen-reference','sdxl-base'):
                guard.prepare(preset)
            self.assertEqual(client.return_value.__enter__.return_value.post.call_count, 3)
            self.assertEqual(sample.call_count, 2)
            self.assertEqual(client.return_value.__enter__.return_value.post.call_args.kwargs['json'],
                             {'unload_models':True,'free_memory':True})

    def test_low_memory_and_rapid_swap_stop(self):
        guard = MemoryGuard()
        with patch('shotboard.memory.memory_sample',return_value=(24,0)):
            with self.assertRaises(MemorySafetyError): guard.sample()
        guard = MemoryGuard()
        with patch('shotboard.memory.memory_sample',side_effect=[(60,0),(55,256)]), patch('shotboard.memory.time.monotonic',side_effect=[10,15]):
            guard.sample()
            with self.assertRaises(MemorySafetyError): guard.sample()

    def test_unreadable_pressure_stops(self):
        with patch('shotboard.memory.memory_sample',side_effect=subprocess.TimeoutExpired('memory_pressure',10)):
            with self.assertRaises(MemorySafetyError): MemoryGuard().sample()
