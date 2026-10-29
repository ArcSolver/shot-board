const HERO_RULE = 'Only an SDXL take or an imported reference can be the hero.';
function isImported(take) { return take?.status==='succeeded' && take.source?.type==='imported' && take.settings?.preset_id==='imported-reference' && !take.reference && take.seed===null && take.models?.length===0 && Object.keys(take.workflow||{}).length===0; }
const canBeHero = take => isSDXLOriginal(take) || isImported(take);
function isSDXLOriginal(take) {
  return !!take && take.status==='succeeded' && !take.reference &&
    take.settings?.checkpoint==='sd_xl_base_1.0.safetensors' &&
    (take.settings?.preset_id||'sdxl-base')==='sdxl-base' &&
    take.workflow?.['1']?.class_type==='CheckpointLoaderSimple';
}
const $ = (id) => document.getElementById(id);
let examples = [], board = null, currentShot = null, editing = false, lastSignature = '', polling = false;
const reviewDrafts = new Map();
// The take on screen in Compare, per cut. It survives the polling rerender; opening a cut starts at its pick.
const viewing = new Map();
let compareShow = 'take';
const choices = {lens:'35', angle:'Eye level', move:'Static', lighting:'Window light', look:'Muted film'};
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const busy = () => board?.shots.some(s => s.takes.some(t => ['queued','running'].includes(t.status)));
const imageURL = (take) => `/api/boards/${board.id}/images/${take.image}`;
// Setup numbers: the script supervisor's 01, 02 … that tie a cut to its line of the scene.
const NN = i => String(i+1).padStart(2,'0');
const TAKE = t => t.id.toUpperCase();
// Take IDs are slate marks, typed like the setup numbers.
const TAKE_NO = t => `<span class="take-no">${TAKE(t)}</span>`;
const WAIT = 'Wait for the queue to finish.';
// Numbers and IDs in a sentence are typed too, in the sentence's own colour; pencil is kept for numbers on a setup line.
const SLATE = text => `<span class="slate">${text}</span>`;
// When a request never arrives, say so in words that fit the build: the local app has a server, the Pages viewer has files.
const offline = () => window.SB?'The page could not load its board files. Check the connection, then reload the page.':'The local Shot Board server is not answering. Start it again, then reload the page.';
// A server's error detail is shown only when it is a sentence; a list or an object gets the fallback.
const detail = (error, fallback) => typeof error.detail==='string'?error.detail:fallback;
// A control the keyboard is on stays focusable while the queue runs: marked unavailable and refusing presses, not disabled.
const hold = (button, off) => {const keep=off&&document.activeElement===button;button.disabled=off&&!keep;button.ariaDisabled=keep?'true':null;};
const phone = () => !!window.matchMedia?.('(max-width:600px)')?.matches;
const icon = name => `<svg class="i" aria-hidden="true"><use href="#i-${name}"/></svg>`;
// Every board image goes through img(): lazy unless it is the first one on screen. The static viewer
// swaps in sized WebP copies (window.SB.sized); only the enlarged view and downloads use the original.
const SIZES={lined:'(max-width:600px) 62vw, 300px',card:'(max-width:600px) calc(50vw - 22px), (max-width:1100px) calc(33vw - 30px), 320px',mini:'(max-width:600px) 72px, 96px',hero:'96px',thumb:'(max-width:600px) 150px, 160px',compare:'(max-width:600px) calc(100vw - 32px), (max-width:1100px) 46vw, 480px',solo:'(max-width:600px) calc(100vw - 32px), (max-width:1100px) 92vw, 960px'};
// Contain-fit slots, as their narrowest shape across layouts: a tall or square still shows narrower than the slot.
const SLOT={card:1.33,compare:1.33};
function img(url,alt,sizes,first=false,slot=0){
  const sized=window.SB?.sized?.(url), scale=slot&&sized?.width?Math.min(1,sized.width/sized.height/slot):1;
  if(scale<1)sizes=sizes.split(', ').map(part=>part.replace(/(calc\(.*\)|[^\s)]+)$/,length=>`calc(${length} * ${scale.toFixed(2)})`)).join(', ');
  return `<img src="${sized?.src||url}"${sized?` srcset="${sized.srcset}" sizes="${sizes}"`:''} alt="${escapeHTML(alt)}" decoding="async"${first?' fetchpriority="high"':' loading="lazy"'}>`;
}
// Frames keep their true shape. Ratios are set after insertion: the static viewer's CSP drops inline style attributes.
// A still that fails to load marks its frame, which then says so; inline handlers are not allowed by the Pages CSP.
document.addEventListener('error',event=>{if(event.target?.tagName==='IMG')event.target.closest?.('.shot-hero,.frame,.mini-frame,.take-frame,.hero-thumb,.take-zoom')?.classList.add('img-missing');},true);
function setRatios(selector,takes){document.querySelectorAll?.(selector).forEach((el,i)=>{const t=takes[i],w=t?.settings?.width,h=t?.settings?.height;if(w&&h)el.style.setProperty('--ar',(w/h).toFixed(4));});}
// The toast is a manual popover so it shows in the top layer, above an open Compare or Storyboard dialog and its backdrop.
// Inside a modal dialog it moves into that dialog, so it is not inert and its status is still announced.
function toast(message) {
  const el=$('toast'), layer=!!el.showPopover, host=[...(document.querySelectorAll?.('dialog[open]')||[])].pop()||document.body;
  if(el.parentNode&&el.parentNode!==host){if(layer&&el.matches(':popover-open'))el.hidePopover();host.append(el);}
  el.textContent=message; el.hidden=false;
  if(layer){if(el.matches(':popover-open'))el.hidePopover();el.showPopover();}
  clearTimeout(toast.timer);
  toast.timer=setTimeout(()=>{el.hidden=true;if(layer&&el.matches(':popover-open'))el.hidePopover();},6000);
}
async function api(path, method='GET', data) {
  const response=await fetch('/api'+path,{method,headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined}).catch(()=>{throw new Error(offline());});
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
const shotIndex = id => board.shots.findIndex(s=>s.id===id);
const reviewFor = (shot,take) => board.review?.find(r=>r.shot===shot.id&&r.take===take.id);
function verdictMark(review){return review&&review.verdict!=='pending'?`<span class="verdict ${review.verdict}" title="${escapeHTML(review.note||'')}">${review.verdict==='pass'?'Pass':'Fail'}</span>`:'';}
// Numbers as a script supervisor writes them: 01, 03–06.
function setupRanges(indexes){
  const runs=[];for(const i of indexes){const last=runs.at(-1);if(last&&i===last[1]+1)last[1]=i;else runs.push([i,i]);}
  return runs.map(([a,b])=>a===b?NN(a):b===a+1?`${NN(a)}, ${NN(b)}`:`${NN(a)}–${NN(b)}`).join(', ');
}
// Where a frame came from, read from the take itself, never from its position on the board.
function sourceLabel(take){
  if(!take)return '';
  if(isImported(take))return 'Imported reference';
  if(take.reference){const at=shotIndex(take.reference.shot_id);return `Redrawn from ${SLATE(at>=0?NN(at):escapeHTML(take.reference.shot_id.toUpperCase()))}`;}
  // On a board of SDXL takes only, every cut would say the same thing.
  return isSDXLOriginal(take)&&allTakes().some(t=>t.reference||isImported(t))?'SDXL take':'';
}
function heroTake(){
  const h=board.continuity?.hero;if(!h)return null;
  const shot=board.shots.find(s=>s.id===h.shot_id), take=shot?.takes.find(t=>t.id===h.take_id&&t.status==='succeeded');
  return shot&&take?{shot,take}:null;
}
function scriptFields(){
  const c=board.config||{}, camera=[c.lens&&`${c.lens} mm lens`,c.angle&&c.angle.toLowerCase(),c.move&&c.move.toLowerCase()].filter(Boolean).join(', ');
  const look=[c.lighting,c.look&&c.look.toLowerCase()].filter(Boolean).join(', ');
  const rows=[['Character',c.character],['Prop',c.prop],['Setting',c.setting],['Camera',[camera,look].filter(Boolean).join('. ')+(camera||look?'.':'')]];
  return rows.filter(([,v])=>v&&v.trim()).map(([k,v])=>`<p class="cue">${k}</p><p class="script-text">${escapeHTML(v)}</p>`).join('');
}
// The hero block draws one setup line from the hero cut to every cut a reference edit redraws.
function heroLine(){
  const c=board.continuity||{}, h=c.hero;
  if(!h)return '<p class="hero-meta">No hero yet.</p>';
  const at=shotIndex(h.shot_id), shot=board.shots[at], found=heroTake(), others=board.shots.map((s,i)=>i).filter(i=>i!==at);
  const kind=h.source?.type==='imported'?'Imported reference':'SDXL take';
  return `<button class="hero-card" data-compare="${escapeHTML(h.shot_id)}" aria-label="Compare the hero, ${escapeHTML(shot?.title||'')}"><span class="hero-thumb">${found?img(imageURL(found.take),`${shot.title} hero`,SIZES.hero):''}</span><span class="hero-text"><span class="hero-name"><span class="setup-no">${at>=0?NN(at):''}</span>${escapeHTML(shot?.title||'')}</span><span><span class="take-no">${escapeHTML(h.take_id.toUpperCase())}</span> · ${kind}</span></span></button>
    <div class="hero-branch"><span class="branch-stem" aria-hidden="true"></span><p><span class="branch-label">${c.enabled?'Reference edits for':'Reference edits off for'}</span> <span class="branch-nos">${setupRanges(others)}</span></p></div>`;
}
function render() {
  if(!board)return;
  $('home').hidden=true;$('composer').hidden=true;$('workspace').hidden=false;
  const scene=board.config?.scene||'';const title=board.title.trim();$('board-title').textContent=title+(scene.trim().length>title.length&&!/[.!?…]$/.test(title)?'…':'');
  const continuity=board.continuity||{}, heroRef=continuity.hero;
  $('keep-continuity').checked=!!continuity.enabled;
  $('keep-continuity').disabled=busy()||!heroRef;
  // The switch is held while the queue runs; the status line says why.
  $('hero-status').textContent=heroRef&&busy()?WAIT:'';
  const picked=board.shots.filter(s=>s.picked).length, takes=allTakes(), completed=takes.filter(t=>t.status==='succeeded').length;
  const allPicked=picked===board.shots.length, ready=s=>s.takes.some(t=>t.status==='succeeded');
  const needsRender=board.shots.some(s=>!ready(s))||(!!continuity.enabled&&board.shots.some(s=>s.id!==heroRef?.shot_id&&!s.takes.some(t=>t.reference&&t.status==='succeeded')));
  $('storyboard').disabled=!allPicked;
  $('export-hint').textContent=allPicked?'':'Pick a take in every cut to export.';
  $('storyboard').className=allPicked?'primary':'quiet';
  hold($('generate'),busy());$('cancel').hidden=!busy();
  $('generate').className=needsRender&&!allPicked?'primary':'quiet';
  $('generate').textContent=board.continuity?.enabled?'Render reference edits':completed?'More takes for every cut':'Render board';
  $('pick-count').textContent=`${picked} of ${board.shots.length} picked`;
  const example=examples.find(ex=>ex.board.id===board.id);
  $('board-name').textContent=example?example.label:'Your scene';
  $('pick-meter').innerHTML=board.shots.map((s,i)=>`<i class="${s.picked?'on':''}">${NN(i)}</i>`).join('');
  $('queue-panel').hidden=!busy();
  const running=takes.find(t=>t.status==='running'),queued=takes.filter(t=>t.status==='queued').length;
  $('queue-status').textContent=`${completed} / ${takes.length} takes ready · ${queued} queued`;
  $('queue-detail').textContent=running?`${running.phase} · ${Math.floor((Date.now()/1000)-running.started_at)}s elapsed`:'Waiting for the worker';
  $('queue-progress').max=takes.length||1;$('queue-progress').value=completed;
  $('recipe-label').textContent='First takes · SDXL Base 1.0';
  const reviewed=board.review?.some(r=>r.verdict!=='pending'), heroAt=continuity.enabled?shotIndex(heroRef?.shot_id):-1;
  // Without a hero a verdict is judged against the cut's own prompt, which needs no note.
  $('review-legend').hidden=!reviewed||heroAt<0;
  $('review-legend').innerHTML=heroAt>=0?`Checked against the hero, ${SLATE(NN(heroAt))} ${escapeHTML(board.shots[heroAt].title)}.`:'';
  const signature=JSON.stringify([board.continuity,board.review,board.config,board.shots.map(s=>[s.title,s.prompt,s.picked,s.locked_seed,s.takes.map(t=>[t.id,t.status,t.image,t.error])])]);
  if(signature!==lastSignature){
    lastSignature=signature;
    $('script-fields').innerHTML=scriptFields();
    $('hero-line').innerHTML=heroLine();
    // The line above each cut's title names the hero and where the still came from; a board with nothing to name drops the row.
    const shown=s=>{const done=s.takes.filter(t=>t.status==='succeeded');return done.find(t=>t.id===s.picked)||done[0];};
    const srcLine=s=>{const src=sourceLabel(shown(s));return heroRef?.shot_id===s.id&&continuity.enabled?`<b>Hero</b>${src?` · ${src}`:''}`:src;};
    const named=board.shots.some(s=>srcLine(s));
    $('board-grid').innerHTML=board.shots.map((s,i)=>{
      const done=s.takes.filter(t=>t.status==='succeeded'),hero=done.find(t=>t.id===s.picked)||done[0];
      const active=s.takes.find(t=>t.status==='running');
      const verdict=hero?verdictMark(reviewFor(s,hero)):'';
      const isHero=heroRef?.shot_id===s.id&&continuity.enabled;
      const label=hero?(s.picked?'':'Preview · '+TAKE_NO(hero)):active?'Rendering':s.takes.some(t=>t.status==='queued')?'Queued':s.takes.some(t=>t.status==='failed')?'Failed':'', status=label?`<span class="frame-status">${label}</span>`:'';
      const inQueue=s.takes.some(t=>['queued','running'].includes(t.status));
      const facts=hero?`<span>${inQueue?`${TAKE_NO(hero)} · ${done.length} of ${s.takes.length} ready`:`${TAKE_NO(hero)} of ${done.length}`}</span>`:`<span>${s.takes.length?`${done.length} of ${s.takes.length} ready`:'No takes yet'}</span>`;
      const lock=s.locked_seed!==null?`<span class="seed" title="Seed locked">${icon('lock')}<span class="visually-hidden">Seed locked</span></span>`:'';
      return `<article class="shot-card${s.picked?' picked':''}${isHero?' is-hero':''}"><div class="shot-hero" tabindex="0" role="button" aria-label="Compare ${escapeHTML(s.title)}" data-compare="${s.id}">${hero?img(imageURL(hero),`${s.title} ${hero.id}`,SIZES.card,i===0,SLOT.card):`<span class="empty-frame">${NN(i)}</span>`}${status}</div>${named?`<p class="cut-src">${srcLine(s)}</p>`:''}<div class="cut-text"><span class="setup-no">${NN(i)}</span><h3>${escapeHTML(s.title)}</h3><p class="cut-facts">${facts}${verdict}${lock}</p><button class="go" data-compare="${s.id}">Compare &amp; pick</button></div></article>`;
    }).join('');
    document.querySelectorAll('[data-compare]').forEach(el=>{el.onclick=()=>openCompare(el.dataset.compare);el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openCompare(el.dataset.compare);}};});
    $('hero-recipe').hidden=!!heroRef;
    if($('compare-dialog').open)renderCompare();
    if($('storyboard-dialog').open)renderExport();
  }
}
async function refresh() {if(board){board=await api('/boards/'+board.id);render();}}
async function openBoard(id){board=await api('/boards/'+id);location.hash=id;lastSignature='';editing=false;$('shot-list').hidden=true;$('board-grid').hidden=false;$('edit-toggle').textContent='Edit cuts';$('script-notes').open=!phone();render();}
const viewKey = s => `${board.id}/${s.id}`;
function viewedTake(s){const id=viewing.get(viewKey(s));return s.takes.find(t=>t.id===id)||s.takes.find(t=>t.id===s.picked)||s.takes.find(t=>t.status==='succeeded')||s.takes[0];}
const takeState = t => ({queued:'Queued',running:'Rendering',failed:'Failed',cancelled:'Cancelled',interrupted:'Interrupted'}[t.status]||escapeHTML(t.status));
function modelName(st){
  if(st?.preset_id==='qwen-reference'){const quant=/-(Q\d_[A-Z0-9_]+|Q8_0)\.gguf$/i.exec(st.unet||'');return 'Qwen-Image-Edit-2511'+(quant?' '+quant[1]:'');}
  return st?.label;
}
function renderDetails(t,s) {
  const row=(k,v)=>v===undefined||v===null||v===''?'':`<div><dt>${k}</dt><dd>${v}</dd></div>`, st=t.settings||{};
  if(isImported(t))return row('Source','Imported reference')+row('Size',`${st.width} × ${st.height}`);
  const ref=t.reference, at=ref?shotIndex(ref.shot_id):-1;
  return row('Model',escapeHTML(modelName(st)))+row('Text encoder',st.encoder?escapeHTML(st.encoder.replace(/\.gguf$/,'').replace(/-(Q\d_\w+)$/,' $1')):'')+row('License',escapeHTML(st.license))
    +row('Reference',ref?`${at>=0?SLATE(NN(at))+' '+escapeHTML(board.shots[at].title):escapeHTML(ref.shot_id)}, ${ref.source?.type==='imported'?'imported':`<span class="take-no">${escapeHTML(ref.take_id.toUpperCase())}</span>`}`:'')
    +row('Seed',t.seed!==null&&t.seed!==undefined?`${t.seed}${s.locked_seed!==null&&s.locked_seed===t.seed?` <span class="locked">${icon('lock')}Locked</span>`:''}`:'')
    +row('Size',st.width?`${st.width} × ${st.height}`:'')+row('Steps, CFG',st.steps?`${st.steps}, ${st.cfg}`:'')
    +row('Sampler',st.sampler_name?`${escapeHTML(st.sampler_name)} / ${escapeHTML(st.scheduler)}`:'')
    +row('Error',t.error?escapeHTML(t.error):'');
}
function figure(role,detail,shot,take,first,zoom,sizes){
  return `<figure class="fig fig-${role.toLowerCase()}"><figcaption><b>${role}</b><span>${detail}</span></figcaption>${take.status==='succeeded'?`<button class="take-zoom" ${zoom} aria-label="Enlarge ${escapeHTML(shot.title)} ${take.id}">${img(imageURL(take),`${shot.title} ${take.id}`,sizes,first,SLOT.compare)}</button>`:`<div class="frame-empty"><span class="take-state">${takeState(take)}</span></div>`}</figure>`;
}
function renderCompare(){
  const s=board.shots.find(s=>s.id===currentShot);if(!s)return;
  const at=board.shots.indexOf(s), v=viewedTake(s), picked=s.takes.find(t=>t.id===s.picked), done=s.takes.filter(t=>t.status==='succeeded');
  $('compare-title').innerHTML=`<span class="setup-no">${NN(at)}</span>${escapeHTML(s.title)}`;
  $('cut-rail').innerHTML=board.shots.map((x,j)=>`<button class="rail-cut${x.picked?' picked':''}" data-rail="${x.id}"${x.id===s.id?' aria-current="true"':''} aria-label="${NN(j)} ${escapeHTML(x.title)}${x.picked?', picked':''}">${NN(j)}</button>`).join('');
  // The hero sits beside the take, so a reference edit is judged against what it was drawn from. Without a hero, the pick does.
  const hero=heroTake(), other=hero&&hero.shot.id!==s.id?{role:'Hero',shot:hero.shot,take:hero.take,detail:`<span class="setup-no">${NN(shotIndex(hero.shot.id))}</span> ${escapeHTML(hero.shot.title)} · ${isImported(hero.take)?'Imported reference':TAKE_NO(hero.take)}`}
    :picked&&v&&picked.id!==v.id?{role:'Picked',shot:s,take:picked,detail:TAKE_NO(picked)}:null;
  const takeDetail=t=>isImported(t)?'Imported reference':'';
  $('compare-switch').hidden=!other;
  $('compare-switch').innerHTML=other?[['take',v?`Take ${TAKE_NO(v)}`:'Take'],['other',other.role]].map(([key,text])=>`<button type="button" data-show="${key}" aria-pressed="${compareShow===key}">${text}</button>`).join(''):'';
  $('compare-images').dataset.show=other?compareShow:'take';
  $('compare-images').innerHTML=v?(other?figure(other.role,other.detail,other.shot,other.take,false,'data-zoom-other="1"',SIZES.compare):'')+figure('Take',`${TAKE_NO(v)}${takeDetail(v)?' · '+takeDetail(v):''}`,s,v,true,`data-zoom="${v.id}"`,other?SIZES.compare:SIZES.solo):'<p class="muted">No takes yet.</p>';
  $('take-strip').innerHTML=s.takes.map(t=>{const isPick=s.picked===t.id, review=reviewFor(s,t);return `<button class="take${t.status!=='succeeded'?' unavailable':''}" data-view="${t.id}" aria-pressed="${t.id===v?.id}" aria-label="${TAKE(t)}${isPick?', picked':''}${review&&review.verdict!=='pending'?', '+review.verdict:''}${t.status!=='succeeded'?', '+t.status:''}"><span class="take-frame">${t.status==='succeeded'?img(imageURL(t),'',SIZES.thumb):`<span class="take-state">${takeState(t)}</span>`}</span><span class="tl"><span class="take-id${isPick?' picked':''}">${TAKE(t)}</span>${isPick?'<span class="pk">Picked</span>':''}${verdictMark(review)}</span></button>`;}).join('');
  const queued=s.takes.filter(t=>['queued','running'].includes(t.status)).length;
  $('takes-meta').textContent=queued?`${queued} in queue`:'';
  $('sheet-title').innerHTML=v?`Take ${TAKE_NO(v)}`:'No takes yet';
  const isPicked=!!v&&s.picked===v.id;
  $('pick-take').disabled=!v||v.status!=='succeeded';
  $('pick-take').className=isPicked?'state':'primary';
  $('pick-take').ariaPressed=String(isPicked);
  $('pick-take').innerHTML=isPicked?`${icon('check')}Picked`:v?(v.status==='succeeded'?`Pick ${TAKE_NO(v)}`:`${TAKE_NO(v)} ${takeState(v).toLowerCase()}`):'Pick';
  $('next-cut-2').className=isPicked?'primary':'quiet';
  const heroCut=!!board.continuity?.enabled&&board.continuity.hero?.shot_id===s.id;
  const others=s.takes.some(t=>t.status==='succeeded'&&t.id!==v?.id), canRender=!window.SB&&!busy()&&!heroCut;
  const takeCondition=v&&v.status!=='succeeded'?({failed:'This take failed.',cancelled:'This take was stopped.',queued:'This take is still in the queue.'}[v.status]||'This take is still rendering.'):'';
  const pickReason=takeCondition&&['failed','cancelled'].includes(v.status)?takeCondition+(others?' View another take to pick one.':canRender?' Render more takes for this cut.':''):takeCondition;
  $('pick-reason').hidden=!pickReason;$('pick-reason').textContent=pickReason;
  $('review-slot').innerHTML=v&&v.status==='succeeded'?reviewEditor(s,v):'';
  $('render-details').innerHTML=v?renderDetails(v,s):'';
  $('render-box').hidden=!v;
  document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>{viewing.set(viewKey(s),el.dataset.view);compareShow='take';renderCompare();document.querySelector?.(`[data-view="${el.dataset.view}"]`)?.focus();});
  document.querySelectorAll('[data-rail]').forEach(el=>el.onclick=()=>{openCompare(el.dataset.rail);$('compare-dialog').scrollTop=0;});
  document.querySelectorAll('[data-show]').forEach(el=>el.onclick=()=>{compareShow=el.dataset.show;renderCompare();});
  document.querySelectorAll('[data-zoom]').forEach(el=>el.onclick=()=>openImage(s,s.takes.find(t=>t.id===el.dataset.zoom)));
  document.querySelectorAll('[data-zoom-other]').forEach(el=>el.onclick=()=>openImage(other.shot,other.take,el.querySelector('img')?.currentSrc));
  bindReviewEditors('#review-slot');
  $('seed-lock').textContent=s.locked_seed!==null?'Unlock seed':'Lock seed';
  const imported=isImported(picked);
  $('reuse-seed').disabled=imported;
  $('seed-lock').disabled=busy()||(s.locked_seed===null&&(imported||!s.takes.some(t=>t.status==='succeeded' && t.seed!==null)));
  $('import-reference').disabled=busy();
  // An imported still has no seed: say so instead of showing the board seed next to it.
  $('seed-row').hidden=imported&&s.locked_seed===null;
  const seedNote=$('seed-row').hidden?`${TAKE_NO(picked)} is an imported reference and has no seed.`:busy()?WAIT:seedError;
  $('seed-note').hidden=!seedNote;$('seed-note').innerHTML=seedNote;
  $('reuse-seed').ariaInvalid=seedError&&!$('seed-row').hidden?'true':null;
  const heroAllowed=canBeHero(picked), h=board.continuity?.hero;
  const isHero=!!h&&board.continuity.enabled&&h.shot_id===s.id&&h.take_id===s.picked;
  $('use-hero').disabled=busy()||!heroAllowed||isHero;
  // The hero is always the pick; when another take is on screen, say which take the button uses.
  const reason=busy()?WAIT:isHero?'':!picked?'Pick a take first.':!heroAllowed?`${TAKE_NO(picked)} is a reference edit, so it can't be the hero.`:v&&v.id!==picked.id?`This uses the pick, ${TAKE_NO(picked)}.`:'';
  $('hero-reason').hidden=!reason;$('hero-reason').innerHTML=reason;
  $('compare-hero-line').innerHTML=h?heroLine():'';
  document.querySelectorAll('#compare-hero-line [data-compare]').forEach(el=>el.onclick=()=>{openCompare(el.dataset.compare);$('compare-dialog').scrollTop=0;});
  // The hero card beside it already names the hero.
  $('hero-note').hidden=!!h;$('hero-note').textContent=h?'':'No hero yet.';
  $('more-takes').disabled=busy()||heroCut;
  $('more-takes').textContent=s.takes.length?'Render more takes':'Render takes';
  const takesReason=busy()?WAIT:heroCut?'The hero cut keeps its takes.':'';
  $('takes-reason').hidden=!takesReason;$('takes-reason').textContent=takesReason;
}
let seedError='';
function openCompare(id){
  currentShot=id;seedError='';const s=board.shots.find(s=>s.id===id);viewing.delete(viewKey(s));compareShow='take';renderCompare();
  const t=s.takes.find(t=>t.id===s.picked)||s.takes.find(t=>t.status==='succeeded');$('reuse-seed').value=s.locked_seed??t?.seed??board.config.seed;
  $('render-box').open=!phone();showDialog($('compare-dialog'));
  document.querySelector?.('#take-strip [aria-pressed="true"]')?.scrollIntoView?.({block:'nearest',inline:'center'});
}
$('pick-take').onclick=guarded(async()=>{
  const s=board.shots.find(x=>x.id===currentShot), v=s&&viewedTake(s);if(!v||v.status!=='succeeded'||s.picked===v.id)return;
  await api(`/boards/${board.id}/shots/${s.id}/pick`,'POST',{take_id:v.id});await refresh();$('reuse-seed').value=board.shots.find(x=>x.id===s.id).takes.find(t=>t.id===v.id).seed;seedError='';renderCompare();
});
// Back closes Compare, the storyboard or the enlarged image instead of leaving the board: opening one adds a history entry with the same URL.
let ownBack=0;
function showDialog(dialog){if(dialog.open)return;dialog.showModal();if(window.history?.pushState){history.pushState({dialog:dialog.id},'');dialog.dataset.history='1';}}
function closedDialog(dialog){if(dialog.dataset.history!=='1')return;delete dialog.dataset.history;if(dialog.dataset.popped)delete dialog.dataset.popped;else{ownBack++;history.back();}}
window.addEventListener('popstate',()=>{if(ownBack){ownBack--;return;}const open=[$('image-dialog'),$('storyboard-dialog'),$('compare-dialog')].find(d=>d.open&&d.dataset.history==='1');if(open){open.dataset.popped='1';open.close();}else if(history.state?.dialog){ownBack++;history.back();}});
if(window.ResizeObserver)for(const heading of document.querySelectorAll('dialog > .dialog-heading'))new ResizeObserver(()=>heading.parentElement.style.setProperty('--heading-h',heading.offsetHeight+'px')).observe(heading);
$('compare-dialog').onclose=()=>closedDialog($('compare-dialog'));$('image-dialog').onclose=()=>closedDialog($('image-dialog'));
$('storyboard-dialog').onclose=()=>{storyboardRequest++;closedDialog($('storyboard-dialog'));};
// The original PNG opens full size; the sized copy already on screen stands in until it arrives.
function openImage(shot,take,shownSrc){
  const full=$('image-full'),preview=$('image-preview'),shown=shownSrc||document.querySelector?.(`[data-zoom="${take.id}"] img`)?.currentSrc;
  $('image-title').innerHTML=`${escapeHTML(shot.title)} · ${TAKE_NO(take)}`;
  full.alt=`${shot.title} ${take.id} original`;full.classList.remove('loaded','actual');full.removeAttribute('src');
  if(shown)preview.src=shown;else preview.removeAttribute('src');preview.hidden=!shown;
  full.onload=()=>{full.classList.add('loaded');preview.hidden=true;};full.onerror=()=>{if(full.getAttribute('src'))toast('The original image could not be loaded.');};full.src=imageURL(take);
  showDialog($('image-dialog'));
}
$('close-image').onclick=()=>$('image-dialog').close();
$('image-full').onclick=()=>$('image-full').classList.toggle('actual');
$('image-full').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('image-full').classList.toggle('actual');}};
if(window.history?.state?.dialog)history.replaceState(null,'');
function showEditors(){
  $('shot-list').innerHTML=board.shots.map((s,i)=>`<div class="shot-editor"><span class="setup-no">${NN(i)}</span><div class="editor-settings"><label>Cut title<input id="title-${s.id}" value="${escapeHTML(s.title)}"></label><label>SDXL width<input type="number" min="512" max="1536" step="64" id="width-${s.id}" value="${s.render_settings?.width||1024}"></label><label>SDXL height<input type="number" min="512" max="1536" step="64" id="height-${s.id}" value="${s.render_settings?.height||576}"></label><label>SDXL CFG<input type="number" min="1" max="12" step="0.1" id="cfg-${s.id}" value="${s.render_settings?.cfg||6}"></label></div><div class="editor-prompts"><label>Prompt<textarea id="prompt-${s.id}">${escapeHTML(s.prompt)}</textarea></label><label>Negative prompt<input class="editor-negative" id="negative-${s.id}" value="${escapeHTML(s.negative)}"></label><button class="quiet" data-save="${s.id}">Save cut</button></div></div>`).join('');
  document.querySelectorAll('[data-save]').forEach(button=>button.onclick=guarded(async()=>{const s=button.dataset.save;await api(`/boards/${board.id}/shots/${s}`,'PATCH',{title:$('title-'+s).value,prompt:$('prompt-'+s).value,negative:$('negative-'+s).value,render_settings:{width:Number($('width-'+s).value),height:Number($('height-'+s).value),cfg:Number($('cfg-'+s).value)}});await refresh();toast('Cut saved.');}));
}
$('use-example').onclick=guarded(async()=>{
  if(!examples.length)examples=await api('/examples');
  const config=examples[0].board.config;
  for(const key of ['scene','character','prop','setting'])$(key).value=config[key]||'';
  coveragePreview();
  document.querySelector('.advanced').open=true;
});
$('scene-form').onsubmit=guarded(async event=>{event.preventDefault();if(!sceneValid())return;const data=Object.fromEntries(new FormData(event.target));Object.assign(data,choices,{seed:Number(data.seed),count:Number(data.count)});const created=await api('/boards','POST',data);await openBoard(created.id);});
$('generate').onclick=guarded(async()=>{const button=$('generate'), label=button.textContent;if(button.ariaDisabled==='true')return;button.ariaDisabled='true';button.ariaBusy='true';button.textContent='Queuing…';try{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value)});await refresh();}finally{button.ariaBusy=null;hold(button,busy());if(button.textContent==='Queuing…')button.textContent=label;}});
$('more-takes').onclick=guarded(async()=>{await api(`/boards/${board.id}/generate`,'POST',{takes:Number($('takes-count').value),shot_id:currentShot});await refresh();});
$('cancel').onclick=guarded(async()=>{await api(`/boards/${board.id}/cancel`,'POST',{});await refresh();});
// Seed problems are told beside the seed field, not in a toast across the screen.
$('seed-lock').onclick=guarded(async()=>{const s=board.shots.find(x=>x.id===currentShot);const input=$('reuse-seed').value.trim();const seed=s.locked_seed!==null?null:Number(input);
  seedError=s.locked_seed===null&&(input===''||isImported(s.takes.find(t=>t.id===s.picked)))?'Pick a generated take and enter its seed.':seed!==null&&(!Number.isInteger(seed)||seed<0||seed>4294967295)?'Enter a whole seed from 0 to 4294967295.':'';
  if(seedError){renderCompare();return;}
  await api(`/boards/${board.id}/shots/${s.id}/seed`,'POST',{seed});await refresh();});
