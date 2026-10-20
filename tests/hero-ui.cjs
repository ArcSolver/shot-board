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
const board = JSON.parse(fs.readFileSync(path.join(root, 'examples/greenhouse-a2/board.json'), 'utf8'));
board.continuity.enabled = false;
context.fixture = board;
vm.runInContext('board=fixture; currentShot="s01"; renderCompare();', context);
assert.equal(element('use-hero').disabled, true);
assert.match(element('hero-rule').textContent, /Only an SDXL original/);
assert.match(element('hero-rule').textContent, /edits are never chained/);
(async()=>{
  requests.length = 0;
  await element('use-hero').onclick();
  assert.equal(requests.length, 0);
  assert.match(element('toast').textContent, /Qwen edits cannot be heroes/);
  vm.runInContext('currentShot="s02"; renderCompare();', context);
  assert.equal(element('use-hero').disabled, false);
  vm.runInContext('board.shots[1].picked=null; renderCompare();', context);
  assert.equal(element('use-hero').disabled, true);
  console.log('Hero UI: Qwen disabled and blocked, SDXL enabled, empty pick disabled.');
})().catch(error=>{console.error(error); process.exitCode=1;});
