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
assert.equal(element('review-legend').textContent, 'Pass and Fail are continuity review results against the hero, 02 Medium.');
continuity.continuity.enabled = false;
vm.runInContext('lastSignature=""; render();', context);
assert.equal(element('review-legend').textContent, "Pass and Fail are review results against each cut's prompt.", 'No hero sentence once continuity is off');
continuity.continuity.enabled = true;
const hangar = example('hangar');
hangar.review = reviews('hangar');
context.fixture = hangar;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
assert.equal(element('review-legend').textContent, "Pass and Fail are review results against each cut's prompt.");
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
assert.match(s04, /fig-hero[\s\S]*<b>Hero<\/b><span>02 Medium · Imported reference<\/span>[\s\S]*fig-take/);
assert.match(s04, /data-zoom="t04" aria-label="Enlarge Over shoulder t04"><img[^>]*sizes="[^"]*480px"/);
const strip = element('take-strip').innerHTML;
assert.equal((strip.match(/<button class="take/g) || []).length, 6);
assert.match(strip, /data-view="t04" aria-pressed="true" aria-label="T04, picked, fail"/);
assert.equal((strip.match(/aria-pressed="true"/g) || []).length, 1);
assert.match(element('render-details').innerHTML, /<dt>Seed<\/dt><dd>20261074 <span class="locked">/);
// Viewing another take keeps the pick and survives a rerender; the lock only shows on the locked seed.
vm.runInContext('viewing.set(`${board.id}/s04`,"t01"); lastSignature=""; render(); renderCompare();', context);
assert.match(element('take-strip').innerHTML, /data-view="t01" aria-pressed="true"/);
assert.match(element('pick-take').innerHTML, /Pick T01/);
assert.doesNotMatch(element('render-details').innerHTML, /Locked/);
vm.runInContext('viewing.clear();', context);
// Board labels come from each take: one imported hero, five reference edits drawn from it.
vm.runInContext('lastSignature=""; render();', context);
const grid = element('board-grid').innerHTML;
assert.equal((grid.match(/Imported reference/g) || []).length, 1);
assert.equal((grid.match(/Redrawn from 02/g) || []).length, 5);
assert.equal((grid.match(/class="shot-card picked is-hero"/g) || []).length, 1);
assert.match(element('hero-line').innerHTML, /Reference edits for<\/span> <span class="branch-nos">01, 03–06<\/span>/);
assert.equal(vm.runInContext('setupRanges([0,1,3,5,6,7])', context), '01, 02, 04, 06–08');
context.fixture = hangar;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
assert.doesNotMatch(element('board-grid').innerHTML, /Redrawn|Imported|is-hero/, 'A board without a hero claims no reference edits');
assert.match(element('hero-line').innerHTML, /No hero yet/);
context.fixture = continuity;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
// Export lists the picks and what the ZIP holds.
vm.runInContext('renderExport();', context);
assert.equal(element('zip-summary').textContent, '20 files · all 6 cuts picked');
assert.match(element('zip-files').innerHTML, /ComfyUI workflows<\/b><span class="n">10 JSON<\/span><span class="p">workflows\/sNN\.api\.json for 01, 03–06, plus 5 as submitted/);
assert.match(element('zip-note').textContent, /^Cut 02 is an imported reference, so it has no workflow\./);
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
assert.equal(element('image-title').textContent, 'Medium · T01');
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
// The ZIP downloads through a link, so the page does not navigate and its polling request is not cancelled.
element('export').onclick();
assert.deepEqual([links.at(-1).tag, links.at(-1).href, links.at(-1).download, links.at(-1).clicked, links.removed],
                 ['a', `/api/boards/${continuity.id}/export`, 'shot-board.zip', 1, 1]);
assert.equal(context.location.href, undefined, 'No navigation');
element('image-full').onload();
assert.equal(element('image-full').classList.contains('loaded'), true);
assert.equal(element('image-preview').hidden, true);
console.log('Board UI: lazy and priority images, review legend, enlarged view and Back passed.');
