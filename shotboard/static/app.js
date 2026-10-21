const HERO_RULE = 'Select an SDXL take to use as the hero.';
function isSDXLOriginal(take) {
  return !!take && take.status==='succeeded' && !take.reference &&
    take.settings?.checkpoint==='sd_xl_base_1.0.safetensors' &&
    (take.settings?.preset_id||'sdxl-base')==='sdxl-base' &&
    take.workflow?.['1']?.class_type==='CheckpointLoaderSimple';
}
const $ = (id) => document.getElementById(id);
let examples = [], board = null, currentShot = null, editing = false, lastSignature = '', polling = false;
const reviewDrafts = new Map();
const choices = {lens:'35', angle:'Eye level', move:'Static', lighting:'Window light', look:'Muted film'};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const busy = () => board?.shots.some(s => s.takes.some(t => ['queued','running'].includes(t.status)));
const imageURL = (take) => `/api/boards/${board.id}/images/${take.image}`;
// The toast is a manual popover so it shows in the top layer, above an open Compare or Storyboard dialog and its backdrop.
// Inside a modal dialog it moves into that dialog, so it is not inert and its status is still announced.
function toast(message) {
  const el=$('toast'), layer=!!el.showPopover, host=document.querySelector?.('dialog[open]')||document.body;
  if(el.parentNode&&el.parentNode!==host){if(layer&&el.matches(':popover-open'))el.hidePopover();host.append(el);}
  el.textContent=message; el.hidden=false;
  if(layer){if(el.matches(':popover-open'))el.hidePopover();el.showPopover();}
  clearTimeout(toast.timer);
  toast.timer=setTimeout(()=>{el.hidden=true;if(layer&&el.matches(':popover-open'))el.hidePopover();},6000);
}
async function api(path, method='GET', data) {
  const response=await fetch('/api'+path,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined});
  if(!response.ok){let error=await response.json().catch(()=>({detail:'Local server unavailable'}));throw new Error(typeof error.detail==='string'?error.detail:'Please check your inputs.');}
  return response.json();
}
function guarded(fn) { return async (...args) => {try{await fn(...args);}catch(error){toast(error.message);}}; }
function chips(config) {
  for(const [key, values] of Object.entries(config)) {
    if(!Object.hasOwn(choices,key))continue;
    let row=document.createElement('div');row.className='chip-row';row.innerHTML=`<span class="chip-label">${{lens:'Lens',angle:'Angle',move:'Move',lighting:'Light',look:'Film look'}[key]}</span>`;
    values.forEach(value=>{let button=document.createElement('button');button.type='button';button.textContent=key==='lens'?value+' mm':value;button.className='chip'+(choices[key]===value?' active':'');button.setAttribute('aria-pressed',choices[key]===value);button.onclick=()=>{choices[key]=value;row.querySelectorAll('button').forEach(b=>{b.classList.toggle('active',b===button);b.setAttribute('aria-pressed',b===button);});};row.append(button);});
    (['lens','angle','move'].includes(key)?$('camera-chips'):$('look-chips')).append(row);
  }
}
function allTakes(){return board.shots.flatMap(s=>s.takes);}
function render() {
  if(!board)return;
  $('home').hidden=true;$('composer').hidden=true;$('workspace').hidden=false;
  const scene=board.config?.scene||'';const title=board.title.trim();$('board-title').textContent=title+(scene.trim().length>title.length&&!/[.!?…]$/.test(title)?'…':'');
  const continuity=board.continuity||{}, heroRef=continuity.hero;
  $('keep-continuity').checked=!!continuity.enabled;
  $('keep-continuity').disabled=busy()||!heroRef;
  $('hero-status').textContent=heroRef?(continuity.enabled?'On · other cuts render as Qwen reference edits':'Off'):'No hero yet';
  const picked=board.shots.filter(s=>s.picked).length, takes=allTakes(), completed=takes.filter(t=>t.status==='succeeded').length;
  const allPicked=picked===board.shots.length, ready=s=>s.takes.some(t=>t.status==='succeeded');
  const needsRender=board.shots.some(s=>!ready(s))||(!!continuity.enabled&&board.shots.some(s=>s.id!==heroRef?.shot_id&&!s.takes.some(t=>t.reference&&t.status==='succeeded')));
  $('export').disabled=!allPicked;$('storyboard').disabled=!allPicked;
  $('storyboard').className=allPicked?'primary':'quiet';
  $('generate').disabled=busy();$('cancel').hidden=!busy();
  $('generate').className=needsRender&&!allPicked?'primary':'quiet';
  $('generate').textContent=board.continuity?.enabled?'Render reference edits':takes.length?'Render more takes':'Render board';
  $('pick-count').textContent=`${picked} of ${board.shots.length} picked`;
  $('pick-meter').innerHTML=board.shots.map(s=>`<i class="${s.picked?'on':''}"></i>`).join('');
  $('queue-panel').hidden=!busy();
  const running=takes.find(t=>t.status==='running'),queued=takes.filter(t=>t.status==='queued').length;
  $('queue-status').textContent=`${completed} / ${takes.length} takes ready · ${queued} queued`;
  $('queue-detail').textContent=running?`${running.phase} · ${Math.floor((Date.now()/1000)-running.started_at)}s elapsed`:'Waiting for the worker';
  $('queue-progress').max=takes.length||1;$('queue-progress').value=completed;
  $('recipe-label').textContent=heroRef?`Hero ${heroRef.shot_id.toUpperCase()} / ${heroRef.take_id.toUpperCase()} · ${heroRef.settings.label}`:'SDXL Base 1.0';
  $('recipe-detail').textContent=heroRef?`${heroRef.settings.steps} steps · seed ${heroRef.seed}`:'20 steps';
  const signature=JSON.stringify([board.continuity,board.review,board.shots.map(s=>[s.title,s.prompt,s.picked,s.locked_seed,s.takes.map(t=>[t.id,t.status,t.image,t.error])])]);
  if(signature!==lastSignature){
    lastSignature=signature;
    $('board-grid').innerHTML=board.shots.map((s,i)=>{
      const ready=s.takes.filter(t=>t.status==='succeeded'),hero=ready.find(t=>t.id===s.picked)||ready[0];
      const active=s.takes.find(t=>t.status==='running'), strip=busy()?s.takes:ready;
      const review=hero&&board.review?.find(r=>r.shot===s.id&&r.take===hero.id), verdict=review&&review.verdict!=='pending'?`<span class="verdict ${review.verdict}" title="${escapeHTML(review.note||'')}">${review.verdict==='pass'?'Pass':'Fail'}</span>`:'';
      const badge=heroRef?.shot_id===s.id&&continuity.enabled?'<span class="badge hero">★ Hero</span>':'';
      const at=strip.findIndex(t=>t.id===s.picked), shown=strip.length<=5?strip:at<4?strip.slice(0,4):[...strip.slice(0,3),strip[at]];
      const label=hero?(s.picked?'':'Preview · '+hero.id.toUpperCase()):active?'Rendering':s.takes.some(t=>t.status==='queued')?'Queued':s.takes.some(t=>t.status==='failed')?'Failed':'', status=label?`<span class="frame-status">${label}</span>`:'';
      return `<article class="shot-card ${s.picked?'picked':''}"><div class="shot-hero" tabindex="0" role="button" aria-label="Compare ${escapeHTML(s.title)}" data-compare="${s.id}">${hero?`<img src="${imageURL(hero)}" alt="${escapeHTML(s.title)} ${hero.id}">`:`<span class="empty-frame">${String(i+1).padStart(2,'0')}</span>`}${badge}${status}</div><div class="shot-label"><h3>${pictogram(s.shot_type||s.title)}<b>${String(i+1).padStart(2,'0')}</b><span>${escapeHTML(s.title)}</span></h3>${verdict}</div><div class="card-bottom"><div class="take-strip">${shown.map(t=>`<button class="take-thumb ${s.picked===t.id?'selected':''}" data-compare="${s.id}" aria-label="Compare ${escapeHTML(s.title)} ${t.id}">${t.status==='succeeded'?`<img src="${imageURL(t)}" alt="${t.id}">`:t.status==='running'?'…':t.status==='queued'?t.id:escapeHTML(t.status)}</button>`).join('')}${shown.length<strip.length?`<button class="take-thumb more" data-compare="${s.id}" aria-label="Compare all ${strip.length} takes of ${escapeHTML(s.title)}">+${strip.length-shown.length}</button>`:''}</div><button class="${s.picked||!ready.length?'quiet':'tinted'}" data-compare="${s.id}">Compare &amp; pick</button></div></article>`;
    }).join('');
    document.querySelectorAll('[data-compare]').forEach(el=>{el.onclick=()=>openCompare(el.dataset.compare);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openCompare(el.dataset.compare);}};});
    if($('compare-dialog').open)renderCompare();
  }
}
async function refresh() {if(board){board=await api('/boards/'+board.id);render();}}
async function openBoard(id){board=await api('/boards/'+id);location.hash=id;lastSignature='';editing=false;$('shot-list').hidden=true;$('board-grid').hidden=false;$('edit-toggle').textContent='Edit cuts';render();}
function renderCompare(){
  const s=board.shots.find(s=>s.id===currentShot);if(!s)return;
  $('compare-title').textContent=s.title;
  $('compare-index').textContent=`· ${board.shots.indexOf(s)+1} of ${board.shots.length}`;
  $('compare-images').innerHTML=s.takes.length?s.takes.map(t=>`<div class="compare-take ${s.picked===t.id?'chosen':''} ${t.status!=='succeeded'?'unavailable':''}">${t.status==='succeeded'?`<img src="${imageURL(t)}" alt="${escapeHTML(s.title)} ${t.id}">`:'<div class="shot-hero"><span class="empty-frame take-state">'+escapeHTML(t.status)+'</span></div>'}<div><div><strong>${t.id.toUpperCase()}</strong><small>${t.reference?'Qwen reference edit':t.settings?escapeHTML(t.settings.label):''}</small><details class="take-details"><summary>Render details</summary><small>SEED ${t.seed}</small>${t.settings?`<small>${escapeHTML(t.settings.label)} · ${t.settings.width} × ${t.settings.height} · CFG ${t.settings.cfg}</small><small>${t.settings.steps} steps · ${escapeHTML(t.settings.sampler_name)} / ${escapeHTML(t.settings.scheduler)}</small>`:''}${t.error?`<small>${escapeHTML(t.error)}</small>`:''}</details></div><button class="${s.picked===t.id?'primary':'tinted'}" data-pick="${t.id}" ${t.status!=='succeeded'?'disabled':''}>${s.picked===t.id?'✓ Picked':'Pick'}</button></div>${reviewEditor(s,t)}</div>`).join(''):'<p class="muted">No takes yet.</p>';
  document.querySelectorAll('[data-pick]').forEach(el=>el.onclick=guarded(async()=>{await api(`/boards/${board.id}/shots/${s.id}/pick`,'POST',{take_id:el.dataset.pick});await refresh();$('reuse-seed').value=board.shots.find(x=>x.id===s.id).takes.find(t=>t.id===el.dataset.pick).seed;}));
  bindReviewEditors('#compare-images');
  $('seed-lock').textContent=s.locked_seed!==null?'Unlock seed':'Lock seed';
  $('seed-lock').disabled=!s.takes.some(t=>t.status==='succeeded');
  const picked=s.takes.find(t=>t.id===s.picked), heroAllowed=isSDXLOriginal(picked);
  $('use-hero').disabled=busy()||!heroAllowed;
  $('more-takes').disabled=busy()||(board.continuity?.enabled&&board.continuity.hero?.shot_id===s.id);
}
function openCompare(id){currentShot=id;renderCompare();const s=board.shots.find(s=>s.id===id),t=s.takes.find(t=>t.id===s.picked)||s.takes.find(t=>t.status==='succeeded');$('reuse-seed').value=s.locked_seed??t?.seed??board.config.seed;if(!$('compare-dialog').open)$('compare-dialog').showModal();}
function showEditors(){
  $('shot-list').innerHTML=board.shots.map(s=>`<div class="shot-editor"><div><label>Cut title<input id="title-${s.id}" value="${escapeHTML(s.title)}"></label><label>SDXL width<input type="number" min="512" max="1536" step="64" id="width-${s.id}" value="${s.render_settings?.width||1024}"></label><label>SDXL height<input type="number" min="512" max="1536" step="64" id="height-${s.id}" value="${s.render_settings?.height||576}"></label><label>SDXL CFG<input type="number" min="1" max="12" step="0.1" id="cfg-${s.id}" value="${s.render_settings?.cfg||6}"></label><button data-save="${s.id}">Save cut</button></div><div><label>Prompt<textarea id="prompt-${s.id}">${escapeHTML(s.prompt)}</textarea></label><label>Negative prompt<input class="editor-negative" id="negative-${s.id}" value="${escapeHTML(s.negative)}"></label></div></div>`).join('');
  document.querySelectorAll('[data-save]').forEach(button=>button.onclick=guarded(async()=>{const s=button.dataset.save;await api(`/boards/${board.id}/shots/${s}`,'PATCH',{title:$('title-'+s).value,prompt:$('prompt-'+s).value,negative:$('negative-'+s).value,render_settings:{width:Number($('width-'+s).value),height:Number($('height-'+s).value),cfg:Number($('cfg-'+s).value)}});await refresh();toast('Cut saved.');}));
}
$('use-example').onclick=guarded(async()=>{
  if(!examples.length)examples=await api('/examples');
  const config=examples[0].board.config;
  for(const key of ['scene','character','prop','setting'])$(key).value=config[key]||'';
  document.querySelector('.advanced').open=true;
});
$('scene-form').onsubmit=guarded(async event=>{event.preventDefault();const data=Object.fromEntries(new FormData(event.target));Object.assign(data,choices,{seed:Number(data.seed),count:Number(data.count)});const created=await api('/boards','POST',data);await openBoard(created.id);});
$('generate').onclick=guarded(async()=>{const button=$('generate');button.disabled=true;try{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value)});await refresh();}finally{button.disabled=busy();}});
$('more-takes').onclick=guarded(async()=>{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value),shot_id:currentShot});await refresh();});
$('cancel').onclick=guarded(async()=>{await api(`/boards/${board.id}/cancel`,'POST',{});await refresh();});
$('seed-lock').onclick=guarded(async()=>{const s=board.shots.find(x=>x.id===currentShot);const seed=s.locked_seed!==null?null:Number($('reuse-seed').value);await api(`/boards/${board.id}/shots/${s.id}/seed`,'POST',{seed});await refresh();});
$('use-hero').onclick=guarded(async()=>{const s=board.shots.find(s=>s.id===currentShot);if(!isSDXLOriginal(s.takes.find(t=>t.id===s.picked)))throw new Error(HERO_RULE);await api(`/boards/${board.id}/continuity`,'POST',{enabled:true,shot_id:s.id,take_id:s.picked});await refresh();toast('Hero locked.');});
$('keep-continuity').onchange=guarded(async()=>{const hero=board.continuity?.hero;await api(`/boards/${board.id}/continuity`,'POST',{enabled:$('keep-continuity').checked,shot_id:hero?.shot_id,take_id:hero?.take_id});await refresh();});
$('export').onclick=()=>{location.href=`/api/boards/${board.id}/export`;};
$('close-compare').onclick=()=>$('compare-dialog').close();$('close-boards').onclick=()=>$('boards-dialog').close();
$('edit-toggle').onclick=()=>{editing=!editing;$('shot-list').hidden=!editing;$('board-grid').hidden=editing;$('edit-toggle').textContent=editing?'Done':'Edit cuts';if(editing)showEditors();};
$('new-board').onclick=()=>{$('scene-form').reset();document.querySelector('.advanced').open=false;board=null;location.hash='';$('home').hidden=true;$('composer').hidden=false;$('workspace').hidden=true;$('scene').focus();};
$('load-example').onclick=guarded(async()=>{const boards=await api('/boards');$('boards-list').innerHTML=boards.map(b=>`<button class="board-link" data-board="${b.id}">${escapeHTML(b.title)}</button>`).join('')||'<p class="muted">No boards yet.</p>';document.querySelectorAll('[data-board]').forEach(b=>b.onclick=guarded(async()=>{await openBoard(b.dataset.board);$('boards-dialog').close();}));$('boards-dialog').showModal();});
async function health(){try{const h=await api('/health');$('connection').textContent=board?.continuity?.enabled&&!h.reference_components_present?'Engine offline':h.proxy_ready&&h.checkpoint_present?'Local engine ready':!h.checkpoint_present?'Engine offline':'Local engine offline';$('connection').dataset.state=$('connection').textContent==='Local engine ready'?'ready':'offline';}catch{$('connection').textContent='Local server unavailable';$('connection').dataset.state='offline';}}
guarded(async()=>{chips(await api('/config'));await loadGallery();if(location.hash.length>1)await openBoard(location.hash.slice(1));await health();})();
setInterval(async()=>{if(polling)return;polling=true;try{await refresh();}catch{}finally{polling=false;}},1600);setInterval(health,15000);

