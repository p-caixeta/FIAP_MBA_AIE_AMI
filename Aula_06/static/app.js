const $ = id => document.getElementById(id);
let current = null, meta = null;
const statusNames = {pending:"Aguardando revisão", approved:"Aprovada", executed:"Executada", rejected:"Rejeitada",
  needs_evidence:"Aguardando nova evidência", superseded:"Substituída", answered:"Resposta informativa", blocked:"Bloqueada"};
const titles = {analysis_completed:"1 · Análise das evidências", proposal_created:"2 · Proposta e rota",
  review_recorded:"3 · Decisão humana", action_executed:"4 · Efeito local"};
function element(tag, text) { const node = document.createElement(tag); if (text != null) node.textContent = text; return node; }
function syncApproval() {
  // Uma edição ainda não salva não pode parecer parte da versão aprovada.
  $("approve").disabled = Boolean(current && $("revision").value !== current.proposal.arguments.summary);
}
async function api(url, options) {
  const response = await fetch(url, options), data = await response.json();
  if (!response.ok) throw Error(data.error || "Falha na requisição.");
  return data;
}
async function busy(action) {
  document.querySelectorAll("button").forEach(b => b.disabled = true);
  $("notice").textContent = "Processando… A decisão humana só aparece depois da proposta.";
  try { await action(); $("notice").textContent = "Estado atualizado. Confira evidências, versão e efeito antes de decidir."; }
  catch (error) { $("notice").textContent = error.message; }
  finally { document.querySelectorAll("button").forEach(b => b.disabled = false); syncApproval(); }
}
function list(title, values, parent) {
  parent.append(element("h3", title));
  const ul = element("ul");
  (values.length ? values : ["Nenhum item registrado."]).forEach(v => ul.append(element("li", v)));
  parent.append(ul);
}
function previews(id, items) {
  $(id).replaceChildren();
  items.forEach(item => {
    const figure = element("figure"), media = element(item.kind === "video" ? "video" : "img");
    media.src = item.url; media.alt = "Evidência " + item.id;
    if (item.kind === "video") media.controls = true;
    const link = element("a", item.id + (item.timestamp != null ? " · " + item.timestamp + " s" : " · abrir"));
    link.href = item.url; link.target = "_blank"; link.rel = "noopener";
    const caption = element("figcaption"); caption.append(link); figure.append(media, caption); $(id).append(figure);
  });
}
async function refreshCases() {
  const rows = await api("/api/cases");
  $("cases").replaceChildren(new Option("Escolha…", ""));
  rows.forEach(p => $("cases").add(new Option(p.thread.slice(0,8) + " · v" + p.version + " · " + statusNames[p.status], p.thread)));
  if (current) $("cases").value = current.thread;
}
function render(state) {
  current = state; const p = state.proposal;
  $("case-view").hidden = false;
  $("case-title").textContent = "P600 · caso " + state.thread.slice(0,8) + " · " + (state.mode === "live" ? "LMM real" : "ANÁLISE FORNECIDA");
  previews("originals", state.originals); previews("evidence", state.evidence);
  const a = $("analysis"); a.replaceChildren(element("p", state.analysis.summary));
  list("Observações", state.analysis.observations.map(o => o.claim + " [" + o.evidence_ids.join(", ") + "]"), a);
  list("Não sabemos", state.analysis.unknowns, a); list("Conflitos", state.analysis.conflicts, a);
  const dl = element("dl");
  Object.entries({"Versão":p.version,"Estado":statusNames[p.status],"Ação":p.tool,"Pedido":p.arguments.order_id,
    "Resumo":p.arguments.summary,"Motivo":p.rationale,"Política":p.policy_version,
    "Evidências":p.evidence_ids.join(", "),"Lacunas":p.unknowns.join(" · ")}).forEach(([k,v]) => dl.append(element("dt",k),element("dd",String(v))));
  $("proposal").replaceChildren(dl);
  $("revision").value = p.arguments.summary;
  syncApproval();
  $("decision-controls").hidden = p.status !== "pending";
  $("continue-label").hidden = !["pending","needs_evidence"].includes(p.status);
  $("continue").checked = p.status === "needs_evidence";
  $("outcome").textContent = state.receipt?.ticket_id ? "Chamado " + state.receipt.ticket_id + " · efeito local registrado uma vez." : statusNames[p.status] + " · nenhum ticket criado.";
  $("steps").replaceChildren();
  state.events.forEach(item => {
    const detail = element("details"); detail.open = true;
    detail.append(element("summary", titles[item.step] || item.step), element("pre",JSON.stringify(item.detail,null,2)));
    $("steps").append(detail);
  });
  if(p.status === "pending") $("steps").append(element("p","Pausa real: nenhum chamado foi criado. A execução pode ser retomada após reiniciar o app."));
  const metrics = state.metrics.analysis;
  $("metrics").textContent = metrics.model ? metrics.model + " · " + metrics.seconds + " s · tokens: " + (metrics.usage?.total_tokens ?? "não informado") : "Análise fornecida · sem chamada ao LMM · consumo não aplicável";
}
async function sendDecision(action) {
  const decision = {proposal_id:current.proposal.proposal_id,version:current.proposal.version,action};
  if (action === "revise") decision.summary = $("revision").value;
  await busy(async () => {
    render(await api("/api/cases/"+current.thread+"/decision",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(decision)}));
    await refreshCases();
  });
}
$("input-form").addEventListener("submit", event => {
  event.preventDefault();
  busy(async () => {
    const form = new FormData();
    ["mode","fixture","frames","message"].forEach(id => form.set(id,$(id).value));
    form.set("kit",JSON.stringify([...document.querySelectorAll("#kit input:checked")].map(i=>i.value)));
    [...$("files").files].forEach(file => form.append("files",file));
    if(current && $("continue").checked && !$("continue-label").hidden) form.set("thread",current.thread);
    render(await api("/api/analyze",{method:"POST",body:form})); await refreshCases();
  });
});
for(const action of ["approve","reject","revise"]) $(action).onclick = () => sendDecision(action);
$("request-evidence").onclick = () => sendDecision("request_evidence");
$("revision").oninput = syncApproval;
$("load").onclick = () => busy(async () => { if(!$("cases").value) throw Error("Escolha um caso."); render(await api("/api/cases/"+$("cases").value)); });
$("new").onclick = () => { current=null; $("case-view").hidden=true; $("continue-label").hidden=true; $("continue").checked=false; $("steps").replaceChildren(); $("notice").textContent="Novo caso: a próxima análise inicia outra execução."; };
$("mode").onchange = () => $("fixture-label").hidden = $("mode").value === "live";
$("exercise").onchange = () => {
  const item = meta.exercises.find(e=>e.id === $("exercise").value);
  $("exercise-detail").textContent = item.function + " · " + item.task;
};
(async () => {
  try {
    meta = await api("/api/meta"); $("model").textContent = "Modelo configurado: " + meta.model;
    $("message").value=meta.case.message;
    meta.exercises.forEach(e=>$("exercise").add(new Option(e.id+" · "+e.title,e.id))); $("exercise").onchange();
    meta.kit.forEach((item,index) => {
      const label=element("label"), input=element("input"), preview=element(item.file.endsWith(".mp4")?"video":"img");
      input.type="checkbox"; input.value=item.file; input.checked=index===0;
      preview.src="/media/kit/"+item.file; preview.alt="Item "+item.file; if(preview.tagName==="VIDEO"){preview.muted=true;preview.preload="metadata";}
      label.append(preview,input,element("span",item.file)); $("kit").append(label);
    });
    list("Política "+meta.policy.version,meta.policy.rules,$("policy")); await refreshCases();
  } catch(error) { $("notice").textContent=error.message; }
})();
