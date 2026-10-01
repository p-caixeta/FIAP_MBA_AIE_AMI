"use strict";

const state = {
  meta: null, online: false, stage: "fixed_rag", busy: false, conversation: [], runs: [],
  selectedRunId: null, selectedEventSeq: null, selectedChunkId: null,
  lastRequest: null, tab: "events"
};

let exercises = [];
const refs = Object.fromEntries(["server-status","build-id","refresh-meta","stage-select","stage-description","exercise-select","exercise-card","use-question","chat-messages","chat-empty","chat-form","message-input","send-button","new-chat","run-again","run-select","graph-svg","graph-summary","run-metrics","inspector-tabs","events-panel","chunks-panel","details-panel","notice"].map(id => [id, document.getElementById(id)]));

function text(value) { return value == null ? "" : String(value); }
function setNotice(message, kind="") { refs.notice.textContent = message; refs.notice.className = kind; }
function selectedRun() { return state.runs.find(run => run.runId === state.selectedRunId) || null; }
function stageLabel(stage) { return {baseline:"Baseline", fixed_rag:"RAG fixo", agentic_rag:"RAG como ferramenta"}[stage] || stage; }

async function loadMeta(preview=false) {
  refs["server-status"].textContent = "Reconectando…";
  try {
    const response = await fetch(`/api/meta?stage=${encodeURIComponent(state.stage)}`, {cache:"no-store"});
    if (!response.ok) throw new Error("meta indisponível");
    state.meta = await response.json();
    if (!exercises.length) { exercises = state.meta.exercises; populateExercises(); }
    state.online = true;
    refs["server-status"].textContent = state.meta.key_configured ? "Pronto" : "Sem chave";
    refs["server-status"].className = state.meta.key_configured ? "status-ok" : "status-error";
    refs["build-id"].textContent = `build ${state.meta.build_id}`;
    refs["stage-description"].textContent = `Próxima execução: síntese ${state.meta.graph.synthesis}.`;
    if (!state.meta.key_configured) setNotice("Crie .env na raiz com OPENAI_API_KEY e reinicie o servidor.");
    else if (state.runs.length && state.runs.at(-1).buildId !== state.meta.build_id) setNotice("Código atualizado. Repita a pergunta para comparar.");
    else setNotice("");
    if (preview || !selectedRun()) renderGraph(state.meta.graph, null);
    else renderInspector();
  } catch (_) {
    state.online = false;
    refs["server-status"].textContent = "Indisponível";
    refs["server-status"].className = "status-error";
    setNotice("Servidor indisponível; tente novamente após reiniciar.");
  }
  setBusy(state.busy);
}

function populateExercises() {
  for (const exercise of exercises) {
    const option = document.createElement("option");
    option.value = exercise.id; option.textContent = `${exercise.id} — ${exercise.title}`;
    refs["exercise-select"].append(option);
  }
  renderExercise();
}
function activeExercise() { return exercises.find(item => item.id === refs["exercise-select"].value) || exercises[0]; }
function renderExercise() {
  const item = activeExercise();
  refs["exercise-card"].querySelector("summary").textContent = `${item.id} · ${item.title} — ${item.question}`;
  const content = refs["exercise-card"].querySelector("div"); content.replaceChildren();
  for (const line of [`Etapa: ${stageLabel(item.stage)}`, `Onde: ${item.where}`, `Alteração: ${item.change}`, `Observe: ${item.observe}`, `Discussão: ${item.discuss}`]) {
    const p = document.createElement("p"); p.textContent = line; content.append(p);
  }
}

