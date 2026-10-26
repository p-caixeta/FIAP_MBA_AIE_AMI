const $ = id => document.getElementById(id);
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const money = value => new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'}).format(value);
const saved = (() => { try { return JSON.parse(localStorage.getItem('aula07') || '{}'); } catch { return {}; } })();
const state = {session:crypto.randomUUID(), current:null, previous:null, input:null, comparing:false, ...saved,
  meta:null, busy:false, statuses:{}, events:[], upload:''};

function persist() {
  const {session,current,previous,input,comparing} = state;
  try { localStorage.setItem('aula07', JSON.stringify({session,current,previous,input,comparing})); }
  catch { notice('A comparação continua nesta aba; não houve espaço para guardá-la no navegador.'); }
}
function notice(text, error=false) { $('notice').textContent=text; $('notice').className=error?'error':''; }
function busy(value) {
  state.busy=value;
  for (const id of ['execute','approve','reject','save-revision','new-session']) $(id).disabled=value;
  $('execute').textContent=value?'Executando…':state.current?'▶ Executar novamente':'▶ Executar';
}
function node(id, label, subtitle='') {
  return `<div class="node ${state.statuses[id] || ''}" data-node="${escapeHTML(id)}">${escapeHTML(label)}${subtitle?`<small>${escapeHTML(subtitle)}</small>`:''}</div>`;
}
function graph(settings) {
  const s=settings, arrow='<span class="arrow" aria-hidden="true">→</span>';
  const tags=[s.rag!=='off'?`RAG · ${s.rag==='fixed'?'obrigatório':'ferramenta'}`:'',s.memory?'Memória':''].filter(Boolean);
  let html=`<div class="graph-group">${node('prepare','Pedido / contexto')}<div class="tags">${tags.map(t=>`<span class="tag">${t}</span>`).join('')}</div></div>`;
  if(s.image) html+=arrow+node('vision','Imagem');
  if(s.architecture==='team') html+=arrow+`<div class="branches">${node('programme','Programa','Equipe · paralelo')}${node('budget','Orçamento','Equipe · paralelo')}</div>`;
  html+=arrow+`<div class="graph-group">${node('planner',s.architecture==='team'?'Síntese':'Planejador')}`;
  if(s.architecture==='subagent') html+=node('budget','Orçamento','Subagente delegado');
  if(s.mcp.length) html+=`<div class="external-nodes">${s.mcp.map(alias=>node(`mcp:${alias}`,alias,'Ferramentas · MCP')).join('')}</div>`;
  html+='</div>';
  if(s.a2a.length) html+=arrow+`<div class="external-nodes">${s.a2a.map(alias=>node('external',alias,'Agente externo · A2A')).join('')}</div>`;
  if(s.hitl) html+=arrow+node('review','Revisão humana')+arrow+node('save','Plano salvo');
  $('graph').innerHTML=html;
  $('architecture').textContent={single:'Um agente',subagent:'Agente com subagente',team:'Equipe de especialistas'}[s.architecture] || s.architecture;
}
function capabilities() {
  if(!state.meta) return;
  const s=state.meta.settings, result=state.current;
  const facts=[`Ferramentas locais: ${s.local_tools.join(', ') || 'nenhuma'}`,`RAG: ${s.rag}`,`Memória: ${s.memory?'ativa':'desativada'}`,
    `Arquitetura: ${s.architecture}`,`Imagem: ${s.image?'ativa':'desativada'}`,`Revisão humana: ${s.hitl?'ativa':'desativada'}`];
  let html=facts.map(t=>`<p>${escapeHTML(t)}</p>`).join('');
  if(s.mcp.length) html+=`<h4>MCP configurado</h4><p>${s.mcp.map(escapeHTML).join(', ')}</p>`;
  if(s.a2a.length) html+=`<h4>A2A configurado</h4><p>${s.a2a.map(escapeHTML).join(', ')}</p>`;
  if(result && (Object.keys(result.catalog).length || Object.keys(result.agents).length))
    html+=`<h4>Catálogo da última execução</h4><pre>${escapeHTML(JSON.stringify({mcp:result.catalog,a2a:result.agents},null,2))}</pre>`;
  $('capabilities').innerHTML=html;
  $('memory-mode').textContent=s.memory?'A conversa e a preferência entram no contexto.':'A memória está desativada no código; os dados abaixo não entram no agente.';
  $('image-controls').hidden=!s.image;
}
function card(result, label) {
  const p=result.plan;
  let html=`<div class="card-label"><span>${label}</span><span>${escapeHTML(result.id.slice(0,8))}</span></div><h3>${escapeHTML(p.title)}</h3>`;
  html+=`<p class="cost-label">${result.total===null?'Orçamento a confirmar':'Orçamento total'}</p><div class="total">${result.total===null?'—':money(result.total)}</div>`;
  if(p.budget_limit && result.total!==null) html+=`<span class="pill ${result.total>p.budget_limit?'over':''}">${result.total>p.budget_limit?'Acima do orçamento':'Dentro do orçamento'} · limite ${money(p.budget_limit)}</span>`;
  html+=(p.costs || []).map(c=>`<div class="cost-row"><span>${escapeHTML(c.label)}<small>${escapeHTML(c.quantity)} × ${money(c.unit_price)}</small></span><strong>${money(c.quantity*c.unit_price)}</strong></div>`).join('');
  html+=`<p class="plan-text">${escapeHTML(p.summary)}</p>`;
  if(p.programme?.length) html+=`<ul class="plan-list">${p.programme.map(t=>`<li>${escapeHTML(t)}</li>`).join('')}</ul>`;
  if(p.notes?.length) html+=`<div class="note">${p.notes.map(escapeHTML).join('<br>')}</div>`;
  return html;
}
function renderResults() {
  const r=state.current, show=Boolean(r?.plan?.title);
  $('empty').hidden=show; $('comparison').hidden=!show;
  $('compare').disabled=!state.previous || !show;
  $('compare').setAttribute('aria-pressed',String(state.comparing));
  $('result-heading').textContent=show?'O que mudou?':'Vamos construir juntos';
  $('execute').textContent=state.busy?'Executando…':show?'▶ Executar novamente':'▶ Executar';
  $('previous').hidden=!(show && state.previous && state.comparing);
  $('comparison').classList.toggle('comparing',Boolean(state.previous && state.comparing));
  for(const id of ['review','visual-panel','announcement-panel']) $(id).hidden=true;
  if(!show) return;
  $('current').innerHTML=card(r,'Atual');
  if(state.previous) $('previous').innerHTML=card(state.previous,'Anterior');
  if(state.previous && state.comparing) {
    const old=state.previous;
    const changes=['summary','programme','costs'].filter(k=>JSON.stringify(old.plan[k])!==JSON.stringify(r.plan[k]));
    const delta=old.total!==null && r.total!==null ? old.total-r.total : null;
    const note=document.createElement('p'); note.className='note';
    note.textContent=delta ? `${money(Math.abs(delta))} ${delta>0?'a menos':'a mais'}. ` : '';
    note.textContent+=changes.length?`Mudanças: ${changes.map(k=>({summary:'resumo',programme:'programa',costs:'custos'}[k])).join(', ')}.`:'Confira as mudanças na execução e nas evidências.';
    $('current').append(note);
  }
  $('run-label').textContent=`Execução ${r.id.slice(0,8)} · revisão ${r.revision}`;
  $('visual-panel').hidden=!r.visual; $('visual').textContent=r.visual;
  $('announcement-panel').hidden=!r.plan.announcement; $('announcement').textContent=r.plan.announcement;
  $('source-count').textContent=r.sources.length?`· ${r.sources.length}`:'';
  $('sources').innerHTML=r.sources.length?r.sources.map(s=>`<h4>${escapeHTML(s.id)}</h4><p>${escapeHTML(s.text)}</p>`).join(''):'Nenhuma regra foi recuperada nesta execução.';
  $('memory').textContent=JSON.stringify(r.memory,null,2);
  if(r.settings.hitl && r.plan.kind==='plan') {
    $('review').hidden=false;
    const pending=r.status==='pending';
    $('review-actions').hidden=!pending; $('editor').hidden=!pending;
    $('review-status').textContent={pending:'Aguardando sua decisão',saved:'Plano salvo',rejected:'Proposta rejeitada',draft:'Rascunho'}[r.status];
    $('receipt').textContent=r.receipt?`Arquivo local: ${r.receipt.file}`:'Nenhum plano salvo nesta execução.';
    $('edit-title').value=r.plan.title; $('edit-summary').value=r.plan.summary; $('edit-announcement').value=r.plan.announcement;
  }
  capabilities();
}
function addEvent(event, replay=false) {
  state.events.push(event);
  if(event.kind==='node') state.statuses[event.node]=event.phase;
  if(event.kind==='delegation') state.statuses.budget=event.phase;
  if(event.detail?.tool?.includes('__')) state.statuses[`mcp:${event.detail.tool.split('__')[0]}`]=event.phase;
  if(event.kind==='discovery' && event.title.startsWith('MCP:')) {
    for(const alias of state.meta.settings.mcp) if(event.title.endsWith(alias)) state.statuses[`mcp:${alias}`]='done';
  }
  const detail=document.createElement('details'); detail.className=`event ${event.phase}`;
  const summary=document.createElement('summary'); summary.textContent=`${state.events.length}. ${event.title}`;
  const pre=document.createElement('pre'); pre.textContent=JSON.stringify(event.detail,null,2);
  detail.append(summary,pre); $('events').append(detail);
  if(!replay && state.meta) graph(state.meta.settings);
}
function showEvents(result) {
  state.events=[]; state.statuses={}; $('events').replaceChildren();
  for(const event of result.events) addEvent(event,true);
  if(result.status==='pending') state.statuses.review='waiting';
  if(result.settings.hitl && !result.receipt) state.statuses.save='pending';
  if(state.meta) graph(result.settings);
}
async function stream(url, payload, isReview=false) {
  busy(true); notice(isReview?'Registrando sua decisão…':'Executando o código carregado…');
  state.events=[]; state.statuses={}; $('events').replaceChildren(); graph(state.meta.settings);
  try {
    const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    if(!response.ok) throw new Error((await response.json()).error || `HTTP ${response.status}`);
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='';
    function consume(line) {
      if(!line.trim()) return;
      const {type,data}=JSON.parse(line);
      if(type==='started') { state.meta.settings=data.settings; graph(data.settings); }
      if(type==='event') addEvent(data);
      if(type==='error') throw new Error(data.message);
      if(type==='result') {
        if(!isReview) { state.previous=state.current; state.comparing=Boolean(state.previous); }
        state.current=data; persist(); renderResults(); showEvents(data);
        notice(data.status==='pending'?'A execução está pausada. Revise a proposta antes de salvar.':data.status==='saved'?'Plano aprovado e salvo localmente.':'Execução concluída. Inspecione os passos e compare o resultado.');
      }
    }
    while(true) { const {value,done}=await reader.read(); if(done) break; buffer+=decoder.decode(value,{stream:true}); const lines=buffer.split('\n'); buffer=lines.pop(); lines.forEach(consume); }
    buffer+=decoder.decode(); if(buffer.trim()) consume(buffer);
  } catch(error) { notice(`${error.message} O resultado anterior continua disponível.`,true); }
  finally { busy(false); }
}
async function loadMeta() {
  try {
    const response=await fetch('/api/meta'); if(!response.ok) throw new Error(); const meta=await response.json();
    const changed=state.meta && state.meta.version!==meta.version; state.meta=meta;
    $('version').textContent=`Código ${meta.version}`;
    if(!$('message').value) $('message').value=state.input?.message || meta.default_request;
    if(changed && !state.busy) { state.statuses={}; notice('Código atualizado. Execute novamente para comparar.'); }
    if(!state.busy) graph(meta.settings);
    capabilities();
  } catch { $('version').textContent='Servidor indisponível'; }
}
$('request-form').addEventListener('submit',event=>{
  event.preventDefault(); if(state.busy) return;
  if(!state.meta) {notice('Aguarde a conexão com o servidor local.',true);return;}
  const input={message:$('message').value.trim(), image:state.meta.settings.image?(state.upload || ($('use-kit').checked?'kit':'')):''};
  const same=state.input && JSON.stringify(input)===JSON.stringify(state.input);
  const payload={...input,session:state.session,replay_of:same?state.current?.id:null}; state.input=input;
  $('repeat-hint').textContent=same?'Repetição com o contexto inicial da execução anterior.':'Novo turno da conversa.';
  stream('/api/run',payload);
});
$('compare').onclick=()=>{state.comparing=!state.comparing;persist();renderResults();};
$('new-session').onclick=()=>{
  state.session=crypto.randomUUID(); state.previous=state.current; state.current=null; state.input=null; state.comparing=false;
  $('message').value=state.meta.default_request; $('memory').textContent=''; $('run-label').textContent='';
  $('sources').textContent='Nenhuma regra recuperada nesta conversa.'; $('source-count').textContent=''; $('events').replaceChildren();
  state.statuses={}; graph(state.meta.settings); persist(); renderResults();
  notice('Nova conversa. A preferência persistente continua disponível quando a memória estiver ativa.');
};
$('use-kit').onchange=()=>{state.upload='';$('upload').value='';$('preview').src='/dados/sala.png';$('preview').hidden=!$('use-kit').checked;};
$('upload').onchange=()=>{
  const file=$('upload').files[0]; if(!file) return;
  if(file.size>2*1024*1024) {notice('Escolha uma imagem de até 2 MB.',true);$('upload').value='';return;}
  const reader=new FileReader();reader.onload=()=>{state.upload=reader.result;$('use-kit').checked=false;$('preview').src=reader.result;$('preview').hidden=false;};reader.readAsDataURL(file);
};
$('inspect-memory').onclick=async()=>{const r=await fetch(`/api/memory/${state.session}`);const m=await r.json();$('memory').textContent=JSON.stringify(m,null,2);$('preference').value=m.preference;};
async function preference(value) {const r=await fetch('/api/preference',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({value})});if(r.ok) notice(value?'Preferência guardada para próximas conversas.':'Preferência removida.');}
$('save-preference').onclick=()=>preference($('preference').value);
$('forget-preference').onclick=()=>{$('preference').value='';preference('');};
function decide(action) {
  const r=state.current;if(!r || state.busy) return;
  const payload={action,revision:r.revision};
  if(action==='edit') Object.assign(payload,{title:$('edit-title').value,summary:$('edit-summary').value,announcement:$('edit-announcement').value});
  $('editor').open=false; stream(`/api/review/${r.id}`,payload,true);
}
$('approve').onclick=()=>decide('approve');$('reject').onclick=()=>decide('reject');$('save-revision').onclick=()=>decide('edit');
async function init() {
  await loadMeta();
  if(state.input?.image==='kit') {$('use-kit').checked=true;$('preview').hidden=false;}
  else if(state.input?.image) {state.upload=state.input.image;$('preview').src=state.upload;$('preview').hidden=false;}
  if(state.current) {
    try {const r=await fetch(`/api/runs/${state.current.id}`);if(r.ok) state.current=await r.json();} catch {}
    renderResults();showEvents(state.current);
  }
  setInterval(loadMeta,2500);
}
init();
