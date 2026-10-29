"use strict";
const $ = id => document.getElementById(id);
const kinds = {DOCUMENT:"문서", DECISION:"결정", PREFERENCE:"선호", FACT:"사실", PROCEDURE:"절차", EPISODE:"경험"};
const pageSize = 10;
let originalSummary="", activeIndex=null, catalogOffset=0, referenceOffset=0, originalUri=null, originalFilename="source.txt";
let sessionMode = true, csrf = "";
let token = "", offset = 0, listMode = true, generation = 0, controller;
let selected = null, original = "", editing = false, saving = false, pending = null;
let searchGraph=null;
let graphGeneration=0, graphController, graphSource=null;
let contentGeneration = 0, contentController, jobTimer, categoryValue = "", relationOnly = false;
function status(message, error = false) { $("status").textContent = message; $("status").classList.toggle("error", error); }
function noteStatus(message, error = false) { $("note-status").textContent = message; $("note-status").classList.toggle("error", error); }
function dirty() { return editing && ($("reader-body").value !== original || $("reader-summary").value !== originalSummary); }
function mayLeave() { return !saving && (!dirty() || window.confirm("저장하지 않은 수정 내용을 버릴까요?")); }
function editMode(value) { editing=value; $("reader-body").readOnly=!value; $("reader-summary").readOnly=!value; $("edit").hidden=value; $("save").hidden=!value; $("cancel").hidden=!value; }
function clearReader() {
 graphGeneration++; graphController?.abort(); graphSource=null;
 showNoteView("summary"); $("reader-summary").value=""; originalSummary=""; originalUri=null; referenceOffset=0; $("reference-indexes").replaceChildren(); $("reference-sources").textContent=""; $("download-original").disabled=true; $("references-more").hidden=true; $("show-workflow").disabled=true; $("flow-count").textContent=""; $("workflow-canvas").replaceChildren(); $("workflow-relations").replaceChildren(); $("workflow-evidence").hidden=true;
 contentGeneration++; contentController?.abort(); clearTimeout(jobTimer); selected=null; pending=null; original=""; editMode(false);
 $("reader-title").textContent="노트를 선택하세요"; $("reader-body").value=""; updateLines(); $("reader-meta").textContent=""; $("edit-origin").hidden=true; $("edit").disabled=true; $("check-job").hidden=true; noteStatus("");
}
function disconnect() {
 proposalGeneration++; $("graph-proposals").replaceChildren(); $("graph-review-status").textContent=""; $("graph-proposals-more").hidden=true;
 searchGraph=null; $("search-result-graph").hidden=true;
 generation++; controller?.abort(); clearReader(); activeIndex=null; $("index-catalog").replaceChildren(); $("index-more").hidden=true; token=""; csrf=""; $("token").value=""; $("connect-form").hidden=false; $("connected").hidden=true; $("connection").textContent="연결 전"; $("results").replaceChildren(); $("category").replaceChildren(new Option("전체 카테고리","")); categoryValue=""; relationOnly=false; $("has-relations").checked=false; $("count").textContent=""; $("pagination").hidden=true; status("API 토큰으로 연결하면 노트를 볼 수 있습니다.");
}
function authHeaders() { return sessionMode ? {"X-CSRF-TOKEN":csrf} : {Authorization:"Bearer "+token}; }
async function request(path, options={}) {
 const response=await fetch(path,{...options,cache:"no-store",credentials:"same-origin",headers:{...authHeaders(),"Content-Type":"application/json"}});
 if(!response.ok) {
  if(response.status===401 || response.status===403) throw new Error("AUTH");
  throw new Error(response.status===409 ? "다른 수정이 먼저 저장되었습니다. 초안을 복사한 뒤 노트를 다시 열어 주세요." : response.status===400 || response.status===422 ? "입력 내용과 검색 조건을 확인해 주세요." : "요청을 처리하지 못했습니다. 잠시 후 다시 확인해 주세요.");
 }
 return response.json();
}
function handleError(error) { if(error.name==="AbortError") return; if(error.message==="AUTH") { if(!dirty()) disconnect(); status("인증할 수 없습니다. 작성 중인 내용은 복사한 뒤 다시 연결해 주세요.",true); } else status(error instanceof TypeError ? "API에 연결할 수 없습니다." : error.message,true); }
function element(tag,text) { const node=document.createElement(tag); node.textContent=text; return node; }
async function categories() {
 const version=generation;
 try { const data=await request("/api/v1/knowledge/categories"); if(version!==generation) return; $("category").replaceChildren(new Option("전체 카테고리",""),...data.categories.filter(Boolean).map(x=>new Option(x,x))); $("category").value=categoryValue; } catch(error) { if(version===generation) handleError(error); }
}
async function read(item) {
 if(!mayLeave()) return;
 clearReader(); selected=item; const version=contentGeneration, graphVersion=graphGeneration; contentController=new AbortController();
 for(const row of $("results").children) row.setAttribute("aria-current",String(row.dataset.id===item.knowledge_id));
 $("reader-title").textContent=item.title; noteStatus("원문을 불러오는 중…");
 try {
  const data=await request(`/api/v1/knowledge/${item.knowledge_id}/revisions/${item.revision_id}/content`,{signal:contentController.signal});
  if(version!==contentGeneration) return;
  original=data.text; originalSummary=data.summary || ""; $("reader-summary").value=originalSummary; $("summary-kind").textContent=data.summary_kind==="EXTRACTIVE"?"원문 발췌 요약 · 전체 내용은 상세에서 확인":"작성된 요약 · "+data.summary_kind; $("reader-body").value=original; updateLines(); $("edit").disabled=false;
  $("edit-origin").hidden=data.edit_origin!=="HUMAN"; $("edit-origin").textContent="사용자 편집";
  const sources=(data.sources || []).map(s=>`${s.kind}: ${s.location}${s.machine_id ? " · 머신 "+s.machine_id : ""}${s.version ? " · 버전 "+s.version : ""}${s.locator ? " · "+s.locator : ""}`);
  $("reader-meta").textContent=`지식 ${item.knowledge_id}\n버전 ${item.revision_id}\n범위 ${item.scope || ""}\n편집 경로 ${data.edit_origin || "UNKNOWN"}\n작성 머신 ${data.origin_machine_label || data.origin_machine_id || "기록 없음"}\n${sources.join("\n") || "출처 위치: 기록 없음"}`;
  noteStatus(""); if(graphVersion===graphGeneration)loadWorkflow(item,version);
 } catch(error) { if(version===contentGeneration) { noteStatus("원문을 불러오지 못했습니다.",true); handleError(error); } }
}
function render(items) {
 $("results").replaceChildren();
 for(const item of items) {
  const row=element("button",""); row.className="note-row"; row.dataset.id=item.knowledge_id; row.disabled=!item.revision_id;
  row.append(element("strong",item.title),element("small",[kinds[item.memory_kind],item.category,item.revision_id?"":"색인 중"].filter(Boolean).join(" · ")));
  row.addEventListener("click",()=>read(item)); $("results").append(row);
 }
}
async function load() {
 if(!token) { status("먼저 API 토큰으로 연결해 주세요.",true); return; }
 controller?.abort(); controller=new AbortController(); const version=++generation; clearReader();
 searchGraph=null; $("search-result-graph").hidden=true;
 $("results").replaceChildren(); $("pagination").hidden=true; status("불러오는 중…");
 const scope=$("scope").value.trim(), kind=$("kind").value, category=$("category").value;
 try {
  let data;
  if(activeIndex) { const params=new URLSearchParams({offset:String(offset),limit:String(pageSize+1)}); if(scope)params.set("scope",scope); const path=activeIndex.id==="unfiled"?"/api/v1/indexes/unfiled":`/api/v1/indexes/${activeIndex.id}/entries`; data=await request(path+"?"+params,{signal:controller.signal}); }
  else if(listMode) { const params=new URLSearchParams({offset:String(offset),limit:String(pageSize+1)}); if(scope) params.set("scope",scope); if(kind) params.set("memory_kind",kind); if(category) params.set("category",category); if(relationOnly) params.set("has_relations","true"); data=await request("/api/v1/knowledge?"+params,{signal:controller.signal}); }
  else { const payload={query:$("query").value.trim(),top_k:20,include_graph:true}; if(scope) payload.scopes=[scope]; if(kind) payload.memory_kinds=[kind]; if(category) payload.category=category; if(relationOnly)payload.has_relations=true; data=await request("/api/v1/knowledge/search",{method:"POST",body:JSON.stringify(payload),signal:controller.signal}); }
  if(version!==generation) return;
  searchGraph=data.graph || null; $("search-result-graph").hidden=!searchGraph;
  $("search-result-graph").textContent=searchGraph?.status==="READY"?`검색 관계 ${searchGraph.edges.length}개 · 근거 보기`:"관계 조회 불가";
  const items=listMode?data.items.slice(0,pageSize):data.items.slice(offset,offset+pageSize);
  render(items); $("connection").textContent="연결됨"; $("connect-form").hidden=true; $("connected").hidden=false;
  $("results-title").textContent=activeIndex?activeIndex.title:(listMode?"노트":"검색 결과"); $("count").textContent=listMode?`${items.length}개`:`${data.items.length}개 · 최대 20개`;
  status(items.length?"":"해당하는 노트가 없습니다."); $("pagination").hidden=false; $("previous").disabled=offset===0;
  $("next").disabled=listMode?data.items.length<=pageSize:offset+pageSize>=data.items.length; $("page-number").textContent=`${offset/pageSize+1} 페이지`;
  if(items[0]?.revision_id) await read(items[0]);
 } catch(error) { if(version===generation) handleError(error); }
}
async function checkJob(attempt=0) {
 if(!pending) return;
 const version=contentGeneration, job=pending;
 try {
  const result=await request("/api/v1/jobs/"+job.job_id);
  if(version!==contentGeneration) return;
  if(result.status==="READY") { const item={...selected,revision_id:job.revision_id}; pending=null; await read(item); noteStatus("저장 및 색인 완료 · 사용자 편집"); return; }
  if(result.status==="FAILED") { noteStatus("수정본은 저장됐지만 색인에 실패했습니다. 초안을 보존하고 작업 이력을 확인해 주세요.",true); $("check-job").hidden=false; return; }
  noteStatus("수정본 저장됨 · 검색 색인 처리 중…");
  if(attempt<30) jobTimer=setTimeout(()=>checkJob(attempt+1),2000); else $("check-job").hidden=false;
 } catch { if(version===contentGeneration) { noteStatus("저장은 접수되었습니다. 색인 상태를 다시 확인해 주세요.",true); $("check-job").hidden=false; } }
}
async function save() {
 if(!selected || saving || !dirty()) return;
 if(!$("reader-body").value.trim() || $("reader-body").value.length>200000) { noteStatus("원문은 1~200,000자로 입력해 주세요.",true); return; }
 saving=true; $("save").disabled=true; $("cancel").disabled=true; noteStatus("저장 중…");
 try {
  const history=await request(`/api/v1/knowledge/${selected.knowledge_id}/history`), latest=history.revisions.at(-1);
  if(latest?.revision_id!==selected.revision_id || latest.status!=="READY") throw new Error("새 수정본이 이미 있습니다. 초안을 복사한 뒤 노트를 다시 열고 이력을 확인해 주세요.");
  pending=await request(`/api/v1/knowledge/${selected.knowledge_id}/revisions`,{method:"POST",body:JSON.stringify({expected_revision_id:selected.revision_id,text:$("reader-body").value,summary:$("reader-summary").value!==originalSummary?$("reader-summary").value:null,change_note:"웹 화면 사용자 편집",edit_origin:"HUMAN"})});
  original=$("reader-body").value; originalSummary=$("reader-summary").value; editMode(false); $("edit").disabled=true;
 } catch(error) { noteStatus(error instanceof TypeError ? "저장 결과를 확인할 수 없습니다. 초안을 보존하고 최신 이력을 확인한 뒤 다시 시도해 주세요." : error.message,true); }
 finally { saving=false; $("save").disabled=false; $("cancel").disabled=false; }
 if(pending) checkJob();
}
$("connect-form").addEventListener("submit",async event=>{
 event.preventDefault(); if(!mayLeave()) return; generation++;
 let key=$("token").value.trim(); $("token").value="";
 try {
  if(sessionMode) {
   const response=await fetch("/knowledge/session",{method:"POST",credentials:"same-origin",cache:"no-store",headers:{"Content-Type":"application/json","X-Knowledge-UI":"1"},body:JSON.stringify({api_key:key})});
   key="";
   if(!response.ok) throw new Error(response.status===429?"로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.":"노트 전용 API 키를 확인해 주세요.");
   const data=await response.json(); csrf=data.csrf; token="session";
  } else { token=key; key=""; }
  offset=0; listMode=true; await categories(); await load();
 } catch(error) { key=""; status(error.message,true); }
});
$("search-form").addEventListener("submit",event=>{event.preventDefault(); if(!mayLeave()) return; activeIndex=null; offset=0; listMode=!$("query").value.trim(); load();});
$("browse").addEventListener("click",()=>{if(!mayLeave()) return; activeIndex=null; offset=0; listMode=true; load();});
$("category").addEventListener("change",()=>{if(!mayLeave()) { $("category").value=categoryValue; return; } activeIndex=null; categoryValue=$("category").value; offset=0; load();});
$("has-relations").addEventListener("change",()=>{if(!mayLeave()){ $("has-relations").checked=relationOnly;return;}relationOnly=$("has-relations").checked;activeIndex=null;offset=0;load();});
$("previous").addEventListener("click",()=>{if(!mayLeave()) return; offset=Math.max(0,offset-pageSize);load();});
$("next").addEventListener("click",()=>{if(!mayLeave()) return; offset+=pageSize;load();});
$("disconnect").addEventListener("click",async()=>{
 if(!mayLeave())return;
 try {
  if(sessionMode) { const response=await fetch("/knowledge/session",{method:"DELETE",credentials:"same-origin",headers:authHeaders()}); if(!response.ok && response.status!==401) throw new Error("로그아웃하지 못했습니다. 다시 시도해 주세요."); }
  disconnect();
 } catch(error) { status(error.message,true); }
});
$("edit").addEventListener("click",()=>{showNoteView("source");editMode(true);noteStatus("원문을 수정한 뒤 저장하세요. 이전 버전은 보존됩니다.");$("reader-body").focus();});
$("cancel").addEventListener("click",()=>{if(!mayLeave()) return; $("reader-body").value=original; $("reader-summary").value=originalSummary; updateLines(); editMode(false);noteStatus("");});
$("save").addEventListener("click",save);
$("check-job").addEventListener("click",()=>checkJob());
window.addEventListener("beforeunload",event=>{if(dirty() || saving) { event.preventDefault(); event.returnValue=""; }});
window.addEventListener("pagehide",()=>{token="";clearTimeout(jobTimer);controller?.abort();contentController?.abort();});
async function autoConnect() {
 const version=generation;
 try {
  const response=await fetch("/knowledge/session",{credentials:"same-origin",cache:"no-store"});
  if(version!==generation)return;
  if(response.status!==404) {
   sessionMode=true;
   if(response.ok) { const data=await response.json(); csrf=data.csrf; token="session"; await categories(); await load(); }
   else status("노트 전용 API 키를 입력해 주세요. 로그인은 7일간 유지됩니다.");
   return;
  }
  sessionMode=false;
 } catch { status("서버에 연결할 수 없습니다.",true); return; }
 try { const response=await fetch("/knowledge/local-connection",{method:"POST",headers:{"X-Knowledge-UI":"1"},credentials:"omit",cache:"no-store"}); if(!response.ok || version!==generation || token) { status("API 토큰으로 연결해 주세요."); return; } const data=await response.json(); if(version!==generation || !data.token || token) return; token=data.token; await categories(); await load(); } catch { status("API 토큰으로 연결해 주세요."); }
}
autoConnect();