function addBubble(role, content, extra={}) {
  state.conversation.push({role, content, ...extra}); renderChat();
}
function renderChat() {
  const panel = refs["chat-messages"], oldScroll = panel.scrollTop;
  const follow = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
  refs["chat-messages"].replaceChildren();
  refs["chat-empty"].hidden = state.conversation.length > 0;
  for (const message of state.conversation) {
    const bubble = document.createElement("article"); bubble.className = `bubble ${message.role}${message.pending ? " pending" : ""}`;
    const header = document.createElement("header");
    header.textContent = message.role === "user" ? "Você" : `${stageLabel(message.stage || state.stage)} · ${message.buildId ? `build ${message.buildId}` : ""} · ${message.status || ""}`;
    bubble.append(header);
    if (message.role === "assistant" && !message.pending) appendAnswer(bubble, message.content, message.runId, message.citations || []);
    else { const body = document.createElement("div"); body.textContent = message.content; bubble.append(body); }
    for (const warning of message.warnings || []) { const note=document.createElement("p"); note.className="status-error"; note.textContent=warning; bubble.append(note); }
    refs["chat-messages"].append(bubble);
  }
  panel.scrollTop = follow ? panel.scrollHeight : oldScroll;
}
function appendAnswer(parent, answer, runId, citations) {
  const verified = new Set(citations.map(item => item.chunk_id));
  const parts = text(answer).split(/(\[D\d{2}-C\d+\])/g);
  for (const part of parts) {
    const match = /^\[(D\d{2}-C\d+)\]$/.exec(part);
    if (match && verified.has(match[1])) {
      const button = document.createElement("button"); button.type="button"; button.className="citation"; button.textContent=part;
      button.addEventListener("click", () => selectChunk(runId, match[1])); parent.append(button);
    } else parent.append(document.createTextNode(part));
  }
}

function setBusy(busy) {
  state.busy = busy;
  const unavailable = !state.online || !state.meta?.key_configured;
  refs["send-button"].disabled = busy || unavailable;
  refs["new-chat"].disabled = busy; refs["run-again"].disabled = busy || !state.lastRequest || unavailable;
  refs["stage-select"].disabled = busy; refs["exercise-select"].disabled = busy; refs["use-question"].disabled = busy;
  for (const id of ["memory-mode", "context-strategy", "save-profile", "revoke-profile"]) document.getElementById(id).disabled = busy;
  refs["server-status"].textContent = busy ? "Executando…" : (!state.online ? "Indisponível" : (unavailable ? "Sem chave" : "Pronto"));
}

function makeRun(event, question, historySnapshot) {
  const data = event.data;
  return {runId:event.run_id, stage:data.stage, buildId:data.build_id, question, historySnapshot, graph:data.graph, events:[], chunksByQuery:[], nodeStatus:{}, output:null, status:"running", metrics:{model_calls:0,tool_calls:0,searches:0,input_tokens:null,output_tokens:null,elapsed_ms:0}};
}
function applyEvent(event, pending) {
  if (!event || typeof event.run_id !== "string" || !Number.isInteger(event.seq) || event.seq < 1 || typeof event.type !== "string" || !event.data || typeof event.data !== "object") throw new Error("Evento malformado.");
  if (pending.runId && pending.runId !== event.run_id) throw new Error("Protocolo: outro run_id no mesmo stream.");
  if (!pending.runId && event.type !== "run_start") throw new Error("Evento antes de run_start.");
  if (pending.terminal) throw new Error("Evento após o término da execução.");
  let run = state.runs.find(item => item.runId === event.run_id);
  if (event.type === "run_start") {
    if (pending.runId) throw new Error("run_start duplicado.");
    pending.runId = event.run_id;
    run = makeRun(event, pending.question, pending.historySnapshot); state.runs.push(run); state.selectedRunId = run.runId;
    renderRuns();
  }
  if (!run) throw new Error("Evento sem run_start correspondente.");
  if (run.events.some(item => item.seq === event.seq)) return;
  const last = run.events.at(-1); if (last && event.seq < last.seq) setNotice("Aviso de protocolo: sequência fora de ordem.");
  run.events.push(event);
  const data = event.data || {};
  run.metrics.elapsed_ms = event.elapsed_ms;
  if (event.type === "model_start") run.metrics.model_calls += 1;
  if (event.type === "tool_start") run.metrics.tool_calls += 1;
  if (event.type === "retrieval_result") run.metrics.searches += 1;
  if (event.type === "node_start") run.nodeStatus[data.node_id] = "running";
  if (event.type === "node_end") run.nodeStatus[data.node_id] = data.status === "completed" ? "done" : data.status;
  if (event.type === "retrieval_result") run.chunksByQuery.push({query:data.query, hits:data.hits || [], status:data.status, index:data.search_index, topK:data.top_k, omitted:data.omitted_count || 0});
  if (event.type === "run_end") { pending.terminal=true; run.output=data.output; run.metrics=data.metrics; run.status=data.output.status; finishPending(pending, run); }
  if (event.type === "run_error") { pending.terminal=true; run.status="failed"; run.error=data.message; finishPending(pending, run); }
  if (pending.terminal) for (const node of run.graph.nodes) {
    if (!run.nodeStatus[node.id]) run.nodeStatus[node.id] = "skipped";
    else if (run.nodeStatus[node.id] === "running") run.nodeStatus[node.id] = "failed";
  }
  if (state.selectedRunId === run.runId) renderInspector();
}
function finishPending(pending, run) {
  const message = state.conversation.find(item => item.token === pending.token);
  if (message) {
    message.pending=false; message.content=run.output ? run.output.answer : `Erro: ${run.error || "Execução interrompida."}`;
    message.runId=run.runId; message.stage=run.stage; message.buildId=run.buildId; message.citations=run.output?.citations || [];
    message.status=run.status; message.warnings=run.output?.warnings || [];
  }
  renderChat(); renderRuns();
}