$('reuse-seed').oninput=()=>{if(seedError){seedError='';renderCompare();}};
$('use-hero').onclick=guarded(async()=>{const s=board.shots.find(s=>s.id===currentShot);if(!canBeHero(s.takes.find(t=>t.id===s.picked)))throw new Error(HERO_RULE);await api(`/boards/${board.id}/continuity`,'POST',{enabled:true,shot_id:s.id,take_id:s.picked});await refresh();toast('Hero set.');});
$('keep-continuity').onchange=guarded(async()=>{const hero=board.continuity?.hero;await api(`/boards/${board.id}/continuity`,'POST',{enabled:$('keep-continuity').checked,shot_id:hero?.shot_id,take_id:hero?.take_id});await refresh();});
// Fetched, then saved through a link: no navigation, so the board's polling request is not cancelled, and a failure is reported.
$('export').onclick=guarded(async()=>{const button=$('export'),label=button.textContent;if(button.ariaBusy==='true')return;button.ariaDisabled='true';button.ariaBusy='true';button.textContent='Preparing ZIP…';try{const response=await fetch(`/api/boards/${board.id}/export`).catch(()=>{throw new Error(offline());});if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(detail(error,'The ZIP could not be made. Try again.'));}const href=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=href;link.download='shot-board.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(href),60000);toast('shot-board.zip is ready.');}finally{button.ariaDisabled=null;button.ariaBusy=null;button.textContent=label;}});
$('close-compare').onclick=()=>$('compare-dialog').close();$('close-boards').onclick=()=>$('boards-dialog').close();
$('edit-toggle').onclick=()=>{editing=!editing;$('shot-list').hidden=!editing;$('board-grid').hidden=editing;$('edit-toggle').textContent=editing?'Done':'Edit cuts';if(editing)showEditors();};
$('new-board').onclick=()=>{$('scene-form').reset();$('scene-error').hidden=true;$('scene').ariaInvalid=null;document.querySelector('.advanced').open=false;board=null;location.hash='';$('home').hidden=true;$('composer').hidden=false;$('workspace').hidden=true;coveragePreview();$('scene').focus();};
$('load-example').onclick=guarded(async()=>{const boards=await api('/boards');if(!examples.length)examples=await api('/examples');
  $('boards-list').innerHTML=boards.map(b=>{const ex=examples.find(e=>e.board.id===b.id), meta=b.cuts?`${b.picked} of ${b.cuts} picked`:'';
    return `<button class="board-link" data-board="${b.id}"><span class="board-link-name">${escapeHTML(ex?ex.label:'Your scene')}</span><span class="board-link-meta">${meta}</span><span class="board-link-scene">${escapeHTML(b.title)}</span></button>`;}).join('')||'<p class="muted">No boards yet.</p>';document.querySelectorAll('[data-board]').forEach(b=>b.onclick=guarded(async()=>{await openBoard(b.dataset.board);$('boards-dialog').close();}));$('boards-dialog').showModal();});
async function health(){try{const h=await api('/health');const reference=!!board?.continuity?.enabled, available=reference?h.reference_components_present:h.checkpoint_present;const ready=h.proxy_ready&&available;$('connection').textContent=!h.proxy_ready?'ComfyUI not reachable':!available?(reference?'Qwen reference files missing':'SDXL checkpoint missing'):'Local engine ready';$('connection').dataset.state=ready?'ready':'offline';}catch{$('connection').textContent='Local server unavailable';$('connection').dataset.state='offline';}}
guarded(async()=>{const appConfig=await api('/config');chips(appConfig);if(appConfig.coverage)coverage=appConfig.coverage;coveragePreview();await loadGallery();if(location.hash.length>1)await openBoard(location.hash.slice(1));await health();})();
setInterval(async()=>{if(polling)return;polling=true;try{await refresh();}catch{}finally{polling=false;}},1600);setInterval(health,15000);

// Original composition diagrams: readable at chip size, with text labels alongside.
function pictogram(type){
  const paths={
    'Establishing':'<path d="M4 23 12 14 18 20 27 9 38 23"/><circle cx="22" cy="17" r="2"/><path d="M22 19v5"/>',
    'Medium':'<circle cx="21" cy="10" r="4"/><path d="M13 25v-5a8 8 0 0 1 16 0v5"/>',
    'Close-up':'<ellipse cx="21" cy="16" rx="10" ry="13"/><path d="M16 13h2m6 0h2m-9 8q4 3 8 0"/>',
    'Over shoulder':'<circle cx="10" cy="13" r="6"/><path d="M2 27v-4q8-9 16 0v4"/><circle cx="29" cy="10" r="3"/><path d="M24 20v-3q5-6 10 0v3"/>',
    'Insert':'<circle cx="22" cy="15" r="9"/><path d="m22 9-4 10 9-5-5-5Zm-14 14 6-4m16 5 5 2"/>',
    'Low angle':'<path d="m12 25 4-13h10l5 13M8 23l-3 3m0 0v-7m0 7h7"/><circle cx="21" cy="7" r="4"/>',
    'Detail':'<circle cx="18" cy="14" r="8"/><path d="m24 20 8 7M14 14h8m-4-4v8"/>',
    'Side angle':'<path d="M6 24h30M14 24V12h14v12"/><path d="M4 8l6 3"/><circle cx="4" cy="8" r="1.5"/>',
    'Profile':'<path d="M18 5q7 0 7 7l2 3-2 1v3q0 2-3 2h-2v4"/><path d="M12 27q1-5 6-6"/>',
    'Three-quarter':'<path d="M15 23V12h16v11zM15 12l5-5h16l-5 5M31 23l5-5V7"/>',
    'High angle':'<circle cx="21" cy="20" r="3"/><path d="M16 27q5-5 10 0M4 4l8 6m26-6-8 6"/>',
    'Closing':'<path d="M4 25h34M21 25l-6-14h12z"/><circle cx="21" cy="8" r="2"/>'
  };
  return `<svg viewBox="0 0 42 30" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="butt" stroke-linejoin="miter" aria-hidden="true"><rect x="1" y="1" width="40" height="28" opacity=".4"/>${paths[type]||paths.Medium}</svg>`;
}
function reviewState(key,saved){
  const draft=reviewDrafts.get(key), stored={verdict:saved?.verdict||'pending',note:saved?.note||''};
  if(draft&&(draft.verdict!==stored.verdict||draft.note!==stored.note))return 'Unsaved changes';
  return saved&&(saved.verdict!=='pending'||saved.note)?'Saved':'Not reviewed';
}
// Verdict, then the note on its own full-width row, then the save row: the order you read it is the order you tab through it.
function reviewEditor(shot,take){
  const key=`${board.id}/${shot.id}/${take.id}`, saved=board.review?.find(r=>r.shot===shot.id&&r.take===take.id);
  const draft=reviewDrafts.get(key)||saved||{}, verdict=draft.verdict||'pending';
  return `<form class="review-editor" data-shot="${shot.id}" data-take="${take.id}" aria-label="Review ${shot.id} ${take.id}"><fieldset class="review-verdict"><legend>Verdict</legend><div class="seg">${['pass','fail','pending'].map(value=>`<label class="seg-${value}"><input type="radio" name="verdict" value="${value}" ${verdict===value?'checked':''}><span>${{pending:'Pending',pass:'Pass',fail:'Fail'}[value]}</span></label>`).join('')}</div></fieldset><label class="review-note">Note<textarea name="note" maxlength="400" rows="5">${escapeHTML(draft.note||'')}</textarea></label><div class="review-foot"><span class="review-state">${reviewState(key,saved)}</span><button type="submit" class="quiet">Save review</button></div></form>`;
}
function bindReviewEditors(root){
  document.querySelectorAll(`${root} .review-editor`).forEach(form=>{
    const key=`${board.id}/${form.dataset.shot}/${form.dataset.take}`;
    const values=()=>({verdict:form.elements.verdict.value,note:form.elements.note.value});
    form.oninput=form.onchange=()=>{reviewDrafts.set(key,values());const state=form.querySelector('.review-state');if(state)state.textContent=reviewState(key,board.review?.find(r=>r.shot===form.dataset.shot&&r.take===form.dataset.take));};
    form.onsubmit=guarded(async event=>{
      event.preventDefault();
      const data=values(), button=form.querySelector('button'), focused=document.activeElement===button;if(button.ariaBusy==='true')return;button.ariaDisabled='true';button.ariaBusy='true';button.textContent='Saving…';
      try{
        await api(`/boards/${board.id}/shots/${form.dataset.shot}/takes/${form.dataset.take}/review`,'PUT',data);
        if(!reviewDrafts.has(key)||JSON.stringify(reviewDrafts.get(key))===JSON.stringify(data))reviewDrafts.delete(key);
        await refresh();toast('Review saved.');
        // The saved form is drawn again; a keyboard user stays on its Save button.
        if(focused)document.querySelector(`${root} .review-editor[data-shot="${form.dataset.shot}"][data-take="${form.dataset.take}"] button`)?.focus();
      }finally{button.ariaDisabled=null;button.ariaBusy=null;button.textContent='Save review';}
    });
  });
}
async function loadGallery(){
  examples=await api('/examples');
  const featured=examples[0], b=featured.board;
  const picked=s=>s.takes.find(t=>t.id===s.picked);
  const url=(ex,s)=>`/api/examples/${ex.slug}/images/${picked(s).image}`;
  const picks=b.shots.map(picked);
  $('featured-board').innerHTML=`<p class="scene-line">${escapeHTML(b.config.scene)}</p><div class="setups">${b.shots.map((s,i)=>`<button class="setup" data-example="${featured.slug}" data-cut="${s.id}" aria-label="Open ${NN(i)} ${escapeHTML(s.title)}"><span class="setup-no">${NN(i)}</span><span class="stem" aria-hidden="true"></span><span class="frame">${img(url(featured,s),`${s.title} selected render`,SIZES.lined,i===0)}</span><span class="cap"><b>${escapeHTML(s.title)}</b>${isImported(picks[i])?'<span class="src">Imported reference</span>':''}</span></button>`).join('')}</div>`;
  setRatios('#featured-board .setup',picks);
  // Phones set two frames a row; each pair shares the row by its true widths.
  document.querySelectorAll?.('#featured-board .setup').forEach((el,i)=>{const pair=picks.slice(i-i%2,i-i%2+2).map(t=>t.settings.width/t.settings.height),sum=pair.reduce((a,x)=>a+x,0);el.style.setProperty('--mw',((t=>t.settings.width/t.settings.height)(picks[i])/sum).toFixed(4));});
  $('home-open').dataset.example=featured.slug;
  $('example-gallery').innerHTML=examples.map(ex=>{
    const h=ex.board.continuity?.enabled?ex.board.continuity.hero:null, at=h?ex.board.shots.findIndex(s=>s.id===h.shot_id):-1;
    const meta=at>=0?`Redrawn from ${NN(at)}`:'SDXL takes';
    return `<button class="gallery-card" data-example="${ex.slug}"><span class="gallery-strip">${ex.board.shots.map((s,i)=>`<span class="mini"><span class="mini-no">${NN(i)}</span><span class="mini-frame">${img(url(ex,s),`${s.title} pick`,SIZES.mini)}</span></span>`).join('')}</span><span class="gallery-caption"><span>${escapeHTML(ex.label)}</span><small>${meta}</small></span><span class="gallery-scene">${escapeHTML(ex.board.config.scene)}</span></button>`;
  }).join('');
  examples.forEach(ex=>setRatios(`.gallery-card[data-example="${ex.slug}"] .mini`,ex.board.shots.map(picked)));
  document.querySelectorAll('[data-example]').forEach(el=>el.onclick=guarded(async()=>{const opened=await api(`/examples/${el.dataset.example}/open`,'POST');await openBoard(opened.id);window.scrollTo(0,0);if(el.dataset.cut)openCompare(el.dataset.cut);}));
  coveragePreview();
}
// The coverage template drops faces, hands and shoulders when the scene has no person.
let coverage={person:['Establishing','Medium','Close-up','Over shoulder','Insert','Low angle','Profile','High angle','Closing'],object:['Establishing','Medium','Detail','Side angle','Insert','Low angle','Three-quarter','High angle','Closing'],person_words:[]};
function sceneHasPerson(){
  if($('character').value.trim())return true;
  return coverage.person_words.length>0&&new RegExp(`\\b(?:${coverage.person_words.join('|')})s?\\b`,'i').test($('scene').value);
}
// One setup line per cut drops from the scene field onto the coverage template, the same lines the board and home draw.
function coveragePreview(){
  const count=Number($('count').value)||6, types=(sceneHasPerson()||!$('scene').value.trim()?coverage.person:coverage.object).slice(0,count);
  $('coverage-preview').ariaLabel=`Coverage for ${types.length} cuts: ${types.join(', ')}`;
  $('coverage-preview').innerHTML=`<div class="setups even">${types.map((type,i)=>`<div class="setup"><span class="setup-no">${NN(i)}</span><span class="stem" aria-hidden="true"></span><div class="composition-chip">${pictogram(type)}<span>${type}</span></div></div>`).join('')}</div>`;
}
$('scene').oninput=()=>{coveragePreview();if($('scene').ariaInvalid==='true')sceneValid();};$('character').oninput=$('count').onchange=()=>coveragePreview();
// The composer says what is missing under the scene field, instead of the browser's own bubble.
function sceneValid(){const empty=!$('scene').value.trim();$('scene-error').hidden=!empty;$('scene-error').textContent=empty?'Describe the scene first.':'';$('scene').ariaInvalid=empty?'true':null;if(empty)$('scene').focus();return !empty;}
// What the export ZIP holds for the current picks, named as export_board names them.
function zipFiles(b){
  const names=[], refs=new Set();
  for(const s of b.shots){
    const t=s.takes.find(x=>x.id===s.picked&&x.status==='succeeded');if(!t)return null;
    names.push(`stills/${s.id}.png`);
    if(t.reference&&!refs.has(t.reference.image)){refs.add(t.reference.image);names.push(t.reference.image);}
    if(t.source?.type!=='imported')names.push(`workflows/${s.id}.api.json`);
    if(t.submitted_workflow)names.push(`workflows/${s.id}.submitted.api.json`);
  }
  return [...names,'storyboard-landscape.png','storyboard-portrait.png','manifest.json'];
}
function renderExport(){
  const names=zipFiles(board);if(!names)return;
  const picks=board.shots.map(s=>s.takes.find(t=>t.id===s.picked));
  const count=prefix=>names.filter(n=>n.startsWith(prefix)).length;
  const built=board.shots.map((s,i)=>i).filter(i=>picks[i].source?.type!=='imported'), submitted=built.filter(i=>picks[i].submitted_workflow);
  const refs=names.filter(n=>n.startsWith('references/'));
  const short=n=>n.replace(/^(references\/)([0-9a-f]{6})[0-9a-f]+([0-9a-f]{4})(\.png)$/,'$1$2…$3$4');
  const groups=[
    ['Storyboards',`2 PNG`,['storyboard-landscape.png','storyboard-portrait.png']],
    ['Stills',`${count('stills/')} PNG`,`stills/${board.shots[0].id}.png … stills/${board.shots.at(-1).id}.png`],
    built.length&&['ComfyUI workflows',`${count('workflows/')} JSON`,submitted.length===built.length?`workflows/sNN.api.json and sNN.submitted.api.json for ${setupRanges(built)}`:`workflows/sNN.api.json for ${setupRanges(built)}${submitted.length?`; sNN.submitted.api.json for ${setupRanges(submitted)}`:''}`],
    refs.length&&['Hero reference',`${refs.length} PNG`,refs.map(short).join(', ')],
    ['Manifest','1 JSON','manifest.json: scene, picks, seeds, verdicts, pinned models'],
  ].filter(Boolean);
  $('zip-summary').textContent=`${names.length} files`;
  // A list of file names breaks between names, never at a hyphen inside one.
  $('zip-files').innerHTML=groups.map(([name,n,path])=>`<li><b>${name}</b><span class="n">${n}</span><span class="p">${Array.isArray(path)?path.map(f=>`<span class="f">${escapeHTML(f)}</span>`).join(', '):escapeHTML(path)}</span></li>`).join('');
  $('export-picks').innerHTML=board.shots.map((s,i)=>`<li><span class="setup-no">${NN(i)}</span><span class="pick-title">${escapeHTML(s.title)}</span><span class="pick-take">${TAKE(picks[i])}</span>${verdictMark(reviewFor(s,picks[i]))}${sourceLabel(picks[i])?`<span class="pick-src">${sourceLabel(picks[i])}</span>`:''}</li>`).join('');
}
let storyboardRequest=0;
const storyboardLayout=()=>document.querySelector?.('input[name="storyboard-layout"]:checked')?.value||'landscape';
async function previewStoryboard(){
  const request=++storyboardRequest, layout=storyboardLayout();
  $('storyboard-preview').hidden=true;$('download-storyboard').hidden=true;$('storyboard-error').hidden=false;$('storyboard-error').textContent='Preparing storyboard…';
  $('storyboard-preview').dataset.layout=layout;
  const path=`/api/boards/${board.id}/storyboard?layout=${layout}`;
  const response=await fetch(path).catch(()=>{throw new Error(offline());});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(detail(error,'The storyboard could not be drawn. Switch the layout or reopen Export storyboard to try again.'));}
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
// Phones open on the portrait sheet, the one that fits their screen.
$('storyboard').onclick=()=>{const portrait=document.querySelector?.(`input[name="storyboard-layout"][value="${phone()?'portrait':'landscape'}"]`);if(portrait)portrait.checked=true;renderExport();showDialog($('storyboard-dialog'));safePreview();};
$('storyboard-layout').onchange=safePreview;
$('close-storyboard').onclick=()=>$('storyboard-dialog').close();
function navigateCut(delta){const index=board.shots.findIndex(s=>s.id===currentShot);openCompare(board.shots[(index+delta+board.shots.length)%board.shots.length].id);$('compare-dialog').scrollTop=0;}
$('previous-cut').onclick=()=>navigateCut(-1);$('next-cut').onclick=$('next-cut-2').onclick=()=>navigateCut(1);
document.addEventListener('keydown',event=>{
  if(['INPUT','TEXTAREA','SELECT','SUMMARY'].includes(event.target.tagName)||event.altKey||event.ctrlKey||event.metaKey)return;
  if(!board||!['ArrowLeft','ArrowRight'].includes(event.key))return;
  if($('storyboard-dialog').open||$('boards-dialog').open||$('image-dialog').open)return;
  event.preventDefault();const delta=event.key==='ArrowRight'?1:-1;
  if($('compare-dialog').open)navigateCut(delta);
  else{const cards=[...document.querySelectorAll('.shot-hero[data-compare]')];const index=cards.indexOf(document.activeElement);cards[(index+delta+cards.length)%cards.length]?.focus();}
});
window.addEventListener('hashchange',guarded(async()=>{const id=location.hash.slice(1);if(id&&id!==board?.id)await openBoard(id);else if(!id&&$('composer').hidden){board=null;$('workspace').hidden=true;$('home').hidden=false;}}));

$('import-reference').onclick=()=>$('reference-file').click();
$('reference-file').onchange=guarded(async event=>{
  const file=event.target.files[0];if(!file)return;
  try {
    const response=await fetch(`/api/boards/${board.id}/shots/${currentShot}/import`,{method:'POST',headers:{'Content-Type':file.type},body:file}).catch(()=>{throw new Error(offline());});
    const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(detail(data,'The reference could not be imported. Try again.'));
    await refresh();toast('Reference imported.');
  } finally { event.target.value=''; }
});
