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
        self.assertIn('top:calc(var(--gutter) * -1)', heading, 'Cancels the dialog padding so nothing shows above the heading')
        self.assertRegex(css, r'\ndialog\{[^}]*padding:var\(--gutter\)')
        self.assertIn('background:var(--page)', heading)
        touch = css[css.index('@media(pointer:coarse)'):]
        touch = touch[:touch.index('\n}\n')]
        root = css[css.index(':root{'):css.index('\n}\n')]
        for token in ('--h:36px', '--h-bar:32px', '--h-lg:44px', '--hit:48px', '--rim:calc((var(--hit) - var(--h)) / 2)', '--rim-bar:calc((var(--hit) - var(--h-bar)) / 2)'):
            self.assertIn(token, root)
        for rule in ('min-height:var(--hit)', '.icon{width:var(--hit);height:var(--hit)}', '.rail-cut{min-height:var(--hit)}', '.seg>label::after,.seg>button::after{content:"";position:absolute;inset:calc(var(--rim) * -1) 0}'):
            self.assertIn(rule, touch)
        self.assertGreater(css.index('@media(pointer:coarse)'), css.index('@media(max-width:600px)'),
                           'Touch sizes come after the phone layout so they win')
        self.assertIn('background-clip:padding-box', touch, 'Filled buttons paint inside the 48px target')
        # The rim is on the block axis only, so painted edges line up with the fields and segments beside them.
        rim = re.search(r'([.\w,-]+)\{border:solid transparent;border-width:var\(--rim\) 0;[^}]*padding-top:0;padding-bottom:0', touch).group(1).split(',')
        self.assertIn('.icon{border:var(--rim) solid transparent;background-clip:padding-box', touch)
        self.assertRegex(touch, r'input:not\(\[type=checkbox\]\):not\(\[type=radio\]\),select\{border:solid transparent;border-width:var\(--rim\) 0;background-clip:padding-box',
                         'Single-line fields paint at button height too')
        for kind in ('.primary', '.quiet', '.plain', '.state', '.chip'):
            self.assertIn(kind, rim, 'Every painted button keeps its desktop size inside the touch target')
        fine = css[css.index('@media(pointer:fine)'):]
        self.assertIn('inset:calc(var(--s1) * -1) 0', fine[:fine.index('\n}\n')], 'A 36px button answers a 44px band under the mouse')
        self.assertIn('.topbar nav>*{min-height:var(--hit);border-width:var(--rim-bar) 0', touch, 'Header buttons paint 32px inside a 48px target')
        self.assertIn('.large{min-height:calc(var(--h-lg) + 2 * var(--rim))}', touch, 'The composer action keeps its 44px paint on touch')
        # Fields paint exactly at button height: border, padding and one 20px line add up to --h.
        self.assertIn('padding:calc((var(--h) - var(--lh-field) - 2 * var(--hair)) / 2) var(--s3);min-height:var(--h)', css)
        self.assertIn('min-height:calc(var(--h) - 2 * var(--hair))', css, 'Segments, border included, are 36px too')

    def test_header_buttons_are_slim(self):
        css = (STATIC / 'style.css').read_text()
        self.assertIn('.topbar nav>*{min-height:var(--h-bar);padding:0 var(--pad-x)}', css)
        phone = css[css.index('@media(max-width:600px)'):]
        self.assertIn('.topbar nav>*{padding:0 var(--s3);font-size:var(--t-sm)}', phone[:phone.index('\n}\n')])

    def test_style_values_come_from_the_tokens(self):
        css = (STATIC / 'style.css').read_text()
        start = css.index(':root{')
        end = css.index('\n}\n', start)
        root, rules = css[start:end], re.sub(r'@font-face\{[^}]*\}', '', css[:start] + css[end:])
        # Colours live in :root only; rules name them.
        self.assertEqual(re.findall(r'#[0-9a-fA-F]{3,8}\b|rgba?\(', rules), [])
        # One type scale, one set of line heights and weights: no raw values in the rules.
        for prop in ('font-size', 'line-height', 'font-weight', 'letter-spacing', 'z-index'):
            for value in re.findall(rf'(?<![-\w]){prop}:([^;}}]+)', rules):
                with self.subTest(prop=prop, value=value):
                    self.assertRegex(value.strip(), r'^(var\(--[\w-]+\)|inherit|\.8em|\d+px)$' if prop == 'line-height' else r'^(var\(--[\w-]+\)|inherit|\.8em)$')
        for value in re.findall(r'(?<![-\w])font:([^;}]+)', rules):
            with self.subTest(font=value):
                self.assertRegex(value.strip(), r'^(inherit|var\(--w-[\w-]+\) var\(--t-[\w-]+\)/var\(--lh-[\w-]+\) var\(--(ui|script)\))$')
        for value in re.findall(r'(?<![-\w])transition:([^;}]+)', rules):
            for part in value.split(','):
                with self.subTest(transition=part):
                    self.assertRegex(part.strip(), r'^[\w-]+ var\(--dur[\w-]*\) var\(--ease\)$')
        # Every stroke that draws a setup line is a border or outline of --line, never a box with a width.
        self.assertIn('--line:2px', root)
        self.assertNotRegex(rules, r'(::before|\.stem)\{[^}]*(width|height):var\(--line\)')

    def test_high_contrast_and_reduced_motion(self):
        css = (STATIC / 'style.css').read_text()
        forced = css[css.index('@media(forced-colors:active){'):]
        for rule in ('.rail-cut[aria-current]', '.seg>label:has(input:checked)', '.shot-card.is-hero .shot-hero,.fig-hero .take-zoom', '.take-id.picked{border-color:Highlight}', 'input[type=checkbox]{appearance:auto'):
            self.assertIn(rule, forced)
        coarse = css[css.index('@media(forced-colors:active) and (pointer:coarse){'):]
        self.assertIn('border-color:Canvas', coarse[:coarse.index('\n}\n')], 'Touch rims vanish instead of drawing black bars')
        reduced = css[css.index('@media(prefers-reduced-motion:reduce)'):]
        self.assertIn('animation:none!important', reduced)
        self.assertIn(':active{transform:none!important}', reduced)
        self.assertNotIn('button:active:not(:disabled),.button:active{transform', css, 'Large surfaces do not press in')

    def test_icons_share_one_stroke(self):
        html = (STATIC / 'index.html').read_text()
        strokes = re.findall(r'stroke-width="([\d.]+)"', html)
        self.assertTrue(strokes)
        self.assertEqual(set(strokes), {'1.5'})
        self.assertEqual(html.count('vector-effect="non-scaling-stroke"'), len(strokes))
        self.assertIn('stroke-width="1.5"', (STATIC / 'app.js').read_text())
        self.assertNotIn('dialog-kicker', html, 'No eyebrow above the Compare heading')

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