async function submitMessage(message, historyOverride=null) {
  const question = message.trim(); if (!question || state.busy || !state.online || !state.meta?.key_configured) return;
  const historySnapshot = historyOverride ?? state.conversation.filter(item => !item.pending && item.status !== "failed").slice(-8).map(item => ({role:item.role, content:item.content.slice(0,4000)}));
  const pending = {token:crypto.randomUUID(), question, historySnapshot};
  state.lastRequest = {question, historySnapshot}; addBubble("user", question); addBubble("assistant", "Executando…", {pending:true, token:pending.token}); setBusy(true);
  try {
    const response = await fetch("/api/chat", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({integration:document.getElementById("integration-mode").value, transport:document.getElementById("mcp-transport").value, message:question, stage:state.stage, thread_id:threadId, memory_mode:document.getElementById("memory-mode").value, strategy:document.getElementById("context-strategy").value})});
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.error?.message || "Não foi possível iniciar a execução."); }
    await readNdjson(response, event => applyEvent(event, pending));
    if (!pending.terminal) throw new Error("Execução interrompida antes do evento terminal.");
  } catch (error) {
    const fakeRun = state.runs.find(run => run.runId === pending.runId) || {runId:"", stage:state.stage, buildId:"", output:null};
    fakeRun.status="failed"; fakeRun.error=error.message; fakeRun.output=null;
    for (const node of fakeRun.graph?.nodes || []) {
      if (fakeRun.nodeStatus[node.id] === "running") fakeRun.nodeStatus[node.id] = "failed";
      else if (!fakeRun.nodeStatus[node.id]) fakeRun.nodeStatus[node.id] = "skipped";
    }
    finishPending(pending, fakeRun); renderInspector(); setNotice(error.message, "status-error");
  } finally { setBusy(false); await inspectMemory(); }
}

async function readNdjson(response, onEvent) {
  const reader = response.body.getReader(), decoder = new TextDecoder("utf-8"); let buffer="";
  const consume = () => { let end; while ((end=buffer.indexOf("\n")) >= 0) { const line=buffer.slice(0,end).trim(); buffer=buffer.slice(end+1); if (line) onEvent(JSON.parse(line)); } };
  try {
    while (true) { const {value,done}=await reader.read(); buffer += decoder.decode(value || new Uint8Array(), {stream:!done}); consume(); if (done) break; }
    buffer += decoder.decode(); if (buffer.trim()) onEvent(JSON.parse(buffer));
  } finally { await reader.cancel(); reader.releaseLock(); }
}

