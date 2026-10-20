"""Exercise browser hero and review controls with a small DOM harness in Node."""
from pathlib import Path
import subprocess
import unittest


class HeroUITests(unittest.TestCase):
    def test_hero_controls_and_take_reviews(self):
        subprocess.run(['node', str(Path(__file__).with_name('hero-ui.cjs'))], check=True, timeout=15)
