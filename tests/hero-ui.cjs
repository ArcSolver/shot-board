const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => {
  if (!elements.has(id)) elements.set(id, {dataset:{}, value:'', hidden:false});
  return elements.get(id);
};
const requests = [];
const context = vm.createContext({
  document:{getElementById:element, querySelectorAll:()=>[], addEventListener:()=>{}},
  window:{addEventListener:()=>{}}, location:{hash:''},
  setInterval:()=>{}, setTimeout:()=>{}, clearTimeout:()=>{},
  fetch:(...args)=>{requests.push(args); return new Promise(()=>{});}
});
vm.runInContext(fs.readFileSync(path.join(root, 'shotboard/static/app.js'), 'utf8'), context);
const board = JSON.parse(fs.readFileSync(path.join(root, 'examples/greenhouse-continuity/board.json'), 'utf8'));
board.continuity.enabled = false;
const referenceTake = board.shots[0].takes.find(t=>t.reference);
assert.ok(referenceTake, 'Example includes a real reference edit');
board.shots[0].picked = referenceTake.id;
context.referenceId = referenceTake.id;
context.fixture = board;
vm.runInContext('board=fixture; currentShot="s01"; renderCompare();', context);
assert.equal(element('use-hero').disabled, true);
(async()=>{
  requests.length = 0;
  await element('use-hero').onclick();
  assert.equal(requests.length, 0);
  assert.match(element('toast').textContent, /Pick an SDXL take or an imported reference, then use the pick as hero/);
  const sdxl = {...board.shots[1].takes[0], id:'sdxl-fixture', source:undefined, reference:null, seed:0, settings:{checkpoint:'sd_xl_base_1.0.safetensors',preset_id:'sdxl-base',width:768,height:576},workflow:{'1':{class_type:'CheckpointLoaderSimple'}}};
  board.shots[1].takes.push(sdxl);board.shots[1].picked=sdxl.id;
  vm.runInContext('currentShot="s02"; renderCompare();', context);
  assert.equal(element('use-hero').disabled, false);
  assert.equal(element('hero-reason').hidden, true, 'No reason while the pick is on screen');
  // The button acts on the pick, so with another take on screen it names the take it will use.
  vm.runInContext('viewing.set(viewKey(board.shots[1]), board.shots[1].takes[0].id); renderCompare();', context);
  assert.equal(element('use-hero').disabled, false);
  assert.equal(element('hero-reason').hidden, false);
  assert.match(element('hero-reason').textContent, /This uses the pick, SDXL-FIXTURE\./);
  vm.runInContext('viewing.delete(viewKey(board.shots[1])); renderCompare();', context);
  const imported = {id:'t16',status:'succeeded',seed:null,image:'imported.png',source:{type:'imported'},settings:{preset_id:'imported-reference',label:'Imported reference',width:768,height:576},workflow:{},models:[]};
  board.shots[1].takes.push(imported); board.shots[1].picked=imported.id;
  vm.runInContext('renderCompare();', context);
  assert.equal(element('use-hero').disabled,false);
  board.shots[1].locked_seed=null; vm.runInContext('renderCompare();', context);
  assert.equal(element('seed-lock').disabled,true);
  assert.equal(element('reuse-seed').disabled,true);
  element('reuse-seed').value='';requests.length=0;
  await element('seed-lock').onclick();
  assert.equal(requests.length,0,'No invented seed from an imported image');
  board.shots[1].locked_seed=0;vm.runInContext('renderCompare();', context);
  assert.equal(element('seed-lock').disabled,false,'Existing seed can still be unlocked');
  const mixed=board.shots[1].takes;board.shots[1].takes=[imported];
  vm.runInContext('renderCompare();', context);
  assert.equal(element('seed-lock').disabled,false,'Imported-only cut can unlock an existing seed');
  board.shots[1].takes=mixed;
  assert.match(element('compare-images').innerHTML,/Imported reference/);
  assert.doesNotMatch(element('compare-images').innerHTML,/SEED null|undefined/);
  vm.runInContext('board.shots[1].picked=null; renderCompare();', context);
  assert.equal(element('use-hero').disabled, true);
  // Keep review fixtures distinct even when every bundled take is a reference edit.
  board.shots[0].takes = [{...referenceTake,id:'review-pass'}, {...referenceTake,id:'review-fail'}];
  context.referenceId='review-fail';
  board.review = [
    {shot:'s01',take:'review-pass',verdict:'pass',note:'<b>Clear</b> "subject"'},
    {shot:'s01',take:'review-fail',verdict:'fail',note:'Too tight'}
  ];
  const verdict = expr => /value="(\w+)" checked>/.exec(vm.runInContext(expr, context))[1];
  assert.equal(verdict('reviewEditor(board.shots[0],board.shots[0].takes.find(t=>t.id===referenceId))'), 'fail');
  vm.runInContext('board.shots[0].picked=null;', context);
  assert.equal(verdict('reviewEditor(board.shots[0],board.shots[0].takes[0])'), 'pass');
  const editor = vm.runInContext('reviewEditor(board.shots[0],board.shots[0].takes[0])', context);
  assert.match(editor, /&lt;b&gt;Clear&lt;\/b&gt; &quot;subject&quot;/);
  assert.doesNotMatch(editor, /<b>Clear<\/b>/);
  assert.match(editor, /Saved<\/span>/);
  vm.runInContext('reviewDrafts.set(`${board.id}/s01/review-pass`,{verdict:"fail",note:"x"});', context);
  assert.match(vm.runInContext('reviewEditor(board.shots[0],board.shots[0].takes[0])', context), /value="fail" checked>[\s\S]*Unsaved changes/, 'A draft shows as unsaved');
  // The take that already is the hero cannot be made the hero again.
  const reloaded = JSON.parse(fs.readFileSync(path.join(root, 'examples/greenhouse-continuity/board.json'), 'utf8'));
  context.fixture = reloaded;
  vm.runInContext('board=fixture; currentShot="s02"; renderCompare();', context);
  assert.equal(element('use-hero').disabled, true);
  assert.match(element('hero-note').textContent, /is the hero/);
  console.log('Hero UI: Qwen disabled and blocked, SDXL enabled, empty pick disabled.');
  console.log('Review UI: verdict follows take, unpicked preview and note escaping passed.');
})().catch(error=>{console.error(error); process.exitCode=1;});
