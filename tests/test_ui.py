"""Exercise browser hero controls with a small DOM harness in Node."""
from pathlib import Path
import subprocess
import unittest


class HeroUITests(unittest.TestCase):
    def test_hero_controls_reject_qwen_and_allow_sdxl(self):
        subprocess.run(['node', str(Path(__file__).with_name('hero-ui.cjs'))], check=True, timeout=15)
