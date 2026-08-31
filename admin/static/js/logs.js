const fields=['q','ct','level','kind','event','result','session_id','request_id','trace_id','span_id','from_ts','to_ts'];
const RANGE_MS={"15m":15*60*1000,"1h":60*60*1000,"6h":6*60*60*1000,"24h":24*60*60*1000};
let timer=null;
let selectedKey=null;

function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));}
function link(k,v){return v?`<a href="/logs?${encodeURIComponent(k)}=${encodeURIComponent(v)}">${esc(v)}</a>`:'';}
function clip(value){return String(value??'').length>120?String(value).slice(0,117)+'…':String(value??'');}
function rowKey(x){return [x.timestamp,x.ct,x.span_id,x.event].join('|');}

function extractRequestText(x){
  const candidates=[x?.params?.input?.text,x?.input?.text,x?.payload?.input?.text,x?.params?.text,x?.text,x?.message?.input?.text];
  return candidates.find(v=>typeof v==='string'&&v.trim())?.trim()||'';
}
function extractResponseText(x){
  const candidates=[x?.params?.response?.text,x?.response?.text,x?.payload?.response?.text,x?.response_text,x?.params?.response_text,x?.message?.response?.text];
  return candidates.find(v=>typeof v==='string'&&v.trim())?.trim()||'';
}
function buildParams(){
  const p=new URLSearchParams();
  fields.forEach(k=>{const e=document.getElementById(k);if(e&&e.value)p.set(k,e.value)});
  return p;
}
function setActiveRange(range){
  document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',b.dataset.range===range));
}
function applyRange(range,{reload=true}={}){
  const from=document.getElementById('from_ts');const to=document.getElementById('to_ts');
  if(range==='all'){from.value='';to.value='';}
  else {from.value=new Date(Date.now()-RANGE_MS[range]).toISOString();to.value='';}
  setActiveRange(range);
  if(reload) load();
}
function defaultRange(){
  const p=new URLSearchParams(location.search);
  if(!p.has('from_ts')&&!p.has('to_ts')) applyRange('15m',{reload:false});
}
function copyButton(label,value){
  if(!value)return '';
  return `<button type="button" class="copy-button" data-copy="${esc(value)}">Copy ${esc(label)}</button>`;
}
async function writeClipboard(value){
  const text=String(value??'');
  if(navigator.clipboard&&typeof navigator.clipboard.writeText==='function'){
    try{await navigator.clipboard.writeText(text);return true;}catch(_error){}
  }
  const textarea=document.createElement('textarea');
  textarea.value=text;textarea.setAttribute('readonly','');
  textarea.style.position='fixed';textarea.style.opacity='0';textarea.style.pointerEvents='none';
  document.body.appendChild(textarea);textarea.focus();textarea.select();
  let copied=false;
  try{copied=document.execCommand('copy');}finally{document.body.removeChild(textarea);}
  if(!copied)throw new Error('Clipboard copy failed');
  return true;
}
function bindCopyButtons(root=document){
  root.querySelectorAll('[data-copy]').forEach(button=>button.onclick=async()=>{
    const old=button.textContent;
    try{await writeClipboard(button.dataset.copy||'');button.textContent='Copied';}
    catch(_error){button.textContent='Copy failed';}
    setTimeout(()=>button.textContent=old,900);
  });
}

