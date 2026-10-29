// Image loading, the review legend, the enlarged view and Back-closes-dialog, in a small DOM harness.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) {
    const classes = new Set(), attributes = new Map();
    const el = {id, dataset:{}, value:'', hidden:false, innerHTML:'', textContent:'',
      classList:{add:(...c)=>c.forEach(x=>classes.add(x)), remove:(...c)=>c.forEach(x=>classes.delete(x)), toggle:c=>classes.has(c)?classes.delete(c):classes.add(c), contains:c=>classes.has(c)},
      setAttribute:(k,v)=>attributes.set(k,String(v)), removeAttribute:k=>{attributes.delete(k); if(k==='src')delete el.src;}};
    if (id.endsWith('-dialog')) Object.assign(el, {open:false, showModal(){el.open=true;}, close(){if(!el.open)return; el.open=false; queue.push(()=>el.onclose?.());}});
    elements.set(id, el);
  }
  return elements.get(id);
};
const links = []; links.removed = 0;
const queue = [], listeners = {}, states = [null], history = {backs:0,
  get entries(){return states.length;}, get state(){return states.at(-1);},
  pushState(state){states.push(state);},
  replaceState(state){states[states.length-1]=state;},
  back(){history.backs++; states.pop(); queue.push(()=>listeners.popstate());}};
const flush = () => { while (queue.length) queue.shift()(); };
const browserBack = () => { states.pop(); listeners.popstate(); flush(); };
const browserForward = state => { states.push(state); listeners.popstate(); flush(); };
const window = {addEventListener:(type, fn)=>{listeners[type]=fn;}, history};
const context = vm.createContext({
  document:{getElementById:element, querySelectorAll:()=>[], addEventListener:()=>{},
    createElement:tag=>{const link={tag, clicked:0, click(){link.clicked++;}, remove(){links.removed++;}}; links.push(link); return link;},
    body:{append:()=>{}}},
  window, history, location:{hash:''},
  setInterval:()=>{}, setTimeout:()=>{}, clearTimeout:()=>{},
  fetch:()=>new Promise(()=>{})
});
vm.runInContext(fs.readFileSync(path.join(root, 'shotboard/static/app.js'), 'utf8'), context);
const example = slug => JSON.parse(fs.readFileSync(path.join(root, `examples/${slug}/board.json`), 'utf8'));
const reviews = slug => JSON.parse(fs.readFileSync(path.join(root, `examples/${slug}/continuity-review.json`), 'utf8'));