function updateLines() {
 const area=$("reader-body"), gutter=$("line-numbers"), lines=area.value.split("\n");
 $("line-count").textContent=`${lines.length}줄`;
 if(!area.clientWidth) return;
 const style=getComputedStyle(area), height=parseFloat(style.lineHeight);
 const mirror=document.createElement("div");
 Object.assign(mirror.style,{position:"absolute",visibility:"hidden",pointerEvents:"none",left:"-100000px",top:"0",width:Math.max(1,area.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight))+"px",font:style.font,letterSpacing:style.letterSpacing,tabSize:style.tabSize,whiteSpace:$("wrap-lines").checked?"pre-wrap":"pre",overflowWrap:"anywhere"});
 const blocks=lines.map(line=>{const block=document.createElement("div");block.textContent=line || "\u200b";mirror.append(block);return block;});
 document.body.append(mirror);
 const fragment=document.createDocumentFragment();
 blocks.forEach((block,index)=>{const number=document.createElement("span");number.textContent=String(index+1);number.style.height=Math.max(height,block.getBoundingClientRect().height)+"px";fragment.append(number);});
 mirror.remove();gutter.replaceChildren(fragment);gutter.scrollTop=area.scrollTop;
}
$("reader-body").addEventListener("input",updateLines);
$("reader-body").addEventListener("scroll",()=>{$("line-numbers").scrollTop=$("reader-body").scrollTop;});
$("wrap-lines").addEventListener("change",()=>{const wrap=$("wrap-lines").checked;$("reader-body").wrap=wrap?"soft":"off";$("reader-body").parentElement.classList.toggle("wrapped",wrap);updateLines();});
$("indent-size").addEventListener("change",()=>{$("reader-body").style.tabSize=$("indent-size").value;updateLines();});
$("reader-body").addEventListener("keydown",event=>{
 const area=event.currentTarget;
 if(area.readOnly || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
 const start=area.selectionStart,end=area.selectionEnd,size=Number($("indent-size").value),space=" ".repeat(size),value=area.value;
 if(event.key==="Tab") {
  event.preventDefault();
  if(start===end && !event.shiftKey) area.setRangeText(space,start,end,"end");
  else {
   const from=value.lastIndexOf("\n",start-1)+1;
   const until=end>start && value[end-1]==="\n"?end-1:end;
   const lines=value.slice(from,until).split("\n");
   const replacement=lines.map(line=>event.shiftKey?line.replace(new RegExp("^( {1,"+size+"}|\t)"),""):space+line).join("\n");
   area.setRangeText(replacement,from,until,"select");
  }
  updateLines();
 } else if(event.key==="Enter") {
  const from=value.lastIndexOf("\n",start-1)+1,indent=value.slice(from,start).match(/^[ \t]*/)[0];
  if(indent) {event.preventDefault();area.setRangeText("\n"+indent,start,end,"end");updateLines();}
 }
});

new ResizeObserver(updateLines).observe($("reader-body"));

function showNoteView(view) {
 for(const name of ["summary","source","references","workflow"]) { $(name+"-view").hidden=view!==name; $("show-"+name).setAttribute("aria-pressed",String(view===name)); }
 if(view==="source") updateLines();
}
$("show-summary").addEventListener("click",()=>showNoteView("summary"));
$("show-references").addEventListener("click",()=>{showNoteView("references");referenceOffset=0;loadReferences();});
async function loadReferences() {
 if(!selected)return;const version=contentGeneration,item=selected;
 $("reference-status").textContent="참조 위치를 확인하는 중…";
 try {
  const data=await request(`/api/v1/knowledge/${item.knowledge_id}/references?revision_id=${item.revision_id}&offset=${referenceOffset}&limit=10`,{signal:contentController.signal});if(version!==contentGeneration)return;
  $("reference-indexes").replaceChildren();for(const link of data.indexes){const b=element("button",link.index.title+" · "+link.section);b.addEventListener("click",()=>selectIndex(link.index));$("reference-indexes").append(b);}
  $("reference-status").textContent=`프로젝트 범위: ${data.scope} · 참조 ${data.rdf.storage==="oracle_rdf"?"Oracle RDF":data.rdf.status==="NOT_INDEXED"?"기존 자료 · RDF 참조 미색인":"메타데이터"}`;
  $("references-more").hidden=data.next_offset===null;$("references-more").dataset.offset=data.next_offset;
  $("reference-sources").textContent=[`지식 ${data.knowledge_id}`,`버전 ${data.revision_id}`,`상세: ${data.detail_uri}`,data.filename?`원본 파일: ${data.filename}`:"",data.source_url?`원본 URL: ${data.source_url}`:"",...data.sources.map(s=>`${s.kind}: ${s.location}${s.machine_id?" · 머신 "+s.machine_id:""}${s.version?" · 버전 "+s.version:""}${s.locator?" · 위치 "+s.locator:""}`)].filter(Boolean).join("\n");
  originalUri=data.original_uri;originalFilename=data.filename || "source.txt";$("download-original").disabled=!originalUri;
 } catch(error){if(version===contentGeneration)handleError(error);}
}
$("references-more").addEventListener("click",()=>{referenceOffset=Number($("references-more").dataset.offset);loadReferences();});
$("download-original").addEventListener("click",async()=>{
 if(!originalUri)return;const version=contentGeneration;
 try{const response=await fetch(originalUri,{headers:authHeaders(),credentials:"same-origin",cache:"no-store"});if(!response.ok)throw new Error("원본을 내려받을 수 없습니다.");const blob=await response.blob();if(version!==contentGeneration)return;const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=originalFilename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){handleError(error);}
});
function selectIndex(index) {if(!mayLeave())return;relationOnly=false;$("has-relations").checked=false;activeIndex=index;listMode=true;offset=0;load();}
async function loadCatalog() {
 if(!token)return;const version=generation,params=new URLSearchParams({offset:String(catalogOffset),limit:"10"});if($("scope").value.trim())params.set("scope",$("scope").value.trim());
 try {const data=await request("/api/v1/indexes?"+params);if(version!==generation)return;$("index-catalog").replaceChildren();for(const index of data.items){const b=element("button",index.title);b.title=index.summary;b.addEventListener("click",()=>selectIndex(index));$("index-catalog").append(b);}if(!data.items.length)$("index-catalog").append(element("p","등록된 인덱스가 없습니다."));$("index-more").hidden=data.next_offset===null;$("index-more").dataset.offset=data.next_offset;}catch(error){handleError(error);}
}
$("index-load").addEventListener("click",()=>{catalogOffset=0;loadCatalog();});
$("index-more").addEventListener("click",()=>{catalogOffset=Number($("index-more").dataset.offset);loadCatalog();});
$("unfiled").addEventListener("click",()=>selectIndex({id:"unfiled",title:"미분류 지식"}));
$("show-source").addEventListener("click",()=>showNoteView("source"));
$("show-workflow").addEventListener("click",()=>showNoteView("workflow"));
$("search-graph").addEventListener("click",()=>{
 if(!token) { status("먼저 저장소에 연결해 주세요.",true); return; }
 graphSource=null; resetGraphFilters(null); $("show-workflow").disabled=false; showNoteView("workflow"); loadSharedGraph();
});
$("graph-form").addEventListener("submit",event=>{event.preventDefault();loadSharedGraph();});
function localDateTime(now) {
 const pad=n=>String(n).padStart(2,"0");
 return `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
function setGraphTimeMode() {
 const current=$("graph-time-mode").value==="current";
 $("valid-at").disabled=current;$("known-at").disabled=current;
}
function resetGraphFilters(item) {
 $("graph-time-mode").value="current";
 const current=localDateTime(new Date());$("valid-at").value=current;$("known-at").value=current;
 $("graph-scopes").value=item?.scope || $("scope").value.trim();
 $("include-undated").checked=true;$("graph-options").open=false;setGraphTimeMode();
}
$("graph-time-mode").addEventListener("change",setGraphTimeMode);
$("graph-reset").addEventListener("click",()=>{resetGraphFilters(graphSource);loadSharedGraph();});
function graphFilters() {
 const scopes=$("graph-scopes").value.trim().split(",").map(s=>s.trim()).filter(Boolean);
 const current=$("graph-time-mode").value==="current";
 return {scopes:scopes.length?scopes:null,
  valid_at:current?null:new Date($("valid-at").value).toISOString(),
  known_at:current?null:new Date($("known-at").value).toISOString(),
  include_undated:$("include-undated").checked,depth:1,max_edges:60};
}
async function loadSharedGraph() {
 graphController?.abort(); graphController=new AbortController();const version=++graphGeneration;
 const payload={...graphFilters(),...(graphSource?{knowledge_id:graphSource.knowledge_id}:{query:$("query").value.trim()})};
 $("workflow-canvas").replaceChildren();$("workflow-relations").replaceChildren();$("workflow-evidence").hidden=true;
 $("workflow-status").textContent="관계를 불러오는 중…";
 $("graph-context").textContent=graphSource?`이 노트의 근거에서 연결: ${graphSource.title}`:`관련 지식: ${payload.query || "전체"}`;
 try {
  let flow=await request("/api/v1/graph/search",{method:"POST",body:JSON.stringify(payload),signal:graphController.signal});
  if(version!==graphGeneration)return;
  let legacy=false;
  if(!flow.edges.length && graphSource && !payload.valid_at && !payload.known_at) {
   const old=await request(`/api/v1/knowledge/${graphSource.knowledge_id}/revisions/${graphSource.revision_id}/workflow`,{signal:graphController.signal});
   if(version!==graphGeneration)return;
   if(old.status==="READY") { flow=old;legacy=true; }
  }
  $("show-workflow").disabled=false;$("flow-count").textContent=`(${flow.edges.length})`;
  const basis=legacy?"이전 형식 · 이 원문 버전만 표시":`업무 ${payload.valid_at ? new Date(payload.valid_at).toLocaleString() : "현재"} · 기록 ${payload.known_at ? new Date(payload.known_at).toLocaleString() : "현재"} · 범위 ${payload.scopes?.join(", ") || "내 전체 지식"}${flow.include_undated?" · 시점 미상 포함":""}`;
  $("workflow-status").textContent=`${flow.nodes.length}개 항목 · ${flow.edges.length}개 관계${flow.truncated?" · 일부만 표시, 검색어/범위를 좁혀 주세요":""} · ${basis}`;
  if(flow.edges.length)renderWorkflow(flow);
 } catch(error) { if(version===graphGeneration && error.name!=="AbortError") { $("workflow-status").textContent="관계를 불러오지 못했습니다. 연결과 검색 조건을 확인해 주세요.";handleError(error); } }
}
async function loadWorkflow(item,version) {
 if(version!==contentGeneration)return;
 graphSource=item; resetGraphFilters(item); await loadSharedGraph();
}
function renderWorkflow(flow) {
 if(!flow.nodes.length){$("workflow-canvas").replaceChildren(element("p","현재 조건에서 확인된 관계가 없습니다."));return;}
 const ns="http://www.w3.org/2000/svg";
 const svgNode=(tag,attrs={},text)=>{const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n;};
 const relationNames={next:"다음 단계",depends_on:"선행 의존",assigned_to:"담당",requires:"필요 조건",produces:"산출",uses:"사용",shares_database:"DB 공유",integrates_with:"연동",part_of:"소속"};
 const nodes=new Map(flow.nodes.map(n=>[n.id,n])), indegree=new Map(flow.nodes.map(n=>[n.id,0])), layers=new Map(flow.nodes.map(n=>[n.id,0]));
 for(const edge of flow.edges) if(indegree.has(edge.target))indegree.set(edge.target,indegree.get(edge.target)+1);
 const queue=flow.nodes.filter(n=>indegree.get(n.id)===0).map(n=>n.id),visited=new Set();
 while(queue.length) {
  const id=queue.shift();visited.add(id);
  for(const edge of flow.edges.filter(e=>e.source===id)) {
   layers.set(edge.target,Math.max(layers.get(edge.target),layers.get(id)+1));indegree.set(edge.target,indegree.get(edge.target)-1);
   if(indegree.get(edge.target)===0) queue.push(edge.target);
  }
 }
 let cycleLayer=Math.max(0,...layers.values())+1;
 for(const n of flow.nodes) if(!visited.has(n.id))layers.set(n.id,cycleLayer++);
 const groups=new Map();for(const n of flow.nodes){const level=layers.get(n.id);if(!groups.has(level))groups.set(level,[]);groups.get(level).push(n);}
 const width=Math.max(280,...Array.from(groups.values(),g=>g.length*240+40)), height=(Math.max(...layers.values())+1)*110+40;
 const positions=new Map();for(const [level,group] of groups)group.forEach((n,i)=>positions.set(n.id,{x:width/2+(i-(group.length-1)/2)*240,y:25+level*110}));
 const svg=svgNode("svg",{width,height,viewBox:`0 0 ${width} ${height}`,role:"img","aria-label":"지식 관계도"});
 svg.append(svgNode("title",{},"저장된 업무 관계. 화살표의 관계명과 아래 근거 문장을 함께 확인하세요."));
 const defs=svgNode("defs"),marker=svgNode("marker",{id:"flow-arrow",viewBox:"0 0 10 10",refX:9,refY:5,markerWidth:6,markerHeight:6,orient:"auto-start-reverse"});marker.append(svgNode("path",{d:"M 0 0 L 10 5 L 0 10 z",class:"flow-arrow"}));defs.append(marker);svg.append(defs);
 for(const edge of flow.edges) {
  const a=positions.get(edge.source),b=positions.get(edge.target);if(!a || !b)continue;
  const down=b.y>a.y, start=a.y+(down?64:0),end=b.y+(down?0:64),bend=(start+end)/2;
  let d=`M ${a.x} ${start} C ${a.x} ${bend}, ${b.x} ${bend}, ${b.x} ${end}`;
  if(a===b || edge.source===edge.target)d=`M ${a.x+100} ${a.y+20} C ${a.x+160} ${a.y-20},${a.x+160} ${a.y+90},${a.x+100} ${a.y+44}`;
  svg.append(svgNode("path",{d,class:"flow-path","marker-end":"url(#flow-arrow)"}));
  const label=(relationNames[edge.relation] || edge.relation)+(edge.condition?" · "+edge.condition:"");
  const text=svgNode("text",{x:(a.x+b.x)/2,y:bend-5,class:"flow-label","text-anchor":"middle"},label.length>20?label.slice(0,20)+"…":label);text.append(svgNode("title",{},label));svg.append(text);
  const button=element("button",`${nodes.get(edge.source).label} → ${nodes.get(edge.target).label} · ${label}`);button.setAttribute("aria-pressed","false");
  button.addEventListener("click",()=>{for(const b of $("workflow-relations").children)b.setAttribute("aria-pressed","false");button.setAttribute("aria-pressed","true");$("workflow-evidence").hidden=false;const evidence=Array.isArray(edge.evidence)?edge.evidence.map(e=>`${e.title}\n지식 ${e.knowledge_id} · 버전 ${e.revision_id}\n${e.quote}`).join("\n\n"):edge.evidence;
   const period=edge.temporal_kind==="INTERVAL"?`${edge.valid_from} ≤ 시점 < ${edge.valid_to || "종료 없음"}`:edge.temporal_kind==="TIMELESS"?"시간 제한 없음 (근거 확인됨)":"시점 미상";
   $("workflow-evidence").textContent=`${label}\n적용: ${period}${edge.recorded_from?"\n기록: "+edge.recorded_from+" ~ "+(edge.recorded_to || "현재"):""}\n\n${evidence}`;});$("workflow-relations").append(button);
 }
 for(const n of flow.nodes) {
  const pos=positions.get(n.id),group=svgNode("g");group.append(svgNode("rect",{x:pos.x-100,y:pos.y,width:200,height:64,rx:5,class:"flow-node"}));group.append(svgNode("title",{},n.label));
  const chunks=n.label.match(/.{1,16}/gu) || [n.label],text=svgNode("text",{x:pos.x,y:pos.y+27,"text-anchor":"middle"});
  chunks.slice(0,2).forEach((chunk,i)=>text.append(svgNode("tspan",{x:pos.x,dy:i?20:0},chunk+(i===1 && chunks.length>2?"…":""))));group.append(text);svg.append(group);
 }
 $("workflow-canvas").replaceChildren(svg);
}

// Candidate strings are untrusted source/model data: render only as text.
let proposalOffset=0, proposalItem=null, proposalGeneration=0;
function reviewMessage(text) { $("graph-review-status").textContent=text; }
function reviewNode(tag,text) { const n=document.createElement(tag); n.textContent=text; return n; }
async function identityField(node, scope, title) {
 const box=document.createElement("div"), label=reviewNode("label",`${title}: ${node.label} (${node.kind})`), select=document.createElement("select"), key=document.createElement("input");
 select.append(new Option("대상 선택…",""),new Option("새 개체 — 식별키 직접 입력","new"));
 const params=new URLSearchParams({query:node.label});
 const data=await request("/api/v1/graph/entities?"+params);
 for(const e of data.items.filter(e=>e.kind===node.kind && ["global",scope].includes(e.scope))) select.append(new Option(`${e.label} · ${e.scope} · ${e.identity_key}`,e.id));
 label.append(select); key.placeholder="확인한 고유 식별키 (예: service:orders:prod)"; key.hidden=true; key.maxLength=200; key.setAttribute("aria-label",`${title}의 새 식별키`);
 select.addEventListener("change",()=>{key.hidden=select.value!=="new";});
 box.append(label,key);
 return {box,value:()=>select.value==="new"?{identity_key:key.value.trim()}:select.value?{existing_id:select.value}:null};
}
async function connectionEditor(row, card, heading) {
 const history=await request(`/api/v1/graph/assertions/${row.assertion_id}/history`);
 const current=history.versions.find(v=>!v.recorded_to);
 if(!current)return;
 const names={part_of:"소속",created_from:"생성 기반",depends_on:"현재 의존",uses:"사용",documents:"설명 대상",deployed_on:"배포 위치",affects:"영향 대상",addresses:"해결 대상",precedes:"다음 단계"};
 const state=reviewNode("p",current.status==="RETRACTED"?"연결 해제됨":row.review_note?.startsWith("AUTO:")?"자동 연결됨 · 잘못된 경우 수정하거나 해제할 수 있습니다.":"연결됨");
 card.append(state);
 const editor=document.createElement("details");editor.append(reviewNode("summary","연결 수정"));
 const fields=document.createElement("div");fields.className="identity-fields";
 async function endpoint(title,id) {
  const box=document.createElement("label");box.append(reviewNode("span",title));
  const search=document.createElement("input"),select=document.createElement("select"),button=reviewNode("button","대상 찾기");
  search.placeholder="프로젝트 또는 대상 이름";search.setAttribute("aria-label",title+" 검색");button.type="button";
  select.append(new Option(id,id));select.setAttribute("aria-label",title);
  async function load() {
   const data=await request("/api/v1/graph/entities?"+new URLSearchParams({query:search.value.trim()}));
   const selected=select.value;const oldLabel=select.selectedOptions[0]?.textContent||selected;
   select.replaceChildren(new Option(oldLabel,selected));
   for(const entity of data.items.filter(e=>["global",current.scope].includes(e.scope))) {
    if(entity.id===selected)select.options[0].textContent=entity.label+" · "+entity.scope;
    else select.append(new Option(entity.label+" · "+entity.scope,entity.id));
   }
  }
  button.addEventListener("click",()=>load().catch(e=>reviewMessage(e.message)));
  box.append(search,button,select);await load();return {box,select};
 }
 const [a,b]=await Promise.all([endpoint("주체",current.subject_id),endpoint("대상",current.object_id)]);
 const predicate=document.createElement("select");predicate.setAttribute("aria-label","관계");
 for(const [key,label] of Object.entries(names))predicate.append(new Option(label,key));
 if(!names[current.predicate])predicate.append(new Option(current.predicate,current.predicate));predicate.value=current.predicate;
 heading.textContent=`${a.select.selectedOptions[0].textContent} · ${names[current.predicate]||current.predicate}: ${b.select.selectedOptions[0].textContent}`;
 fields.append(a.box,predicate,b.box);editor.append(fields);
 const save=reviewNode("button","수정 저장"),remove=reviewNode("button","연결 해제");save.type=remove.type="button";
 remove.disabled=current.status==="RETRACTED";
 async function update(status) {
  save.disabled=remove.disabled=true;
  const {version_id,recorded_from,recorded_to,...payload}=current;
  try {
   await request(`/api/v1/graph/assertions/${row.assertion_id}`,{method:"PUT",body:JSON.stringify({...payload,
    subject_id:status==="RETRACTED"?current.subject_id:a.select.value,
    object_id:status==="RETRACTED"?current.object_id:b.select.value,
    predicate:status==="RETRACTED"?current.predicate:predicate.value,
    status,expected_version_id:version_id,change_note:status==="RETRACTED"?"사용자가 자동 연결 해제":"사용자가 자동 연결 수정",verified:true})});
   await loadProposals(false);
  }catch(e){reviewMessage(e.message);save.disabled=false;remove.disabled=current.status==="RETRACTED";}
 }
 save.addEventListener("click",()=>update("ACTIVE"));remove.addEventListener("click",()=>update("RETRACTED"));
 editor.append(save);card.append(editor,remove);
}
async function loadProposals(reset=true) {
 if(reset)proposalOffset=0;
 const version=++proposalGeneration, params=new URLSearchParams({offset:String(proposalOffset),limit:"10"});
 if(proposalItem)params.set("knowledge_id",proposalItem);
 reviewMessage("후보를 불러오는 중…"); $("graph-proposals-more").hidden=true;
 try {
  const data=await request("/api/v1/graph/proposals?"+params);
  if(version!==proposalGeneration)return;
  const fragment=document.createDocumentFragment();
  for(const row of data.items) {
   const p=row.candidate, card=document.createElement("article");card.className="graph-proposal";
   const relationNames={part_of:"소속",created_from:"생성 기반",depends_on:"현재 의존",uses:"사용",documents:"설명 대상",deployed_on:"배포 위치",affects:"영향 대상",addresses:"해결 대상",precedes:"다음 단계"};
   card.append(reviewNode("h3",`${p.subject.label} · ${relationNames[p.predicate]||p.predicate}: ${p.object.label}`),reviewNode("p",`${row.status} · ${row.scope} · 원문 버전 ${row.revision_id}`),reviewNode("blockquote",p.quote));
   if(p.condition)card.append(reviewNode("p","조건: "+p.condition));
   const sourceButton=reviewNode("button","근거 원문 보기"); sourceButton.type="button";
   sourceButton.addEventListener("click",async()=>{try{const data=await request(`/api/v1/knowledge/${row.knowledge_id}/revisions/${row.revision_id}/content`); const pre=reviewNode("pre",data.text);pre.style.whiteSpace="pre-wrap";pre.style.overflowWrap="anywhere";sourceButton.replaceWith(pre);}catch(e){reviewMessage(e.message);}});
   card.append(sourceButton);
   if(row.status==="LEGACY") {
    card.append(reviewNode("p","이전 추출 방식의 후보입니다. 기존 기록은 보존하며, 새 기준으로 다시 확인해야 합니다."));
    const retry=reviewNode("button","새 기준으로 관계 확인");retry.type="button";
    retry.addEventListener("click",async()=>{try{await request(`/api/v1/graph/extraction/knowledge/${row.knowledge_id}`,{method:"POST"});reviewMessage("관계 재확인을 요청했습니다.");}catch(e){reviewMessage(e.message);}});card.append(retry);
   }
   if(row.status==="PENDING") {
    const [a,b]=await Promise.all([identityField(p.subject,row.scope,"주체"),identityField(p.object,row.scope,"대상")]);
    const fields=document.createElement("div");fields.className="identity-fields";fields.append(a.box,b.box);
    const noteLabel=reviewNode("label","검토 사유"), note=document.createElement("input");note.maxLength=1000;noteLabel.append(note);
    const yes=reviewNode("button","확인 후 승인"), no=reviewNode("button","기각");yes.type=no.type="button";yes.className="primary";
    async function submit(decision) {
     if(!note.value.trim() || (decision==="approve" && (!a.value() || !b.value()))) {reviewMessage("검토 사유와 승인할 대상의 식별을 확인해 주세요.");return;}
     yes.disabled=no.disabled=true;
     try {const payload={decision,note:note.value.trim()};if(decision==="approve"){payload.subject=a.value();payload.object=b.value();}await request(`/api/v1/graph/proposals/${row.id}/review`,{method:"POST",body:JSON.stringify(payload)});await loadProposals(false);}
     catch(e){reviewMessage(e.message);yes.disabled=no.disabled=false;}
    }
    yes.addEventListener("click",()=>submit("approve"));no.addEventListener("click",()=>submit("reject"));
    const actions=document.createElement("div");actions.className="index-controls";actions.append(yes,no);card.append(fields,noteLabel,actions);
   } else if(row.status==="APPROVED" && row.assertion_id) {
    try {await connectionEditor(row,card,card.querySelector("h3"));}catch(e){card.append(reviewNode("p","연결 정보를 불러오지 못했습니다: "+e.message));}
   } else if(row.review_note) card.append(reviewNode("p","검토: "+row.review_note));
   fragment.append(card);
  }
  if(version!==proposalGeneration)return;
  $("graph-proposals").replaceChildren(fragment); $("graph-proposals-more").hidden=data.next_offset===null;
  $("graph-proposals-more").onclick=()=>{proposalOffset=data.next_offset;loadProposals(false);};
  reviewMessage(data.items.length?`${data.items.length}개 · 승인 전 후보는 검색 그래프에 포함되지 않습니다.`:"연결 후보가 없습니다. 추출 작업이 완료됐는지 확인해 주세요.");
 } catch(e) {if(version===proposalGeneration)reviewMessage(e.message);}
}
$("graph-proposals-load").addEventListener("click",()=>{proposalItem=null;loadProposals();});
$("graph-proposals-note").addEventListener("click",()=>{if(!selected){reviewMessage("노트를 먼저 선택하세요.");return;}proposalItem=selected.knowledge_id;loadProposals();});
$("graph-extract-note").addEventListener("click",async()=>{if(!selected){reviewMessage("노트를 먼저 선택하세요.");return;}try{const run=await request(`/api/v1/graph/extraction/knowledge/${selected.knowledge_id}`,{method:"POST"});reviewMessage(`추출 작업: ${run.status} · 원문 버전 ${run.revision_id}`);}catch(e){reviewMessage(e.message);}});
async function loadExtractionRuns(offset=0) {
 const version=++proposalGeneration;reviewMessage("추출 처리 내역을 불러오는 중…");$("graph-proposals-more").hidden=true;
 try {
  const data=await request(`/api/v1/graph/extraction/runs?offset=${offset}&limit=10`);
  if(version!==proposalGeneration)return;
  const fragment=document.createDocumentFragment();
  for(const row of data.items) {
   const card=document.createElement("article");card.className="graph-proposal";
   card.append(reviewNode("h3",`${row.status} · ${row.attempts}회 시도`),reviewNode("p",`원문 버전 ${row.revision_id}`),reviewNode("p",`${row.schema_version} · ${row.model}`));
   if(row.error_code)card.append(reviewNode("p",`오류: ${row.error_code}`));
   if(row.routing)card.append(reviewNode("p",`판단: ${row.routing.action} · ${row.routing.reason} · 모델 규칙 위반 관계 ${row.routing.rejected_relations || 0}개 제외`));
   const candidates=reviewNode("button","이 노트의 후보");candidates.type="button";candidates.addEventListener("click",()=>{proposalItem=row.knowledge_id;loadProposals();});card.append(candidates);
   if(row.status==="FAILED") {
    const retry=reviewNode("button","실패 작업 재시도");retry.type="button";
    retry.addEventListener("click",async()=>{retry.disabled=true;try{await request(`/api/v1/graph/extraction/runs/${row.id}/retry`,{method:"POST"});await loadExtractionRuns(offset);}catch(e){reviewMessage(e.message);retry.disabled=false;}});card.append(retry);
   }
   fragment.append(card);
  }
  $("graph-proposals").replaceChildren(fragment);$("graph-proposals-more").hidden=data.next_offset===null;
  $("graph-proposals-more").onclick=()=>loadExtractionRuns(data.next_offset);
  reviewMessage("DONE은 후보 추출 완료입니다. 그래프 반영 여부는 후보의 승인 상태에서 확인하세요.");
 } catch(e){if(version===proposalGeneration)reviewMessage(e.message);}
}
$("graph-runs-load").addEventListener("click",()=>loadExtractionRuns());

$("search-result-graph").addEventListener("click",()=>{
 if(!searchGraph || !mayLeave())return;
 if(searchGraph.status!=="READY"){status("관계를 조회하지 못했습니다. RDF 설정과 연결 상태를 확인하세요.",true);return;}
 const flow=searchGraph; clearReader();
 $("reader-title").textContent="검색 결과의 연결된 지식";
 $("show-workflow").disabled=false; $("flow-count").textContent=`(${flow.edges.length})`;
 $("graph-context").textContent="검색어와 검색된 원문에서 찾은 관계 · 카테고리/종류 필터는 직접 검색 문서에만 적용";
 $("workflow-status").textContent=`${flow.edges.length}개 관계 · ${flow.paths?.length || 0}개 연결 경로${flow.truncated || flow.paths_truncated?" · 일부만 표시":""} · 현재 원문 근거 기준`;
 renderWorkflow(flow); showNoteView("workflow");
});