async function load(){
  const p=buildParams();
  const r=await fetch('/admin-api/logs?'+p);const d=await r.json();
  document.getElementById('error').textContent=d.error||'';
  const tb=document.getElementById('rows');tb.innerHTML='';
  for(const x of d.items){
    const tr=document.createElement('tr');const elapsed=x.span_elapsed_ms??x.trace_elapsed_ms??x.request_elapsed_ms??x.session_elapsed_ms??'';
    const input=extractRequestText(x);
    tr.dataset.rowKey=rowKey(x);if(tr.dataset.rowKey===selectedKey)tr.classList.add('selected');
    tr.innerHTML=`<td>${esc(formatNyraTimestamp(x.timestamp))}</td><td><span class="badge">${esc(x.ct)}</span></td><td class="level-${esc(x.level)}">${esc(x.level)}</td><td class="kind-${esc(x.kind)}">${esc(x.kind)}</td><td class="request-input" title="${esc(input)}">${esc(clip(input))}</td><td>${link('session_id',x.session_id)}</td><td>${link('request_id',x.request_id)}</td><td>${link('trace_id',x.trace_id)}</td><td>${link('span_id',x.span_id)}</td><td>${esc(x.event)}</td><td>${esc(elapsed)}${elapsed!==''?' ms':''}</td><td>${esc(x.result)}</td>`;
    tr.onclick=e=>{if(e.target.closest('a'))return;selectedKey=rowKey(x);document.querySelectorAll('#rows tr').forEach(row=>row.classList.toggle('selected',row===tr));loadRequestDetail(x);};
    tb.appendChild(tr);
  }
}

function renderTimeline(items){
  if(!items.length)return '<p class="muted">No correlated records found.</p>';
  return `<div class="request-timeline">${items.map(x=>`<div class="timeline-entry"><div class="timeline-time">${esc(formatNyraTimestamp(x.timestamp))}</div><div><strong>${esc(x.event||x.kind||'Record')}</strong><div class="timeline-meta">${esc(x.ct||'')} ${x.result?`· ${esc(x.result)}`:''}</div></div></div>`).join('')}</div>`;
}
async function loadRequestDetail(selected){
  const detail=document.getElementById('detail');detail.innerHTML='<div class="detail-loading">Loading request…</div>';
  let items=[selected];let error='';
  if(selected.request_id){
    const p=new URLSearchParams({request_id:selected.request_id});
    const r=await fetch('/admin-api/logs?'+p);const d=await r.json();items=d.items||items;error=d.error||'';
  }
  items=[...items].sort((a,b)=>String(a.timestamp||'').localeCompare(String(b.timestamp||'')));
  const requestRecord=items.find(x=>extractRequestText(x))||selected;
  const input=extractRequestText(requestRecord);
  const responseRecord=[...items].reverse().find(x=>extractResponseText(x));
  const response=responseRecord?extractResponseText(responseRecord):'';
  const outcome=[...items].reverse().find(x=>x.result||String(x.event||'').includes('FAILED')||String(x.event||'').includes('COMPLETED'));
  const raw=JSON.stringify(selected,null,2);
  detail.innerHTML=`
    <div class="detail-head"><div><span class="eyebrow">Correlated request</span><h3>${esc(selected.request_id||selected.event||'Structured record')}</h3></div><div class="detail-actions">${copyButton('request',selected.request_id)}${copyButton('JSON',raw)}</div></div>
    ${error?`<div class="detail-error">${esc(error)}</div>`:''}
    <section class="detail-section"><h4>Input</h4><div class="detail-value">${input?esc(input):'<span class="muted">No request text on correlated records.</span>'}</div></section>
    <section class="detail-section"><h4>Outcome</h4><div class="detail-value">${outcome?esc(outcome.result||outcome.event):'<span class="muted">No terminal outcome yet.</span>'}</div></section>
    <section class="detail-section"><h4>Response</h4><div class="detail-value">${response?esc(response):'<span class="muted">No response text recorded.</span>'}</div></section>
    <section class="detail-section"><h4>Timeline</h4>${renderTimeline(items)}</section>
    <section class="detail-section"><div class="section-title-row"><h4>Selected record</h4></div><pre class="json">${esc(raw)}</pre></section>`;
  bindCopyButtons(detail);
}

function syncFromUrl(){const p=new URLSearchParams(location.search);fields.forEach(k=>{const e=document.getElementById(k);if(e&&p.has(k))e.value=p.get(k)})}
document.getElementById('apply').onclick=load;
document.getElementById('live').onchange=e=>{if(timer)clearInterval(timer);timer=e.target.checked?setInterval(load,2000):null};
document.querySelectorAll('[data-range]').forEach(b=>b.onclick=()=>applyRange(b.dataset.range));
syncFromUrl();defaultRange();bindCopyButtons();load();