// Original composition diagrams: readable at chip size, with text labels alongside.
function pictogram(type){
  const paths={
    'Establishing':'<path d="M4 23 12 14 18 20 27 9 38 23"/><circle cx="22" cy="17" r="2"/><path d="M22 19v5"/>',
    'Medium':'<circle cx="21" cy="10" r="4"/><path d="M13 25v-5a8 8 0 0 1 16 0v5"/>',
    'Close-up':'<ellipse cx="21" cy="16" rx="10" ry="13"/><path d="M16 13h2m6 0h2m-9 8q4 3 8 0"/>',
    'Over shoulder':'<circle cx="10" cy="13" r="6"/><path d="M2 27v-4q8-9 16 0v4"/><circle cx="29" cy="10" r="3"/><path d="M24 20v-3q5-6 10 0v3"/>',
    'Insert':'<circle cx="22" cy="15" r="9"/><path d="m22 9-4 10 9-5-5-5Zm-14 14 6-4m16 5 5 2"/>',
    'Low angle':'<path d="m12 25 4-13h10l5 13M8 23l-3 3m0 0v-7m0 7h7"/><circle cx="21" cy="7" r="4"/>'
  };
  return `<svg viewBox="0 0 42 30" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true"><rect x="1" y="1" width="40" height="28" rx="3" opacity=".4"/>${paths[type]||paths.Medium}</svg>`;
}
function reviewEditor(shot,take){
  const saved=board.review?.find(r=>r.shot===shot.id&&r.take===take.id);
  const draft=reviewDrafts.get(`${board.id}/${shot.id}/${take.id}`)||saved||{};
  return `<form class="review-editor" data-shot="${shot.id}" data-take="${take.id}" aria-label="Review ${shot.id} ${take.id}"><label>Review<select name="verdict">${['pending','pass','fail'].map(value=>`<option value="${value}" ${(draft.verdict||'pending')===value?'selected':''}>${{pending:'Pending',pass:'Pass',fail:'Fail'}[value]}</option>`).join('')}</select></label><label class="review-note">Note<input name="note" maxlength="400" value="${escapeHTML(draft.note||'')}"></label><button type="submit" class="quiet">Save</button></form>`;
}
function bindReviewEditors(root){
  document.querySelectorAll(`${root} .review-editor`).forEach(form=>{
    const key=`${board.id}/${form.dataset.shot}/${form.dataset.take}`;
    const values=()=>({verdict:form.elements.verdict.value,note:form.elements.note.value});
    form.oninput=()=>reviewDrafts.set(key,values());
    form.onsubmit=guarded(async event=>{
      event.preventDefault();
      const data=values(), button=form.querySelector('button');button.disabled=true;
      try{
        await api(`/boards/${board.id}/shots/${form.dataset.shot}/takes/${form.dataset.take}/review`,'PUT',data);
        if(!reviewDrafts.has(key)||JSON.stringify(reviewDrafts.get(key))===JSON.stringify(data))reviewDrafts.delete(key);
        await refresh();toast('Saved');
      }finally{button.disabled=false;}
    });
  });
}
async function loadGallery(){
  examples=await api('/examples');
  const featured=examples[0], b=featured.board;
  const picked=s=>s.takes.find(t=>t.id===s.picked);
  const url=(ex,s)=>`/api/examples/${ex.slug}/images/${picked(s).image}`;
  $('featured-board').innerHTML=`<div class="featured-content"><div class="feature-cover"><img src="${url(featured,b.shots[1])}" alt="Traveler in a mustard raincoat examining a brass compass"><div class="feature-caption"><h2>The greenhouse</h2><button class="on-photo" data-example="${featured.slug}">Explore the board</button></div></div><div class="feature-mosaic">${b.shots.map((s,i)=>`<button class="feature-cut" data-example="${featured.slug}" data-cut="${s.id}" aria-label="Open ${escapeHTML(s.title)}"><img src="${url(featured,s)}" alt="${escapeHTML(s.title)} selected render"><span>${String(i+1).padStart(2,'0')} ${escapeHTML(s.title)}</span></button>`).join('')}</div></div>`;
  $('example-gallery').innerHTML=examples.map(ex=>`<button class="gallery-card" data-example="${ex.slug}"><div class="gallery-images">${[0,2,4].map(i=>`<img loading="lazy" src="${url(ex,ex.board.shots[i])}" alt="${escapeHTML(ex.board.shots[i].title)} render">`).join('')}</div><div class="gallery-caption"><span>${escapeHTML(ex.label)}</span><small>${ex.board.shots.length} cuts</small></div></button>`).join('');
  document.querySelectorAll('[data-example]').forEach(el=>el.onclick=guarded(async()=>{const opened=await api(`/examples/${el.dataset.example}/open`,'POST');await openBoard(opened.id);window.scrollTo(0,0);if(el.dataset.cut)openCompare(el.dataset.cut);}));
  $('coverage-preview').innerHTML=['Establishing','Medium','Close-up','Over shoulder','Insert','Low angle'].map(type=>`<div class="composition-chip">${pictogram(type)}${type==='Establishing'?'Wide':type==='Over shoulder'?'OTS':type}</div>`).join('');
}
let storyboardRequest=0;
async function previewStoryboard(){
  const request=++storyboardRequest, layout=$('storyboard-layout').value;
  $('storyboard-preview').hidden=true;$('download-storyboard').hidden=true;$('storyboard-error').hidden=false;$('storyboard-error').textContent='Preparing your storyboard…';
  const path=`/api/boards/${board.id}/storyboard?layout=${layout}`;
  const response=await fetch(path);
  if(!response.ok){const error=await response.json();throw new Error(error.detail);}
  const blob=await response.blob();
  if(request!==storyboardRequest)return;
  const old=$('storyboard-preview').dataset.objectUrl;
  if(old)URL.revokeObjectURL(old);
  const objectUrl=URL.createObjectURL(blob);
  $('storyboard-preview').dataset.objectUrl=objectUrl;
  $('storyboard-preview').src=objectUrl;$('storyboard-preview').hidden=false;
  $('download-storyboard').href=path+'&download=true';$('download-storyboard').hidden=false;$('storyboard-error').hidden=true;
}
const safePreview=async()=>{try{await previewStoryboard();}catch(error){$('storyboard-error').textContent=error.message;}};
$('storyboard').onclick=()=>{$('storyboard-dialog').showModal();safePreview();};
$('storyboard-layout').onchange=safePreview;
$('close-storyboard').onclick=()=>{$('storyboard-dialog').close();storyboardRequest++;};
function navigateCut(delta){const index=board.shots.findIndex(s=>s.id===currentShot);openCompare(board.shots[(index+delta+board.shots.length)%board.shots.length].id);$('compare-dialog').scrollTop=0;}
$('previous-cut').onclick=()=>navigateCut(-1);$('next-cut').onclick=()=>navigateCut(1);
document.addEventListener('keydown',event=>{
  if(['INPUT','TEXTAREA','SELECT','SUMMARY'].includes(event.target.tagName)||event.altKey||event.ctrlKey||event.metaKey)return;
  if(!board||!['ArrowLeft','ArrowRight'].includes(event.key))return;
  if($('storyboard-dialog').open||$('boards-dialog').open)return;
  event.preventDefault();const delta=event.key==='ArrowRight'?1:-1;
  if($('compare-dialog').open)navigateCut(delta);
  else{const cards=[...document.querySelectorAll('.shot-hero[data-compare]')];const index=cards.indexOf(document.activeElement);cards[(index+delta+cards.length)%cards.length]?.focus();}
});
window.addEventListener('hashchange',guarded(async()=>{const id=location.hash.slice(1);if(id&&id!==board?.id)await openBoard(id);else if(!id&&$('composer').hidden){board=null;$('workspace').hidden=true;$('home').hidden=false;}}));