function renderRuns() {
  const previous=refs["run-select"].value; refs["run-select"].replaceChildren();
  if (!state.runs.length) { const option=document.createElement("option"); option.value=""; option.textContent="Nenhuma execução"; refs["run-select"].append(option); return; }
  state.runs.forEach((run,index) => { const option=document.createElement("option"); option.value=run.runId; option.textContent=`Execução ${index+1} · ${stageLabel(run.stage)} · ${run.buildId}`; refs["run-select"].append(option); });
  refs["run-select"].value = state.selectedRunId || previous;
}

function renderInspector() {
  renderTabs();
  const run=selectedRun(); renderGraph(run?.graph || state.meta?.graph, run); renderEvents(run); renderChunks(run); renderDetails(run); renderMetrics(run);
}
function renderMetrics(run) {
  const metrics=run?.metrics; if (!metrics) { refs["run-metrics"].textContent="Modelo: — · Ferramentas: — · Buscas: — · Tempo: —"; return; }
  const tokens=metrics.input_tokens == null ? "não informado" : `${metrics.input_tokens}/${metrics.output_tokens}`;
  refs["run-metrics"].textContent=`Modelo: ${metrics.model_calls} · Ferramentas: ${metrics.tool_calls} · Buscas: ${metrics.searches} · Tempo: ${(metrics.elapsed_ms/1000).toLocaleString("pt-BR",{maximumFractionDigits:1})}s · Tokens: ${tokens}`;
}
function renderGraph(graph, run) {
  const svg=refs["graph-svg"], ns="http://www.w3.org/2000/svg"; svg.replaceChildren(); if (!graph) return;
  const positions={__start__:[320,25],prepare:[320,80],logistics:[155,165],resolution:[485,165],retrieve_policies:[320,250],synthesize:[320,graph.stage==="fixed_rag"?335:255],__end__:[320,graph.stage==="fixed_rag"?410:330]};
  svg.setAttribute("viewBox", `0 0 640 ${graph.stage === "fixed_rag" ? 440 : 360}`);
  const edgeLayer=document.createElementNS(ns,"g"), nodeLayer=document.createElementNS(ns,"g"); svg.append(edgeLayer,nodeLayer);
  const defs=document.createElementNS(ns,"defs"), marker=document.createElementNS(ns,"marker"), arrow=document.createElementNS(ns,"path");
  marker.setAttribute("id","arrow"); marker.setAttribute("viewBox","0 0 10 10"); marker.setAttribute("refX","9"); marker.setAttribute("refY","5"); marker.setAttribute("markerWidth","6"); marker.setAttribute("markerHeight","6"); marker.setAttribute("orient","auto"); arrow.setAttribute("d","M 0 0 L 10 5 L 0 10 z"); arrow.setAttribute("fill","#b4bdca"); marker.append(arrow); defs.append(marker); svg.prepend(defs);
  for (const edge of graph.edges) { const a=positions[edge.from],b=positions[edge.to]; if (!a||!b) continue; const path=document.createElementNS(ns,"path"); const error=edge.to === "__end__" && edge.from === "prepare"; path.setAttribute("class", `edge ${error ? "error" : ""}`); path.setAttribute("marker-end","url(#arrow)"); path.setAttribute("d", error ? `M ${a[0]+100} ${a[1]} H 620 V ${b[1]} H ${b[0]+100}` : `M ${a[0]} ${a[1]+22} L ${b[0]} ${b[1]-22}`); const title=document.createElementNS(ns,"title"); title.textContent=error?"pedido ausente/inválido":`${edge.from} → ${edge.to}`; path.append(title); edgeLayer.append(path); }
  for (const node of graph.nodes) { const point=positions[node.id]; if (!point) continue; const group=document.createElementNS(ns,"g"), status=run?.nodeStatus[node.id] || "pending"; group.setAttribute("role","button"); group.setAttribute("tabindex","0");
    const rect=document.createElementNS(ns,"rect"); rect.setAttribute("x",point[0]-100);rect.setAttribute("y",point[1]-22);rect.setAttribute("width",200);rect.setAttribute("height",44);rect.setAttribute("rx",8);rect.setAttribute("class",`node ${status}`); group.append(rect);
    const label=document.createElementNS(ns,"text");label.setAttribute("x",point[0]);label.setAttribute("y",point[1]-2);label.setAttribute("class","node-label"); label.textContent=node.id.startsWith("__") ? node.id.replaceAll("_","") : node.label;group.append(label);
    const note=document.createElementNS(ns,"text");note.setAttribute("x",point[0]);note.setAttribute("y",point[1]+13);note.setAttribute("class","node-state");note.textContent=(node.id==="synthesize" ? `${graph.synthesis} · ` : "") + ({pending:"pendente",running:"executando",done:"concluído",partial:"parcial",failed:"erro",skipped:"não executado"}[status] || status);group.append(note);
    const select=()=>{ state.selectedEventSeq=run?.events.find(item => item.data?.node_id===node.id)?.seq || null; state.tab="events"; renderInspector(); }; group.addEventListener("click",select);group.addEventListener("keydown",event=>{if(event.key==="Enter"||event.key===" "){event.preventDefault();select();}});nodeLayer.append(group);
  }
  const unknown = graph.nodes.some(node => !positions[node.id]);
  refs["graph-summary"].textContent= unknown ? `Novo nó sem posição visual. Nós: ${graph.nodes.map(n=>n.id).join(", ")}. Arestas: ${graph.edges.map(e=>`${e.from} → ${e.to}`).join("; ")}` : `${graph.nodes.length} nós · ${graph.edges.length} conexões · ${graph.synthesis} · ${run?.status || "Próxima execução"}`;
}
function eventSummary(event) { const data=event.data||{}; if(data.name) return `${data.name}(${Object.values(data.arguments||{})[0] ?? ""})`; if(data.label) return data.label; if(data.query) return `busca: ${data.query}`; return event.type; }
function renderEvents(run) {
  const panel=refs["events-panel"], oldScroll=panel.scrollTop;
  const follow=panel.scrollHeight-panel.scrollTop-panel.clientHeight<80;
  refs["events-panel"].replaceChildren(); if (!run) return;
  for (const event of run.events) { const button=document.createElement("button");button.type="button";button.className=`event ${state.selectedEventSeq===event.seq?"active":""}`;button.textContent=`+${(event.elapsed_ms/1000).toFixed(2)}s · ${event.type} · ${eventSummary(event).slice(0,100)}`;button.addEventListener("click",()=>{state.selectedEventSeq=event.seq;state.tab="details";renderInspector();});refs["events-panel"].append(button); }
  panel.scrollTop=follow?panel.scrollHeight:oldScroll;
}
function renderChunks(run) {
  const panel=refs["chunks-panel"], signature=JSON.stringify([run?.runId,run?.chunksByQuery,run?.output?.citations]);
  if (panel.dataset.signature===signature) return;
  panel.dataset.signature=signature; const oldScroll=panel.scrollTop; panel.replaceChildren(); if (!run) return;
  if (!run.chunksByQuery.length) { panel.textContent="Nenhuma busca documental nesta execução."; return; }
  for (const group of run.chunksByQuery) {
    const heading=document.createElement("h3"); heading.textContent=`Busca ${group.index} · ${group.status} · ${group.hits.length} hits · top_k ${group.topK ?? "—"} · ${group.query}`; panel.append(heading);
    for (const hit of group.hits) {
      const card=document.createElement("article"); card.className="chunk"; card.id=`chunk-${run.runId}-${group.index}-${hit.chunk_id}`; card.dataset.chunkId=hit.chunk_id; card.tabIndex=-1;
      const h=document.createElement("h3"); h.textContent=`${hit.chunk_id} · ${hit.title || hit.section} · ${hit.section} · v${hit.version} · similaridade ${Number(hit.score).toFixed(3)}`;
      const p=document.createElement("p"); p.textContent=hit.text; card.append(h,p);
      const source=document.createElement("p"); source.textContent=hit.source_path || "";
      if (/^https?:\/\//.test(hit.source_url || "")) { const link=document.createElement("a"); link.href=hit.source_url; link.target="_blank"; link.rel="noopener noreferrer"; link.textContent=" Abrir fonte"; source.append(link); }
      card.append(source);
      const mark=document.createElement("span"); mark.className="badge"; mark.textContent=run.output?.citations?.some(item=>item.chunk_id===hit.chunk_id)?"Entregue ao modelo · Citado":"Entregue ao modelo"; card.append(mark); panel.append(card);
    }
    if (group.omitted) { const note=document.createElement("p"); note.textContent=`${group.omitted} chunks não foram entregues por orçamento.`; panel.append(note); }
  }
  panel.scrollTop=oldScroll;
}
function renderDetails(run) { refs["details-panel"].replaceChildren(); const event=run?.events.find(item=>item.seq===state.selectedEventSeq); if(!event){refs["details-panel"].textContent="Selecione um evento para abrir argumentos e resultado.";return;} const title=document.createElement("h3");title.textContent=`${event.type} · sequência ${event.seq}`;const pre=document.createElement("pre");pre.textContent=JSON.stringify(event.data,null,2);refs["details-panel"].append(title,pre); }
function selectChunk(runId, chunkId) { state.selectedRunId=runId; state.selectedChunkId=chunkId; state.tab="chunks";renderRuns();renderInspector();requestAnimationFrame(()=>{const card=Array.from(refs["chunks-panel"].querySelectorAll(".chunk")).find(item=>item.dataset.chunkId===chunkId);card?.scrollIntoView({block:"nearest"});card?.focus({preventScroll:true});}); }
function renderTabs() { for (const button of refs["inspector-tabs"].querySelectorAll("button")) { const active=button.dataset.tab===state.tab;button.setAttribute("aria-selected",String(active));document.getElementById(`${button.dataset.tab}-panel`).hidden=!active; } }

refs["chat-form"].addEventListener("submit",event=>{event.preventDefault();if(state.busy||!state.online||!state.meta?.key_configured)return;submitMessage(refs["message-input"].value);refs["message-input"].value="";});
refs["message-input"].addEventListener("keydown",event=>{if(event.key==="Enter"&&!event.shiftKey&&!event.isComposing){event.preventDefault();refs["chat-form"].requestSubmit();}});
refs["stage-select"].addEventListener("change",()=>{state.stage=refs["stage-select"].value;loadMeta(true);});
refs["exercise-select"].addEventListener("change",renderExercise);
refs["use-question"].addEventListener("click",()=>{const exercise=activeExercise();if(!exercise)return;document.getElementById("integration-mode").value=exercise.integration;state.stage=exercise.stage;refs["stage-select"].value=exercise.stage;document.getElementById("memory-mode").value=exercise.mode;refs["message-input"].value=exercise.question;refs["message-input"].focus();loadMeta(true);});
refs["refresh-meta"].addEventListener("click",()=>loadMeta());
refs["new-chat"].addEventListener("click",async()=>{await createConversation();state.conversation=[];state.lastRequest=null;renderChat();setNotice("Nova thread. A preferência confirmada pertence ao usuário e pode continuar ativa.");setBusy(false);});
refs["run-again"].addEventListener("click",()=>{if(state.lastRequest)submitMessage(state.lastRequest.question,state.lastRequest.historySnapshot);});
refs["run-select"].addEventListener("change",()=>{state.selectedRunId=refs["run-select"].value;state.selectedEventSeq=null;renderInspector();});
refs["inspector-tabs"].addEventListener("click",event=>{if(event.target.matches("button")){state.tab=event.target.dataset.tab;renderTabs();}});

let threadId = localStorage.getItem("aula05-thread");
let profileVersion = 0;
async function createConversation() {
  const response = await fetch("/api/threads", {method:"POST"});
  if (!response.ok) throw new Error("Não foi possível criar a conversa.");
  threadId = (await response.json()).thread_id;
  localStorage.setItem("aula05-thread", threadId);
  await inspectMemory();
}
async function inspectMemory() {
  try {
    const [threadResponse, profileResponse] = await Promise.all([
      fetch(`/api/threads/${encodeURIComponent(threadId)}`), fetch("/api/profile")]);
    if (!threadResponse.ok || !profileResponse.ok) throw new Error("Memória indisponível.");
    const [thread, profile] = await Promise.all([threadResponse.json(), profileResponse.json()]);
    profileVersion = profile.version;
    document.getElementById("thread-label").textContent = `Thread ${threadId.slice(0,8)} · ${thread.turns.length} turnos`;
    document.getElementById("memory-preview").textContent = JSON.stringify({thread, profile}, null, 2);
  } catch (error) { setNotice(error.message, "status-error"); }
}
async function changeProfile(remove=false) {
  try {
    const response = await fetch("/api/profile", {method:remove ? "DELETE" : "POST", headers:{"Content-Type":"application/json"},
      body:JSON.stringify({version:profileVersion, value:document.getElementById("profile-value").value, confirmed:document.getElementById("profile-confirm").checked})});
    const body = await response.json();
    if (!response.ok) throw new Error(body.error.message);
    document.getElementById("profile-confirm").checked = false;
    await inspectMemory();
    setNotice(remove ? "Preferência revogada para futuras seleções." : "Preferência confirmada salva. Use o bloco 2 ou 3 para recuperá-la.");
  } catch(error) { setNotice(error.message, "status-error"); await inspectMemory(); }
}
document.getElementById("inspect-memory").addEventListener("click",inspectMemory);
document.getElementById("save-profile").addEventListener("click",()=>changeProfile());
document.getElementById("revoke-profile").addEventListener("click",()=>changeProfile(true));
async function initialize() {
  refs["stage-select"].value=state.stage; renderTabs();
  try {
    if (threadId) {
      const response = await fetch(`/api/threads/${encodeURIComponent(threadId)}`);
      if (response.status === 404) await createConversation();
      else if (!response.ok) throw new Error("Falha ao recuperar a conversa.");
      else await inspectMemory();
    } else await createConversation();
    await loadMeta();
  } catch(error) { setNotice(error.message, "status-error"); }
}
initialize();

document.getElementById("diagnostic-tool").addEventListener("change", event => {
  const examples = {get_order:{order_id:"P100"}, get_delivery_status:{shipment_id:"E100"},
    get_resolution_options:{order_id:"P100"}, search_policies:{query:"atraso compensação",top_k:3}};
  document.getElementById("diagnostic-arguments").value = JSON.stringify(examples[event.target.value]);
});
for (const button of document.querySelectorAll("[data-diagnostic]")) {
  button.addEventListener("click", async () => {
    const status = document.getElementById("diagnostic-status"), output = document.getElementById("diagnostic-output");
    try {
      const arguments_ = button.dataset.diagnostic === "call" ? JSON.parse(document.getElementById("diagnostic-arguments").value) : {};
      document.querySelectorAll("[data-diagnostic]").forEach(item => item.disabled = true);
      status.textContent = "Consultando servidor local…"; output.textContent = "";
      const response = await fetch("/api/mcp/diagnostic", {method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({action:button.dataset.diagnostic, transport:document.getElementById("mcp-transport").value,
          name:document.getElementById("diagnostic-tool").value, arguments:arguments_})});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || "Diagnóstico indisponível.");
      output.textContent = JSON.stringify(data, null, 2);
      status.textContent = data.result.error ? `Falha observada: ${data.result.error} · ${data.result.error_origin}` :
        button.dataset.diagnostic === "compare" ? "A usa a fixture de referência; B devolve um dado falso deliberadamente. Compare catálogos e respostas." : "Consulta concluída. Inspecione resultado e eventos.";
    } catch (error) { status.textContent = error.message; }
    finally { document.querySelectorAll("[data-diagnostic]").forEach(item => item.disabled = false); }
  });
}