// Images: lazy and async by default, the first one on screen eager and high priority; alt text escaped.
let tag = vm.runInContext(`img('/api/x.png','<b>Cut</b> "a"',SIZES.card)`, context);
assert.match(tag, /src="\/api\/x\.png"/);
assert.match(tag, /loading="lazy"/);
assert.match(tag, /decoding="async"/);
assert.doesNotMatch(tag, /srcset|fetchpriority/);
assert.match(tag, /alt="&lt;b&gt;Cut&lt;\/b&gt; &quot;a&quot;"/);
tag = vm.runInContext(`img('/api/x.png','Cut',SIZES.cover,true)`, context);
assert.match(tag, /fetchpriority="high"/);
assert.doesNotMatch(tag, /loading=/);
// The static viewer hands back sized copies; the original stays out of src and srcset.
window.SB = {sized: url => ({src:url.replace('.png','-800.webp'), srcset:`${url.replace('.png','-400.webp')} 400w, ${url.replace('.png','-800.webp')} 800w`})};
tag = vm.runInContext(`img('/api/x.png','Cut',SIZES.hero)`, context);
assert.match(tag, /src="\/api\/x-800\.webp" srcset="\/api\/x-400\.webp 400w, \/api\/x-800\.webp 800w" sizes="96px"/);
assert.doesNotMatch(tag, /x\.png/);
// A portrait still in a contain-fit card shows narrower than the card, so it asks for less width.
window.SB.sized = url => ({src:'p-400.webp', srcset:'p-400.webp 400w, p-768.webp 768w', width:768, height:1024});
tag = vm.runInContext(`img('/api/p.png','Cut',SIZES.card,false,SLOT.card)`, context);
assert.match(tag, /sizes="\(max-width:600px\) calc\(calc\(50vw - 22px\) \* 0\.56\), \(max-width:1100px\) calc\(calc\(33vw - 30px\) \* 0\.56\), calc\(320px \* 0\.56\)"/);
tag = vm.runInContext(`img('/api/p.png','Cut',SIZES.thumb)`, context);
assert.match(tag, /sizes="\(max-width:600px\) 150px, 160px"/, 'Cover-fit slots keep their sizes');
window.SB.sized = url => ({src:'w-800.webp', srcset:'w-800.webp 800w', width:1216, height:704});
assert.match(vm.runInContext(`img('/api/w.png','Cut',SIZES.card,false,SLOT.card)`, context), /sizes="\(max-width:600px\) calc\(50vw - 22px\), /, 'Wide stills fill the width');
delete window.SB;

// Board: first card image is the priority, the rest lazy; the legend names the hero when there is one.
const continuity = example('greenhouse-continuity');
continuity.review = reviews('greenhouse-continuity');
context.fixture = continuity;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
const cards = element('board-grid').innerHTML.split('<article').slice(1);
assert.equal(cards.length, continuity.shots.length);
assert.match(cards[0], /fetchpriority="high"/);
for (const card of cards.slice(1)) assert.doesNotMatch(card, /fetchpriority/);
assert.equal((element('board-grid').innerHTML.match(/fetchpriority/g) || []).length, 1);
assert.equal(element('review-legend').hidden, false);
assert.equal(element('review-legend').innerHTML, 'Checked against the hero, <span class="slate">02</span> Medium.');
continuity.continuity.enabled = false;
vm.runInContext('lastSignature=""; render();', context);
assert.equal(element('review-legend').hidden, true, 'No hero sentence once continuity is off');
continuity.continuity.enabled = true;
const hangar = example('hangar');
hangar.review = reviews('hangar');
context.fixture = hangar;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
assert.equal(element('review-legend').hidden, true, 'Verdicts against the prompt need no note');
hangar.review = hangar.review.map(r => ({...r, verdict:'pending'}));
vm.runInContext('lastSignature=""; render();', context);
assert.equal(element('review-legend').hidden, true, 'No legend without a verdict');

// Compare: each finished take image is a button that enlarges it; Imported reference keeps its label.
context.fixture = continuity;
window.SB = {sized: url => ({src:url.replace('.png','-800.webp'), srcset:`${url.replace('.png','-1200.webp')} 1200w`})};
vm.runInContext('board=fixture; currentShot="s02"; renderCompare();', context);
delete window.SB;
const compare = element('compare-images').innerHTML;
assert.match(compare, /<button class="take-zoom" data-zoom="t01" aria-label="Enlarge Medium t01"><img src="[^"]*s02-t01-800\.webp" srcset="[^"]*" sizes="[^"]*960px"/);
assert.match(compare, /Imported reference/);
assert.doesNotMatch(compare, /fig-hero/, 'The hero cut is not compared with itself');
assert.equal((compare.match(/fetchpriority/g) || []).length, 1);

// A reference edit is shown beside the hero it was drawn from; the strip shows every take and which one is picked.
window.SB = {sized: url => ({src:url.replace('.png','-800.webp'), srcset:`${url.replace('.png','-1200.webp')} 1200w`})};
vm.runInContext('currentShot="s04"; viewing.clear(); renderCompare();', context);
delete window.SB;
const s04 = element('compare-images').innerHTML;
assert.match(s04, /fig-hero[\s\S]*<b>Hero<\/b><span><span class="setup-no">02<\/span> Medium · Imported reference<\/span>[\s\S]*fig-take/);
assert.match(s04, /data-zoom="t04" aria-label="Enlarge Over shoulder t04"><img[^>]*sizes="[^"]*480px"/);
const strip = element('take-strip').innerHTML;
assert.equal((strip.match(/<button class="take/g) || []).length, 6);
assert.match(strip, /data-view="t04" aria-pressed="true" aria-label="T04, picked, fail"/);
assert.equal((strip.match(/aria-pressed="true"/g) || []).length, 1);
assert.match(element('render-details').innerHTML, /<dt>Seed<\/dt><dd>20261074 <span class="locked">/);
// Viewing another take keeps the pick and survives a rerender; the lock only shows on the locked seed.
vm.runInContext('viewing.set(`${board.id}/s04`,"t01"); lastSignature=""; render(); renderCompare();', context);
assert.match(element('take-strip').innerHTML, /data-view="t01" aria-pressed="true"/);
assert.match(element('pick-take').innerHTML, /Pick <span class="take-no">T01<\/span>/);
assert.doesNotMatch(element('render-details').innerHTML, /Locked/);
vm.runInContext('viewing.clear();', context);
// Board labels come from each take: one imported hero, five reference edits drawn from it.
vm.runInContext('lastSignature=""; render();', context);
const grid = element('board-grid').innerHTML;
assert.equal((grid.match(/Imported reference/g) || []).length, 1);
assert.equal((grid.match(/Redrawn from <span class="slate">02<\/span>/g) || []).length, 5);
assert.equal((grid.match(/class="shot-card picked is-hero"/g) || []).length, 1);
assert.match(element('hero-line').innerHTML, /Reference edits for<\/span> <span class="branch-nos">01, 03–06<\/span>/);
assert.equal(vm.runInContext('setupRanges([0,1,3,5,6,7])', context), '01, 02, 04, 06–08');
context.fixture = hangar;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
assert.doesNotMatch(element('board-grid').innerHTML, /Redrawn|Imported|is-hero/, 'A board without a hero claims no reference edits');
assert.doesNotMatch(element('board-grid').innerHTML, /cut-src/, 'A board of SDXL takes keeps no empty source rows');
hangar.continuity = {enabled:true, hero:{shot_id:'s01', take_id:hangar.shots[0].picked, seed:1, settings:{}}};
vm.runInContext('lastSignature=""; render();', context);
assert.equal((element('board-grid').innerHTML.match(/<p class="cut-src"><b>Hero<\/b><\/p>/g) || []).length, 1, 'An SDXL hero before any reference edit is named Hero alone');
assert.equal((element('board-grid').innerHTML.match(/<p class="cut-src"><\/p>/g) || []).length, 5, 'The other cards keep the row so the titles line up');
hangar.continuity = {enabled:false};
vm.runInContext('lastSignature=""; render();', context);
assert.match(element('hero-line').innerHTML, /No hero yet/);
context.fixture = continuity;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
// Disabled controls say why: export waits for every pick; the hero cut keeps its takes; no hero means no status line.
assert.equal(element('export-hint').textContent, '');
const firstPick = continuity.shots[0].picked;
continuity.shots[0].picked = null;
vm.runInContext('lastSignature=""; render();', context);
assert.equal(element('storyboard').disabled, true);
assert.equal(element('export-hint').textContent, 'Pick a take in every cut to export.');
continuity.shots[0].picked = firstPick;
vm.runInContext('lastSignature=""; render(); currentShot="s02"; renderCompare();', context);
assert.equal(element('more-takes').disabled, true);
assert.equal(element('takes-reason').hidden, false);
assert.equal(element('takes-reason').textContent, 'The hero cut keeps its takes.');
vm.runInContext('currentShot="s04"; renderCompare();', context);
assert.equal(element('takes-reason').hidden, true);
assert.equal(element('more-takes').textContent, 'Render more takes');
const s04takes = continuity.shots[3].takes; continuity.shots[3].takes = [];
vm.runInContext('renderCompare();', context);
assert.equal(element('more-takes').textContent, 'Render takes', 'No "more" before the first take');
assert.equal(element('render-box').hidden, true, 'No empty Render details');
continuity.shots[3].takes = [{...s04takes[0], id:'t09', status:'failed'}];
vm.runInContext('viewing.clear(); renderCompare();', context);
assert.equal(element('pick-take').disabled, true);
assert.match(element('pick-take').innerHTML, /T09<\/span> failed$/, 'A failed take is named, not offered as a pick');
assert.equal(element('pick-reason').hidden, false);
assert.equal(element('pick-reason').textContent, 'Render more takes for this cut.', 'Only an action this screen has');
continuity.shots[3].takes = [{...s04takes[0], id:'t09', status:'interrupted'}];
vm.runInContext('viewing.clear(); renderCompare();', context);
assert.equal(element('pick-reason').textContent, 'Render more takes for this cut.', 'An interrupted take is not said to be rendering');
vm.runInContext('lastSignature=""; render();', context);
assert.match(element('board-grid').innerHTML.split('<article').slice(1)[3], /frame-status">Interrupted</, 'A cut left with an interrupted take says so');
continuity.shots[3].takes = s04takes;
vm.runInContext('renderCompare();', context);
assert.equal(element('render-box').hidden, false);
assert.equal(element('pick-reason').hidden, true, 'No reason once the take on screen can be picked');
assert.equal(element('hero-status').textContent, '', 'The checkbox already shows on or off');
context.fixture = hangar;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
assert.equal(element('hero-status').textContent, '', 'The script column already says there is no hero');
context.fixture = continuity;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
// Export lists the picks and what the ZIP holds.
vm.runInContext('renderExport();', context);
assert.equal(element('zip-summary').textContent, '20 files');
assert.match(element('zip-files').innerHTML, /ComfyUI workflows<\/b><span class="n">10 JSON<\/span><span class="p">workflows\/sNN\.api\.json and sNN\.submitted\.api\.json for 01, 03–06</);
assert.equal((element('export-picks').innerHTML.match(/<li>/g) || []).length, 6);

// Back closes Compare without leaving the board; moving between cuts adds no history.
vm.runInContext('openCompare("s01");', context);
assert.equal(element('compare-dialog').open, true);
assert.equal(history.entries, 2);
vm.runInContext('navigateCut(1); navigateCut(1);', context);
assert.equal(history.entries, 2, 'Cut arrows do not add history');
browserBack();
assert.equal(element('compare-dialog').open, false, 'Back closes Compare');
assert.equal(history.backs, 0, 'Closing by Back does not go back again');
assert.equal(history.entries, 1);
// Closing with ✕ or Esc removes the entry it added, so the next Back leaves the board as before.
vm.runInContext('openCompare("s01");', context);
element('close-compare').onclick(); flush();
assert.equal(history.backs, 1);
assert.equal(history.entries, 1);
// The enlarged image stacks on Compare: Esc on it keeps Compare open, Back then closes Compare.
vm.runInContext('openCompare("s02");', context);
vm.runInContext('openImage(board.shots[1], board.shots[1].takes[0]);', context);
assert.equal(element('image-dialog').open, true);
assert.equal(element('image-full').src, `/api/boards/${continuity.id}/images/${continuity.shots[1].takes[0].image}`);
assert.equal(element('image-title').innerHTML, 'Medium · <span class="take-no">T01</span>');
assert.equal(history.entries, 3);
element('image-dialog').close(); flush();
assert.equal(element('compare-dialog').open, true, 'Esc on the image keeps Compare open');
assert.equal(history.entries, 2);
vm.runInContext('openImage(board.shots[1], board.shots[1].takes[0]);', context);
browserBack();
assert.deepEqual([element('image-dialog').open, element('compare-dialog').open], [false, true], 'Back closes the image first');
browserBack();
assert.equal(element('compare-dialog').open, false);
assert.equal(history.entries, 1);
// Forward into an entry whose dialog is gone steps back again instead of leaving a dead Back press.
const backs = history.backs;
browserForward({dialog:'compare-dialog'});
assert.equal(history.backs, backs + 1);
assert.equal(history.entries, 1);
// The storyboard export is a screen too: Back closes it and stays on the board.
element('storyboard').onclick();
assert.equal(element('storyboard-dialog').open, true);
assert.equal(history.entries, 2);
browserBack();
assert.equal(element('storyboard-dialog').open, false, 'Back closes the storyboard');
assert.equal(history.entries, 1);
element('storyboard').onclick(); element('close-storyboard').onclick(); flush();
assert.equal(history.entries, 1, 'Closing it removes its entry');
element('image-full').onload();
assert.equal(element('image-full').classList.contains('loaded'), true);
assert.equal(element('image-preview').hidden, true);
// The ZIP is fetched and saved through a link, so the page does not navigate and its polling request is not cancelled;
// a server error or a stopped server is said in a sentence.
(async () => {
  const fetched = [];
  context.URL = {createObjectURL: blob => `blob:${blob}`, revokeObjectURL() {}};
  context.fetch = async url => { fetched.push(url); return {ok: true, blob: async () => 'zip'}; };
  await element('export').onclick();
  assert.deepEqual(fetched, [`/api/boards/${continuity.id}/export`]);
  assert.deepEqual([links.at(-1).tag, links.at(-1).href, links.at(-1).download, links.at(-1).clicked, links.removed], ['a', 'blob:zip', 'shot-board.zip', 1, 1]);
  assert.equal(context.location.href, undefined, 'No navigation');
  assert.equal(element('toast').textContent, 'shot-board.zip is ready.');
  assert.deepEqual([!!element('export').disabled, element('export').ariaDisabled], [false, null]);
  context.fetch = async () => ({ok: false, json: async () => ({detail: 'Pick one completed take for every cut before exporting.'})});
  await element('export').onclick();
  assert.equal(element('toast').textContent, 'Pick one completed take for every cut before exporting.');
  context.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await element('export').onclick();
  assert.equal(element('toast').textContent, 'The local Shot Board server is not answering. Start it again, then reload the page.');
  await vm.runInContext('api("/boards")', context).then(() => assert.fail('should throw'), error => assert.equal(error.message, 'The local Shot Board server is not answering. Start it again, then reload the page.'));
  // While the ZIP is made the button keeps keyboard focus: it is marked aria-disabled, not disabled, and a second press sends nothing.
  let release; fetched.length = 0;
  context.fetch = url => { fetched.push(url); return new Promise(resolve => { release = () => resolve({ok: true, blob: async () => 'zip'}); }); };
  const pending = element('export').onclick();
  assert.deepEqual([!!element('export').disabled, element('export').ariaDisabled, element('export').ariaBusy, element('export').textContent], [false, 'true', 'true', 'Preparing ZIP…']);
  await element('export').onclick();
  assert.equal(fetched.length, 1, 'A second press while busy sends nothing');
  release(); await pending;
  assert.deepEqual([element('export').ariaDisabled, element('export').ariaBusy], [null, null]);
  // A list-shaped detail is not printed as [object Object].
  context.fetch = async () => ({ok: false, json: async () => ({detail: [{msg: 'field required'}]})});
  await element('export').onclick();
  assert.equal(element('toast').textContent, 'The ZIP could not be made. Try again.');
  // Render board under a running queue: disabled, unless the keyboard is on it; then it stays focusable and refuses presses.
  const generate = element('generate');
  context.document.activeElement = generate;
  vm.runInContext("hold($('generate'),true)", context);
  assert.deepEqual([generate.disabled, generate.ariaDisabled], [false, 'true']);
  fetched.length = 0; context.fetch = async url => { fetched.push(url); return {ok: true, json: async () => ({})}; };
  await generate.onclick();
  assert.equal(fetched.length, 0, 'A held Render board sends nothing');
  context.document.activeElement = null;
  vm.runInContext("hold($('generate'),true)", context);
  assert.deepEqual([generate.disabled, generate.ariaDisabled], [true, null]);
  vm.runInContext("hold($('generate'),false)", context);
  assert.deepEqual([generate.disabled, generate.ariaDisabled], [false, null]);
  console.log('Board UI: lazy and priority images, review legend, enlarged view, Back, ZIP download and busy focus passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
