"""Bound local model residency and stop work before macOS starts swapping."""
import re
import os
import subprocess
import sys
import time
from urllib.parse import urlparse

import httpx


class MemorySafetyError(RuntimeError):
    pass


def memory_sample():
    pressure = subprocess.check_output(['memory_pressure'], text=True, timeout=10)
    swap = subprocess.check_output(['sysctl', 'vm.swapusage'], text=True, timeout=10)
    free = re.search(r'memory free percentage:\s*(\d+)%', pressure)
    used = re.search(r'used\s*=\s*([\d.]+)M', swap)
    if not free or not used:
        raise MemorySafetyError('Memory check unavailable. Rendering stopped.')
    return int(free[1]), float(used[1])


class MemoryGuard:
    def __init__(self):
        self.engine_url = os.environ.get('COMFY_ENGINE_URL', 'http://127.0.0.1:8188').rstrip('/')
        parsed = urlparse(self.engine_url)
        if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise ValueError('Engine control requires a loopback HTTP URL')
        # A nonstandard loopback port is the remote SSH-tunnel convention.
        # Use ENGINE_MODE for tunnels on 8188 or local engines on other ports.
        self.mode = os.environ.get('ENGINE_MODE') or ('remote' if parsed.port not in (None, 8188) else 'local')
        if self.mode not in ('local', 'remote'):
            raise ValueError('ENGINE_MODE must be local or remote')
        self.preset = None
        self.previous = None
        self.checked_at = 0

    def prepare(self, preset):
        # Cache-none drops graph caches; /free also unloads resident model weights.
        if preset != self.preset:
            with httpx.Client(trust_env=False, timeout=30) as client:
                client.post(self.engine_url + '/free', json={
                    'unload_models': True, 'free_memory': True}).raise_for_status()
        self.preset = preset
        if self.mode == 'local' and preset == 'qwen-reference' and sys.platform == 'darwin':
            self.sample()

    def sample(self):
        try:
            free, swap = memory_sample()
        except (OSError, subprocess.SubprocessError) as exc:
            raise MemorySafetyError('Memory check unavailable. Rendering stopped.') from exc
        now = time.monotonic()
        previous = self.previous
        self.previous = (now, swap)
        self.checked_at = now
        if free < 25 or (previous and swap - previous[1] >= 256 and now - previous[0] <= 15):
            raise MemorySafetyError('Memory safety stop: below 25% free or rapid swap growth. Queued renders cancelled.')

    def check_running(self):
        if self.mode == 'local' and self.preset == 'qwen-reference' and sys.platform == 'darwin' and time.monotonic()-self.checked_at >= 5:
            self.sample()
