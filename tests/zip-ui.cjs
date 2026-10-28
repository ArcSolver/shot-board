// Prints the ZIP file list the export screen shows for each example board, for test_ui.py to check against export_board.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const elements = new Map();
const element = id => { if (!elements.has(id)) elements.set(id, {dataset:{}, value:'', hidden:false}); return elements.get(id); };
const context = vm.createContext({
  document:{getElementById:element, querySelectorAll:()=>[], addEventListener:()=>{}},
  window:{addEventListener:()=>{}}, location:{hash:''},
  setInterval:()=>{}, setTimeout:()=>{}, clearTimeout:()=>{}, fetch:()=>new Promise(()=>{})
});
vm.runInContext(fs.readFileSync(path.join(root, 'shotboard/static/app.js'), 'utf8'), context);
const out = {};
for (const slug of process.argv.slice(2)) {
  context.fixture = JSON.parse(fs.readFileSync(path.join(root, `examples/${slug}/board.json`), 'utf8'));
  out[slug] = vm.runInContext('zipFiles(fixture)', context);
}
process.stdout.write(JSON.stringify(out));
