const $ = (id) => document.getElementById(id);
let board = null, currentShot = null, editing = false, lastSignature = '', polling = false;
const choices = {lens:'35', angle:'Eye level', move:'Static', lighting:'Window light', look:'Muted film'};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const busy = () => board?.shots.some(s => s.takes.some(t => ['queued','running'].includes(t.status)));
const imageURL = (take) => `/api/boards/${board.id}/images/${take.image}`;
function toast(message) { $('toast').textContent=message; $('toast').hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>$('toast').hidden=true,6000); }
async function api(path, method='GET', data) {
  const response=await fetch('/api'+path,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  if(!response.ok){let error=await response.json().catch(()=>({detail:'Local server unavailable'}));throw new Error(typeof error.detail==='string'?error.detail:'Please check your inputs.');}
  return response.json();
}
function guarded(fn) { return async (...args) => {try{await fn(...args);}catch(error){toast(error.message);}}; }
function chips(config) {
  for(const [key, values] of Object.entries(config)) {
    if(!Object.hasOwn(choices,key))continue;
    let row=document.createElement('div');row.className='chip-row';row.innerHTML=`<span class="chip-label">${{lens:'LENS',angle:'ANGLE',move:'MOVE',lighting:'LIGHT',look:'FILM LOOK'}[key]}</span>`;
    values.forEach(value=>{let button=document.createElement('button');button.type='button';button.textContent=key==='lens'?value+' mm':value;button.className='chip'+(choices[key]===value?' active':'');button.setAttribute('aria-pressed',choices[key]===value);button.onclick=()=>{choices[key]=value;row.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button);});};row.append(button);});
    (['lens','angle','move'].includes(key)?$('camera-chips'):$('look-chips')).append(row);
  }
}
function allTakes(){return board.shots.flatMap(s=>s.takes);}
function render() {
  if(!board)return;
  $('composer').hidden=true;$('workspace').hidden=false;
  $('board-title').textContent=board.title;
  $('board-meta').textContent=`${board.shots.length} cuts  /  ${board.config.lens} mm  /  ${board.config.lighting}  /  ${board.config.look}  /  SDXL Base 1.0`;
  const picked=board.shots.filter(s=>s.picked).length, takes=allTakes(), completed=takes.filter(t=>t.status==='succeeded').length;
  $('pick-count').textContent=`${picked} / ${board.shots.length} selected`;
  $('export').disabled=picked!==board.shots.length;
  $('generate').disabled=busy();$('cancel').hidden=!busy();
  $('generate').textContent=takes.length?'▶ Render more takes':'▶ Render board';
  $('queue-panel').hidden=!takes.length;
  const running=takes.find(t=>t.status==='running'),queued=takes.filter(t=>t.status==='queued').length,failed=takes.filter(t=>['failed','interrupted','cancelled'].includes(t.status)).length;
  $('queue-status').textContent=busy()?`${completed} / ${takes.length} takes ready · ${queued} queued`:`${completed} / ${takes.length} takes ready${failed?' · '+failed+' stopped':''}`;
  $('queue-detail').textContent=running?`${running.phase} · ${Math.floor((Date.now()/1000)-running.started_at)}s elapsed`:busy()?'Waiting for local worker':failed?'Review stopped takes before retrying':'Local rendering complete';
  $('queue-progress').max=takes.length||1;$('queue-progress').value=completed;
  const signature=JSON.stringify(board.shots.map(s=>[s.title,s.prompt,s.picked,s.locked_seed,s.takes.map(t=>[t.id,t.status,t.image,t.error])]));
  if(signature!==lastSignature){
    lastSignature=signature;
    $('board-grid').innerHTML=board.shots.map((s,i)=>{
      const ready=s.takes.filter(t=>t.status==='succeeded'),hero=ready.find(t=>t.id===s.picked)||ready[0];
      const active=s.takes.find(t=>t.status==='running');
      return `<article class="shot-card ${s.picked?'picked':''}"><div class="shot-label"><h3><b>${String(i+1).padStart(2,'0')}</b>${escapeHTML(s.title)}</h3><span class="pill">${s.picked?'✓ SELECTED':'COVERAGE'}</span></div><div class="shot-hero" tabindex="0" role="button" aria-label="Compare ${escapeHTML(s.title)}" data-compare="${s.id}">${hero?`<img src="${imageURL(hero)}" alt="${escapeHTML(s.title)} ${hero.id}">`:`<span class="empty-frame">${String(i+1).padStart(2,'0')}</span>`}<span class="frame-status">${hero?(s.picked?'SELECT / ':'PREVIEW / ')+hero.id.toUpperCase():active?'RENDERING LOCALLY':s.takes.some(t=>t.status==='queued')?'IN THE QUEUE':s.takes.some(t=>t.status==='failed')?'RENDER FAILED · RETRY':'AWAITING FIRST TAKE'}</span></div><div class="take-strip">${s.takes.map(t=>`<button class="take-thumb ${s.picked===t.id?'selected':''}" data-compare="${s.id}" aria-label="Compare ${s.title} ${t.id}">${t.status==='succeeded'?`<img src="${imageURL(t)}" alt="${t.id}">`:t.status==='running'?'…':t.status==='queued'?t.id:escapeHTML(t.status)}</button>`).join('') || '<small class="muted">Two takes. A little room to explore.</small>'}<span class="take-count">${ready.length} TAKES</span></div><div class="card-bottom"><small>${s.locked_seed!==null?'▣ SEED LOCKED':'SHARED SEED FAMILY'}</small><button data-compare="${s.id}">Compare & pick ↗</button></div></article>`;
    }).join('');
    document.querySelectorAll('[data-compare]').forEach(el=>{el.onclick=()=>openCompare(el.dataset.compare);el.onkeydown=e=>{if(e.key==='Enter')openCompare(el.dataset.compare);};});
    if($('compare-dialog').open)renderCompare();
  }
}
async function refresh() {if(board){board=await api('/boards/'+board.id);render();}}
async function openBoard(id){board=await api('/boards/'+id);location.hash=id;lastSignature='';editing=false;$('shot-list').hidden=true;$('board-grid').hidden=false;render();}
function renderCompare(){
  const s=board.shots.find(s=>s.id===currentShot);if(!s)return;
  $('compare-title').textContent=s.title;
  $('compare-images').innerHTML=s.takes.length?s.takes.map(t=>`<div class="compare-take ${s.picked===t.id?'chosen':''}">${t.status==='succeeded'?`<img src="${imageURL(t)}" alt="${escapeHTML(s.title)} ${t.id}">`:'<div class="shot-hero"><span class="empty-frame">'+escapeHTML(t.status)+'</span></div>'}<div><div><strong>${t.id.toUpperCase()}${s.picked===t.id?' · SELECTED':''}</strong><small>SEED ${t.seed} · ${t.elapsed_seconds||0}s · ${escapeHTML(t.status)}</small>${t.error?`<small>${escapeHTML(t.error)}</small>`:''}</div><button class="${s.picked===t.id?'primary':'quiet'}" data-pick="${t.id}" ${t.status!=='succeeded'?'disabled':''}>${s.picked===t.id?'✓ Selected':'Pick this take'}</button></div></div>`).join(''):'<p class="muted">No takes yet. Render this cut to start comparing.</p>';
  document.querySelectorAll('[data-pick]').forEach(el=>el.onclick=guarded(async()=>{await api(`/boards/${board.id}/shots/${s.id}/pick`,'POST',{take_id:el.dataset.pick});await refresh();$('reuse-seed').value=board.shots.find(x=>x.id===s.id).takes.find(t=>t.id===el.dataset.pick).seed;}));
  $('seed-lock').textContent=s.locked_seed!==null?'Unlock seed':'Lock seed';
  $('seed-lock').disabled=!s.takes.some(t=>t.status==='succeeded');
  $('more-takes').disabled=busy();$('reframe').disabled=!s.picked;
  $('compare-message').textContent=s.locked_seed!==null?`Seed ${s.locked_seed} locked. New takes reuse this seed; edit the shot prompt to explore a change.`:'Pick a take, then lock its seed to reuse it. You can also enter a seed manually.';
}
function openCompare(id){currentShot=id;renderCompare();const s=board.shots.find(s=>s.id===id),t=s.takes.find(t=>t.id===s.picked)||s.takes.find(t=>t.status==='succeeded');$('reuse-seed').value=s.locked_seed??t?.seed??board.config.seed;if(!$('compare-dialog').open)$('compare-dialog').showModal();}
function showEditors(){
  $('shot-list').innerHTML=board.shots.map(s=>`<div class="shot-editor"><div><label>Cut title<input id="title-${s.id}" value="${escapeHTML(s.title)}"></label><button data-save="${s.id}">Save cut</button></div><div><label>Prompt<textarea id="prompt-${s.id}">${escapeHTML(s.prompt)}</textarea></label><label>Negative prompt<input class="editor-negative" id="negative-${s.id}" value="${escapeHTML(s.negative)}"></label></div></div>`).join('');
  document.querySelectorAll('[data-save]').forEach(button=>button.onclick=guarded(async()=>{const s=button.dataset.save;await api(`/boards/${board.id}/shots/${s}`,'PATCH',{title:$('title-'+s).value,prompt:$('prompt-'+s).value,negative:$('negative-'+s).value});await refresh();toast('Cut saved. Existing takes keep their original settings.');}));
}
$('scene-form').onsubmit=guarded(async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));Object.assign(data,choices,{seed:Number(data.seed),count:Number(data.count)});const created=await api('/boards','POST',data);await openBoard(created.id);});
$('generate').onclick=guarded(async()=>{const button=$('generate');button.disabled=true;try{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value)});await refresh();}finally{button.disabled=busy();}});
$('more-takes').onclick=guarded(async()=>{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value),shot_id:currentShot});await refresh();});
$('cancel').onclick=guarded(async()=>{await api(`/boards/${board.id}/cancel`,'POST',{});await refresh();});
$('seed-lock').onclick=guarded(async()=>{const s=board.shots.find(x=>x.id===currentShot);const seed=s.locked_seed!==null?null:Number($('reuse-seed').value);await api(`/boards/${board.id}/shots/${s.id}/seed`,'POST',{seed});await refresh();});
$('reframe').onclick=guarded(async()=>{const result=await api(`/boards/${board.id}/shots/${currentShot}/reframe`,'POST',{});toast(result.message);});
$('export').onclick=()=>{location.href=`/api/boards/${board.id}/export`;};
$('close-compare').onclick=()=>$('compare-dialog').close();$('close-boards').onclick=()=>$('boards-dialog').close();
$('edit-toggle').onclick=()=>{editing=!editing;$('shot-list').hidden=!editing;$('board-grid').hidden=editing;$('edit-toggle').textContent=editing?'Return to board':'Edit shot list';if(editing)showEditors();};
$('board-tab').onclick=()=>{editing=false;$('shot-list').hidden=true;$('board-grid').hidden=false;$('edit-toggle').textContent='Edit shot list';};
$('new-board').onclick=()=>{board=null;location.hash='';$('composer').hidden=false;$('workspace').hidden=true;};
$('load-example').onclick=guarded(async()=>{const boards=await api('/boards');$('boards-list').innerHTML=boards.map(b=>`<button class="board-link" data-board="${b.id}">${escapeHTML(b.title)} ↗</button>`).join('')||'<p class="muted">Your first scene starts here. Build a shot list to begin.</p>';document.querySelectorAll('[data-board]').forEach(b=>b.onclick=guarded(async()=>{await openBoard(b.dataset.board);$('boards-dialog').close();}));$('boards-dialog').showModal();});
async function health(){try{const h=await api('/health');$('connection').textContent=h.proxy_ready&&h.checkpoint_present?'Local engine ready':!h.checkpoint_present?'SDXL setup needed':'Local engine offline';}catch{$('connection').textContent='Local server unavailable';}}
guarded(async()=>{chips(await api('/config'));await health();if(location.hash.length>1)await openBoard(location.hash.slice(1));})();
setInterval(async()=>{if(polling)return;polling=true;try{await refresh();}catch{}finally{polling=false;}},1600);setInterval(health,15000);
