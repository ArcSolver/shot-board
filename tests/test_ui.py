"""Exercise browser hero and review controls with a small DOM harness in Node."""
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unittest

STATIC = Path(__file__).resolve().parents[1] / 'shotboard' / 'static'


class HeroUITests(unittest.TestCase):
    def test_hero_controls_and_take_reviews(self):
        subprocess.run(['node', str(Path(__file__).with_name('hero-ui.cjs'))], check=True, timeout=15)


class BoardUITests(unittest.TestCase):
    def test_images_review_legend_enlarged_view_and_back(self):
        subprocess.run(['node', str(Path(__file__).with_name('board-ui.cjs'))], check=True, timeout=15)


class PageTests(unittest.TestCase):
    def test_landing_says_what_it_does_and_links_the_project(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links, self.ids, self.footer = [], set(), False
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                self.ids.add(attrs.get('id'))
                self.footer |= tag == 'footer'
                if self.footer and tag == 'a':
                    self.links.append(attrs['href'])
            def handle_endtag(self, tag):
                self.footer &= tag != 'footer'
        html = (STATIC / 'index.html').read_text()
        page = Links()
        page.feed(html)
        self.assertIn('<p class="home-lede">Shot Board turns one scene into six camera cuts.', html)
        self.assertEqual(page.links, ['https://github.com/ArcSolver/shot-board',
                                      'https://github.com/ArcSolver/shot-board/blob/main/LICENSE',
                                      'https://github.com/ArcSolver/shot-board/blob/main/THIRD_PARTY_NOTICES.md'])
        self.assertTrue({'review-legend', 'image-dialog', 'image-full', 'image-preview', 'close-image'} <= page.ids)

    def test_dialog_heading_stays_on_screen_and_touch_targets_are_48px(self):
        css = (STATIC / 'style.css').read_text()
        heading = re.search(r'\n\.dialog-heading\{([^}]*)\}', css).group(1)
        self.assertIn('position:sticky', heading)
        self.assertIn('top:-28px', heading, 'Cancels the dialog padding so nothing shows above the heading')
        self.assertIn('background:var(--sheet)', heading)
        touch = css[css.index('@media(pointer:coarse)'):]
        touch = touch[:touch.index('\n}\n')]
        for rule in ('min-height:48px', '.icon{width:48px;height:48px}', '.take-thumb{width:64px;height:48px}'):
            self.assertIn(rule, touch)
        self.assertGreater(css.index('@media(pointer:coarse)'), css.index('@media(max-width:600px)'),
                           'Touch sizes come after the phone layout so they win')
        self.assertIn('background-clip:padding-box', touch, 'Filled buttons paint inside the 48px target')
        rim = re.search(r'([.\w,-]+)\{border:4px solid transparent', touch).group(1).split(',')
        self.assertIn('.on-photo', rim, 'The button on the cover photo paints at the same size as the others')

    def test_review_note_spans_the_take_and_dialogs_focus_their_title(self):
        css = (STATIC / 'style.css').read_text()
        self.assertIn('.review-note{grid-column:1/-1}', css)
        js = (STATIC / 'app.js').read_text()
        form = js[js.index('<form class="review-editor"'):js.index('</form>', js.index('<form class="review-editor"'))]
        self.assertLess(form.index('name="note"'), form.index('name="verdict"'), 'Note comes first so focus order matches the layout')
        self.assertLess(form.index('name="verdict"'), form.index('type="submit"'))
        html = (STATIC / 'index.html').read_text()
        for dialog in re.findall(r'<dialog id="[^"]+"[^>]*>.*?</dialog>', html, re.S):
            if 'dialog-heading' in dialog:
                self.assertRegex(dialog, r'<h2 id="[^"]+" tabindex="-1" autofocus>', 'Opening a dialog focuses its title, not the first button')
