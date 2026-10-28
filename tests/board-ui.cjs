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
const queue = [], listeners = {}, history = {entries:1, backs:0, state:null,
  pushState(state){history.entries++; history.state=state;},
  replaceState(state){history.state=state;},
  back(){history.backs++; history.entries--; queue.push(()=>listeners.popstate());}};
const flush = () => { while (queue.length) queue.shift()(); };
const browserBack = () => { history.entries--; listeners.popstate(); flush(); };
const window = {addEventListener:(type, fn)=>{listeners[type]=fn;}, history};
const context = vm.createContext({
  document:{getElementById:element, querySelectorAll:()=>[], addEventListener:()=>{}},
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
tag = vm.runInContext(`img('/api/x.png','Cut',SIZES.thumb)`, context);
assert.match(tag, /src="\/api\/x-800\.webp" srcset="\/api\/x-400\.webp 400w, \/api\/x-800\.webp 800w" sizes="64px"/);
assert.doesNotMatch(tag, /x\.png/);
// A portrait still in a contain-fit card shows narrower than the card, so it asks for less width.
window.SB.sized = url => ({src:'p-400.webp', srcset:'p-400.webp 400w, p-768.webp 768w', width:768, height:1024});
tag = vm.runInContext(`img('/api/p.png','Cut',SIZES.card,false,SLOT.card)`, context);
assert.match(tag, /sizes="\(max-width:600px\) calc\(calc\(100vw - 32px\) \* 0\.65\), \(max-width:1100px\) calc\(calc\(50vw - 52px\) \* 0\.65\), calc\(440px \* 0\.65\)"/);
tag = vm.runInContext(`img('/api/p.png','Cut',SIZES.thumb)`, context);
assert.match(tag, /sizes="64px"/, 'Cover-fit slots keep their sizes');
window.SB.sized = url => ({src:'w-800.webp', srcset:'w-800.webp 800w', width:1216, height:704});
assert.match(vm.runInContext(`img('/api/w.png','Cut',SIZES.card,false,SLOT.card)`, context), /sizes="\(max-width:600px\) calc\(100vw - 32px\), /, 'Wide stills fill the width');
delete window.SB;

// Board: first card image is the priority, the rest lazy; the legend names the hero when there is one.
const continuity = example('greenhouse-continuity');
continuity.review = reviews('greenhouse-continuity');
context.fixture = continuity;
vm.runInContext('board=fixture; lastSignature=""; render();', context);
const cards = element('board-grid').innerHTML.split('<article').slice(1);
assert.equal(cards.length, continuity.shots.length);
assert.match(cards[0].split('take-strip')[0], /fetchpriority="high"/);
for (const card of cards.slice(1)) assert.doesNotMatch(card, /fetchpriority/);
assert.equal((element('board-grid').innerHTML.match(/fetchpriority/g) || []).length, 1);
assert.equal(element('review-legend').hidden, false);
assert.equal(element('review-legend').textContent, 'Pass and Fail are continuity review results against the hero, 02 Medium.');
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
assert.match(compare, /<button class="take-zoom" data-zoom="t01" aria-label="Enlarge Medium t01"><img src="[^"]*s02-t01-800\.webp" srcset="[^"]*" sizes="[^"]*640px"/);
assert.match(compare, /Imported reference/);

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
element('image-full').onload();
assert.equal(element('image-full').classList.contains('loaded'), true);
assert.equal(element('image-preview').hidden, true);
console.log('Board UI: lazy and priority images, review legend, enlarged view and Back passed.');
