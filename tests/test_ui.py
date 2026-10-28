"""Exercise browser hero and review controls with a small DOM harness in Node."""
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'shotboard' / 'static'


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
        self.assertIn('background:var(--page)', heading)
        touch = css[css.index('@media(pointer:coarse)'):]
        touch = touch[:touch.index('\n}\n')]
        for rule in ('min-height:48px', '.icon{width:48px;height:48px}', '.rail-cut{min-height:48px}', '.seg>label::after,.seg>button::after{content:"";position:absolute;inset:-6px 0}'):
            self.assertIn(rule, touch)
        self.assertGreater(css.index('@media(pointer:coarse)'), css.index('@media(max-width:600px)'),
                           'Touch sizes come after the phone layout so they win')
        self.assertIn('background-clip:padding-box', touch, 'Filled buttons paint inside the 48px target')
        # The rim is on the block axis only, so painted edges line up with the fields and segments beside them.
        rim = re.search(r'([.\w,-]+)\{border:solid transparent;border-width:6px 0;[^}]*padding-top:0;padding-bottom:0', touch).group(1).split(',')
        self.assertIn('.icon{border:6px solid transparent;background-clip:padding-box', touch)
        self.assertRegex(touch, r'input:not\(\[type=checkbox\]\):not\(\[type=radio\]\),select\{border:solid transparent;border-width:6px 0;background-clip:padding-box',
                         'Single-line fields paint at button height too')
        for kind in ('.primary', '.quiet', '.plain', '.state', '.chip'):
            self.assertIn(kind, rim, 'Every painted button keeps its desktop size inside the touch target')
        fine = css[css.index('@media(pointer:fine)'):]
        self.assertIn('inset:-4px 0', fine[:fine.index('\n}\n')], 'A 36px button answers a 44px band under the mouse')
        self.assertIn('.topbar nav>*{min-height:48px;border-width:8px', touch, 'Header buttons paint 32px inside a 48px target')

    def test_header_buttons_are_slim(self):
        css = (STATIC / 'style.css').read_text()
        self.assertIn('.topbar nav>*{min-height:32px;padding:0 14px}', css)
        phone = css[css.index('@media(max-width:600px)'):]
        self.assertIn('.topbar nav>*{padding:0 12px;font-size:13px}', phone[:phone.index('\n}\n')])

    def test_review_note_spans_the_take_and_dialogs_focus_their_title(self):
        css = (STATIC / 'style.css').read_text()
        self.assertIn('.review-note{grid-column:1/-1}', css)
        js = (STATIC / 'app.js').read_text()
        form = js[js.index('<form class="review-editor"'):js.index('</form>', js.index('<form class="review-editor"'))]
        self.assertLess(form.index('name="verdict"'), form.index('name="note"'), 'Focus order matches the layout: verdict, note, save')
        self.assertLess(form.index('name="note"'), form.index('type="submit"'))
        self.assertIn('<textarea name="note" maxlength="400" rows="5">', form, 'The note is a multi-line field')
        html = (STATIC / 'index.html').read_text()
        for dialog in re.findall(r'<dialog id="[^"]+"[^>]*>.*?</dialog>', html, re.S):
            if 'dialog-heading' in dialog:
                self.assertRegex(dialog, r'<h2 id="[^"]+" tabindex="-1" autofocus>', 'Opening a dialog focuses its title, not the first button')


class DirectionTests(unittest.TestCase):
    def test_fonts_are_self_hosted_with_their_licenses(self):
        css = (STATIC / 'style.css').read_text()
        for name in ('hanken-grotesk.woff2', 'courier-prime-400.woff2', 'courier-prime-700.woff2'):
            self.assertIn(f'url({name})', css, 'Relative URLs work under the Pages subpath too')
            self.assertTrue((STATIC / name).is_file())
        for name in ('OFL-hanken-grotesk.txt', 'OFL-courier-prime.txt'):
            self.assertIn('SIL Open Font License', (STATIC / name).read_text())
        self.assertNotIn('/static/', css)
        notices = (ROOT / 'THIRD_PARTY_NOTICES.md').read_text()
        self.assertIn('Hanken Grotesk', notices)
        self.assertIn('Courier Prime', notices)

    def test_templates_set_no_inline_styles(self):
        # The static viewer's CSP is style-src 'self': inline style attributes are dropped there.
        js = (STATIC / 'app.js').read_text()
        self.assertNotRegex(js, r'style="')
        self.assertNotRegex((STATIC / 'index.html').read_text(), r'style="')

    def test_no_glyphs_the_fonts_do_not_carry(self):
        for path in (STATIC / 'app.js', STATIC / 'index.html'):
            for glyph in '←→✕★✓':
                self.assertNotIn(glyph, path.read_text(), f'{glyph} in {path.name}')

    def test_export_screen_lists_what_export_board_writes(self):
        from shotboard.core import export_board
        slugs = sorted(p.parent.name for p in (ROOT / 'examples').glob('*/board.json'))
        shown = json.loads(subprocess.run(['node', str(Path(__file__).with_name('zip-ui.cjs')), *slugs],
                                          check=True, capture_output=True, text=True, timeout=15).stdout)
        for slug in slugs:
            folder = ROOT / 'examples' / slug
            board = json.loads((folder / 'board.json').read_text())
            with self.subTest(example=slug), tempfile.TemporaryDirectory() as tmp:
                data = Path(tmp) / board['id']
                data.mkdir()
                for take in (folder / 'takes').iterdir():
                    (data / take.name).symlink_to(take.resolve())
                if (folder / 'references').is_dir():
                    (data / 'references').symlink_to((folder / 'references').resolve())
                with zipfile.ZipFile(io.BytesIO(export_board(board, tmp))) as archive:
                    self.assertEqual(sorted(shown[slug]), sorted(archive.namelist()))
