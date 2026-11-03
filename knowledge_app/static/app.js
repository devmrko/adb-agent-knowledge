"use strict";
const $ = id => document.getElementById(id);
const kinds = {DOCUMENT:"문서", DECISION:"결정", PREFERENCE:"선호", FACT:"사실", PROCEDURE:"절차", EPISODE:"경험"};
const pageSize = 10;
let originalSummary="", activeIndex=null, catalogOffset=0, referenceOffset=0, originalUri=null, originalFilename="source.txt";
let sessionMode = true, csrf = "";
let token = "", offset = 0, listMode = true, generation = 0, controller;
let selected = null, original = "", editing = false, saving = false, pending = null;
const READ_ONLY = true;
let searchGraph=null;
let graphGeneration=0, graphController, graphSource=null;
let contentGeneration = 0, contentController, jobTimer, categoryValue = "", relationOnly = false;
function status(message, error = false) { $("status").textContent = message; $("status").classList.toggle("error", error); }
function noteStatus(message, error = false) { $("note-status").textContent = message; $("note-status").classList.toggle("error", error); }
function dirty() { return editing && ($("reader-body").value !== original || $("reader-summary").value !== originalSummary); }
function mayLeave() { return !saving && (!dirty() || window.confirm("저장하지 않은 수정 내용을 버릴까요?")); }
function editMode(value) { value=READ_ONLY?false:value; editing=value; $("reader-body").readOnly=!value; $("reader-summary").readOnly=!value; $("edit").hidden=READ_ONLY || value; $("save").hidden=!value; $("cancel").hidden=!value; }
function clearReader() {
 $("note-memories").replaceChildren(); $("note-memory-status").textContent=""; $("note-memories-more").hidden=true;
 $("capture-content").replaceChildren(); $("capture-count").textContent=""; $("capture-status").textContent="";
 graphGeneration++; graphController?.abort(); graphSource=null;
 showNoteView("summary"); $("reader-summary").value=""; originalSummary=""; originalUri=null; referenceOffset=0; $("reference-indexes").replaceChildren(); $("reference-sources").textContent=""; $("download-original").disabled=true; $("references-more").hidden=true; $("show-workflow").disabled=true; $("flow-count").textContent=""; $("workflow-canvas").replaceChildren(); $("workflow-relations").replaceChildren(); $("workflow-evidence").hidden=true;
 contentGeneration++; contentController?.abort(); clearTimeout(jobTimer); selected=null; pending=null; original=""; editMode(false);
 $("reader-title").textContent="노트를 선택하세요"; $("reader-body").value=""; updateLines(); $("reader-meta").textContent=""; $("edit-origin").hidden=true; $("edit").disabled=true; $("check-job").hidden=true; noteStatus("");
}
function disconnect() {
 clearPrinciples();
 memoryDetailGeneration++; $("memory-evidence").replaceChildren(); $("memory-graph").replaceChildren(); $("memory-edges").replaceChildren(); $("note-memories").replaceChildren(); $("memory-evidence-status").textContent=""; $("memory-graph-status").textContent=""; $("note-memory-status").textContent="";
 memoryGeneration++; $("memory-results").replaceChildren(); $("memory-body").textContent=""; $("memory-meta").textContent=""; $("memory-title").textContent="메모리를 선택하세요"; $("memory-status").textContent=""; $("memory-agent").replaceChildren(new Option("내 전체 에이전트","")); $("memory-thread").replaceChildren(new Option("내 전체 대화",""));
 proposalGeneration++; $("graph-proposals").replaceChildren(); $("graph-review-status").textContent=""; $("graph-proposals-more").hidden=true;
 searchGraph=null; $("search-result-graph").hidden=true;
 generation++; controller?.abort(); clearReader(); activeIndex=null; $("index-catalog").replaceChildren(); $("index-more").hidden=true; token=""; csrf=""; $("token").value=""; $("connect-form").hidden=false; $("connected").hidden=true; $("connection").textContent="연결 전"; $("results").replaceChildren(); $("category").replaceChildren(new Option("전체 카테고리","")); categoryValue=""; relationOnly=false; $("has-relations").checked=false; $("count").textContent=""; $("pagination").hidden=true; status("API 토큰으로 연결하면 노트를 볼 수 있습니다.");
}
function authHeaders() { return sessionMode ? {"X-CSRF-TOKEN":csrf} : {Authorization:"Bearer "+token}; }
async function request(path, options={}) {
 const method=(options.method || "GET").toUpperCase();
 const readPosts=["/api/v1/knowledge/search","/api/v1/graph/search","/api/v1/graph/identities/resolve","/api/v1/agent-memory/search","/api/v1/agent-memory/graph"];
 if(READ_ONLY && !(method==="PUT" && path==="/api/v1/principles") && method!=="GET" && method!=="HEAD" && !(method==="POST" && readPosts.includes(path)))throw new Error("데이터 변경은 MCP에서 진행해 주세요. 웹은 조회 전용입니다.");
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
  original=data.text; originalSummary=data.summary || ""; $("reader-summary").value=originalSummary; $("summary-kind").textContent=data.summary_kind==="EXTRACTIVE"?"원문 발췌 요약 · 전체 내용은 상세에서 확인":"작성된 요약 · "+data.summary_kind; $("reader-body").value=original; updateLines(); $("edit").disabled=READ_ONLY;
  $("edit-origin").hidden=data.edit_origin!=="HUMAN"; $("edit-origin").textContent="사용자 편집";
  const sources=(data.sources || []).map(s=>`${s.kind}: ${s.location}${s.machine_id ? " · 머신 "+s.machine_id : ""}${s.version ? " · 버전 "+s.version : ""}${s.locator ? " · "+s.locator : ""}`);
  $("reader-meta").textContent=`지식 ${item.knowledge_id}\n버전 ${item.revision_id}\n범위 ${item.scope || ""}\n편집 경로 ${data.edit_origin || "UNKNOWN"}\n작성 머신 ${data.origin_machine_label || data.origin_machine_id || "기록 없음"}\n${sources.join("\n") || "출처 위치: 기록 없음"}`;
  noteStatus(""); loadCapture(item,version); if(graphVersion===graphGeneration)loadWorkflow(item,version);
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
 const requestedView=storeView, requestedGeneration=generation;
 if(token && (storeView==="memory" || storeView==="all")) { await loadMemories(); if(requestedView!==storeView || requestedGeneration!==generation || storeView==="memory") return; }
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
$("search-form").addEventListener("submit",event=>{event.preventDefault(); if(!mayLeave()) return; activeIndex=null; offset=0; memoryOffset=0; listMode=!$("query").value.trim(); load();});
$("browse").addEventListener("click",()=>{if(!mayLeave()) return; activeIndex=null; offset=0; memoryOffset=0; listMode=true; load();});
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
$("edit").addEventListener("click",()=>{if(READ_ONLY)return;showNoteView("source");editMode(true);noteStatus("원문을 수정한 뒤 저장하세요. 이전 버전은 보존됩니다.");$("reader-body").focus();});
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
let storeView="knowledge", memoryOffset=0, memoryNext=null, memoryGeneration=0;
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
 for(const name of ["summary","source","references","workflow","capture"]) { $(name+"-view").hidden=view!==name; $("show-"+name).setAttribute("aria-pressed",String(view===name)); }
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
    const retry=reviewNode("button","새 기준으로 관계 확인");retry.type="button";retry.hidden=READ_ONLY;
    retry.addEventListener("click",async()=>{try{await requestGraphExtraction(row.knowledge_id);}catch(e){reviewMessage(e.message);}});card.append(retry);
   }
   if(row.status==="PENDING" && !READ_ONLY) {
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
   } else if(row.status==="APPROVED" && row.assertion_id && !READ_ONLY) {
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
async function requestGraphExtraction(knowledgeId) {
 const schema=await request("/api/v1/graph/extraction/schema");
 if(schema.mode==="agent") {
  reviewMessage(`에이전트 추출 모드입니다. Codex·Claude에 이 지식의 관계 연결을 요청하세요: ${knowledgeId} (knowledge_graph_prepare). 별도 LLM 작업은 등록하지 않았습니다.`);
  return;
 }
 const run=await request(`/api/v1/graph/extraction/knowledge/${knowledgeId}`,{method:"POST"});
 reviewMessage(`추출 작업: ${run.status} · 원문 버전 ${run.revision_id}`);
}
$("graph-extract-note").addEventListener("click",async()=>{if(!selected){reviewMessage("노트를 먼저 선택하세요.");return;}try{await requestGraphExtraction(selected.knowledge_id);}catch(e){reviewMessage(e.message);}});
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
   if(row.status==="FAILED" && !READ_ONLY) {
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


// Data handling is performed through MCP; the web displays recorded clarification only.
$("show-capture").addEventListener("click",()=>showNoteView("capture"));
$("capture-refresh").addEventListener("click",()=>{if(selected)loadCapture(selected,contentGeneration);});
async function loadCapture(item, version) {
 $("capture-status").textContent="확인 내용을 불러오는 중…";
 try {
  const data=await request(`/api/v1/graph/reviews/${item.knowledge_id}/capture?revision_id=${encodeURIComponent(item.revision_id)}`);
  if(version!==contentGeneration)return;
  $("capture-content").replaceChildren();
  const draft=data.capture;
  if(!draft){$("capture-status").textContent="등록된 확인 질문이 없습니다.";$("capture-count").textContent="";return;}
  const pending=draft.pending_question_keys.length;
  $("capture-count").textContent=pending?`(${pending})`:"";
  $("capture-status").textContent=!data.source_current?"이전 원문에 대한 기록":pending?`확인 대기 ${pending}개`:data.review.status==="COMPLETE"?"검토 완료":"답변 기록 완료 · 에이전트 반영 대기";
  $("capture-content").append(element("p",draft.summary));
  if(draft.hypotheses.length){const box=document.createElement("details");box.append(element("summary","추론 후보 · 확정 사실 아님"));for(const h of draft.hypotheses)box.append(element("p",h));$("capture-content").append(box);}
  for(const q of draft.questions){
   const card=document.createElement("section");card.className="capture-question";
   card.append(element("h3",q.question),element("p",q.reason));
   const evidence=document.createElement("details");evidence.append(element("summary","질문 근거"),element("blockquote",q.quote));card.append(evidence);
   const labels={answered:"답변 기록됨",deferred:"미정 · 확인 대기",not_applicable:"해당 없음"};
   card.append(element("strong",q.answer?labels[q.answer.disposition]:"아직 답변 없음"));
   if(q.answer){card.append(element("p",q.answer.text),element("small","기록 시각: "+q.answer.recorded_at));}
   $("capture-content").append(card);
  }
 }catch(error){if(version===contentGeneration){$("capture-status").textContent=error.message==="AUTH"?"연결 상태를 확인해 주세요.":"확인 내용을 불러오지 못했습니다. 다시 확인해 주세요.";}}
}


async function loadMemoryProfiles() {
 const v=memoryGeneration;
 const data=await request("/api/v1/agent-memory/profiles");
 if(v!==memoryGeneration || !token)return;
 const agent=$("memory-agent").value, thread=$("memory-thread").value;
 for(const [kind,id,label] of [["agent","memory-agent","내 전체 에이전트"],["thread","memory-thread","내 전체 대화"]]) {
  $(id).replaceChildren(new Option(label,""),...(data.items || []).filter(p=>p.kind===kind).map(p=>new Option(p.name+" · "+p.id.slice(0,8),p.id)));
 }
 $("memory-agent").value=agent; $("memory-thread").value=thread;
}
function readMemory(item) {
 memorySelection=item; memoryEvidenceOffset=0; const detailVersion=++memoryDetailGeneration;
 $("memory-evidence").replaceChildren(); $("memory-graph").replaceChildren(); $("memory-edges").replaceChildren(); $("memory-evidence-more").hidden=true;
 loadMemoryEvidence(item,detailVersion); loadMemoryGraph(item,detailVersion);
 $("memory-title").textContent=item.title;
 $("memory-body").textContent=item.text;
 $("memory-meta").textContent=[
  "에이전트 메모리 · "+item.memory_type+" · "+item.status,
  "에이전트: "+(item.agent_name || "지정 없음"),
  "대화: "+(item.thread_name || item.thread_id || "지정 없음"),
  "범위: "+item.scope, "기록 시점: "+(item.timestamp || "미상"), "ID: "+item.memory_id
 ].join("\n");
}
async function loadMemories() {
 const v=++memoryGeneration;
 memoryDetailGeneration++; memorySelection=null; $("memory-evidence").replaceChildren(); $("memory-graph").replaceChildren(); $("memory-edges").replaceChildren(); $("memory-evidence-status").textContent=""; $("memory-graph-status").textContent=""; $("memory-evidence-more").hidden=true;
 $("memory-status").textContent="메모리를 불러오는 중…";
 $("memory-results").replaceChildren(); $("memory-body").textContent=""; $("memory-meta").textContent=""; $("memory-title").textContent="메모리를 선택하세요";
 try {
  const data=await request("/api/v1/agent-memory/search",{method:"POST",body:JSON.stringify({
   query:listMode?"":$("query").value.trim(), agent_id:$("memory-agent").value || null,
   thread_id:$("memory-thread").value || null, scope:$("scope").value.trim() || null,
   offset:memoryOffset,limit:10,include_invalid:$("memory-history").checked
  })});
  if(v!==memoryGeneration)return;
  $("connection").textContent="연결됨"; $("connect-form").hidden=true; $("connected").hidden=false;
  memoryNext=data.next_offset; $("memory-prev").disabled=memoryOffset===0; $("memory-next").disabled=memoryNext==null;
  $("memory-page").textContent=(memoryOffset/10+1)+" 페이지";
  $("memory-status").textContent=data.status==="NOT_CONFIGURED"?"에이전트 메모리 연결이 필요합니다. 기존 업무 지식은 계속 조회할 수 있습니다.":data.truncated?"조회 상한에 도달했습니다. 검색어나 필터로 좁혀 주세요.":data.items.length?"":"저장된 메모리가 없습니다.";
  for(const item of data.items) {
   const row=element("button",""); row.className="note-row";
   row.append(element("strong",item.title),element("small","에이전트 메모리 · "+(item.agent_name || "공통")+" · "+item.status));
   row.addEventListener("click",()=>readMemory(item)); $("memory-results").append(row);
  }
  if(data.items[0])readMemory(data.items[0]);
  status(storeView==="all"?"업무 지식과 에이전트 메모리를 각각 조회합니다.":"");
 } catch(error) {if(v===memoryGeneration){$("memory-status").textContent="메모리 조회에 실패했습니다. 기존 업무 지식 조회와는 별도입니다."; handleError(error);}}
}
for(const button of document.querySelectorAll("#store-tabs button"))button.addEventListener("click",async()=>{
 if(!mayLeave())return;
 storeView=button.dataset.store; memoryGeneration++; generation++; controller?.abort();
 const tabGeneration=memoryGeneration;
 for(const b of document.querySelectorAll("#store-tabs button"))b.setAttribute("aria-pressed",String(b===button));
 $("memory-panel").hidden=!["memory","all"].includes(storeView);
 $("search-graph").hidden=storeView==="memory";
 $("kind").closest("label").hidden=storeView==="memory";
 document.querySelector(".workspace").hidden=storeView==="memory";
 $("graph-review-panel").hidden=storeView==="memory";
 memoryOffset=0; offset=0; activeIndex=null;
 if(!token){status("먼저 연결해 주세요.");return;}
 if(["memory","all"].includes(storeView)){try{await loadMemoryProfiles();}catch(error){handleError(error);}}
 if(tabGeneration!==memoryGeneration)return;
 if(storeView==="graph"){$("search-graph").click();return;}
 await load();
});
for(const id of ["memory-agent","memory-thread","memory-history"])$(id).addEventListener("change",()=>{memoryOffset=0;loadMemories();});
$("memory-prev").addEventListener("click",()=>{memoryOffset=Math.max(0,memoryOffset-10);loadMemories();});
$("memory-next").addEventListener("click",()=>{if(memoryNext!=null){memoryOffset=memoryNext;loadMemories();}});
$("search-form").addEventListener("submit",()=>{memoryOffset=0;});
$("browse").addEventListener("click",()=>{memoryOffset=0;});

let memoryDetailGeneration=0,memorySelection=null,memoryEvidenceOffset=0,noteMemoryOffset=0;
function chooseStore(view){
 storeView=view;generation++;controller?.abort();memoryGeneration++;
 for(const b of document.querySelectorAll("#store-tabs button"))b.setAttribute("aria-pressed",String(b.dataset.store===view));
 $("memory-panel").hidden=view!=="memory";document.querySelector(".workspace").hidden=view==="memory";
 $("graph-review-panel").hidden=view==="memory";$("search-graph").hidden=view==="memory";$("kind").closest("label").hidden=view==="memory";
}
async function loadMemoryEvidence(item,version){
 $("memory-evidence-status").textContent="근거를 확인하는 중…";
 try{
  const data=await request("/api/v1/agent-memory/references?"+new URLSearchParams({memory_id:item.memory_id,offset:String(memoryEvidenceOffset),limit:"20"}));
  if(version!==memoryDetailGeneration)return;
  if(memoryEvidenceOffset===0)$("memory-evidence").replaceChildren();
  for(const link of data.items){
   const card=element("section","");card.className="memory-evidence-card";
   const b=element("button",link.title+" · "+(link.status==="CURRENT"?"현재 근거":"재검토 필요"));
   b.addEventListener("click",()=>{chooseStore("knowledge");read({knowledge_id:link.knowledge_id,revision_id:link.revision_id,title:link.title,scope:link.scope});});
   card.append(b,element("blockquote",link.quote),element("small","원문 버전 "+link.revision_id),element("p",link.reason));$("memory-evidence").append(card);
  }
  $("memory-evidence-status").textContent=data.items.length?"인용을 선택하면 당시 원문 버전을 엽니다.":"연결된 근거가 없습니다.";
  memoryEvidenceOffset=data.next_offset;$("memory-evidence-more").hidden=memoryEvidenceOffset==null;
 }catch(e){if(version===memoryDetailGeneration){$("memory-evidence-status").textContent="근거 조회 불가";handleError(e);}}
}
async function loadMemoryGraph(item,version){
 $("memory-graph-status").textContent="기억 관계를 확인하는 중…";
 try{
  const graph=await request("/api/v1/agent-memory/graph",{method:"POST",body:JSON.stringify({memory_id:item.memory_id,depth:2,max_edges:30})});
  if(version!==memoryDetailGeneration)return;
  $("memory-graph-status").textContent=graph.edges.length?graph.edges.length+"개 관계"+(graph.truncated?" · 일부만 표시":""):"등록된 기억 관계가 없습니다.";
  renderMemoryGraph(graph);
 }catch(e){if(version===memoryDetailGeneration){$("memory-graph-status").textContent="기억 관계 조회 불가";handleError(e);}}
}

function memoryRelationLabel(value) {
 return {supports:"뒷받침함",contradicts:"내용이 충돌함",supersedes:"이전 기억을 대체함",refines:"내용을 보완함",duplicates:"중복된 기억"}[value] || value;
}
function memoryStateLabel(value) {
 return {valid:"현재 기억",invalid:"과거 기억"}[value] || value || "상태 미상";
}
function memoryNodeCard(node) {
 const card=element("section","");card.className="memory-node-card";
 const type={memory:"기억",fact:"사실 기록",guideline:"지침",preference:"선호"}[node.memory_type] || node.memory_type || "기억";
 card.append(element("small",type+" · "+memoryStateLabel(node.status)+(node.timestamp?" · "+String(node.timestamp).split("T")[0]:"")));
 const title=element("button",node.title);title.className="memory-node-title";
 title.addEventListener("click",()=>readMemory({...node,memory_id:node.id}));
 card.append(title);
 const source=element("details","");source.className="memory-node-source";
 source.append(element("summary","내용·근거 보기"));
 const body=element("p",node.text);body.className="memory-node-body";source.append(body);
 const proofs=element("div","");source.append(proofs);
 let loaded=false;
 source.addEventListener("toggle",async()=>{
  if(!source.open || loaded)return;loaded=true;proofs.textContent="원문 근거를 확인하는 중…";
  try {
   const data=await request("/api/v1/agent-memory/references?"+new URLSearchParams({memory_id:node.id,limit:"5"}));
   if(!source.isConnected)return;proofs.replaceChildren();
   for(const link of data.items){
    const b=element("button",link.title+" · "+(link.status==="CURRENT"?"현재 원문":"이전 원문 · 다시 확인 필요"));
    b.addEventListener("click",()=>{chooseStore("knowledge");read({knowledge_id:link.knowledge_id,revision_id:link.revision_id,title:link.title,scope:link.scope});});
    proofs.append(b,element("blockquote",link.quote));
   }
   if(!data.items.length)proofs.append(element("p","연결된 원문 근거가 없습니다."));
   if(data.next_offset!=null)proofs.append(element("p","일부 근거만 표시합니다. 기억을 열어 전체 근거를 확인하세요."));
  }catch(e){if(source.isConnected){proofs.textContent="근거를 불러오지 못했습니다.";loaded=false;}}
 });
 card.append(source);
 return card;
}
function renderMemoryGraph(graph){
 $("memory-graph").replaceChildren();$("memory-edges").replaceChildren();if(!graph.edges.length)return;
 const nodes=new Map(graph.nodes.map(n=>[n.id,n]));
 for(const edge of graph.edges){
  const a=nodes.get(edge.source),b=nodes.get(edge.target);if(!a||!b)continue;
  const row=element("article","");row.className="memory-relation-card";
  const pair=element("div","");pair.className="memory-relation-pair";
  const relation=element("div","");relation.className="memory-relation-label";
  relation.append(element("span","→"),element("strong",memoryRelationLabel(edge.relation)));
  relation.title="기억 간 관계: "+edge.relation+" · 방향과 상태는 에이전트 메모리 기록을 그대로 표시합니다.";
  pair.append(memoryNodeCard(a),relation,memoryNodeCard(b));row.append(pair);
  row.append(element("p","연결 이유: "+(edge.reason || "기록되지 않음")));
  const raw=element("details","");raw.className="memory-sdk-details";raw.append(element("summary","메모리 기록 상세"));
  raw.append(element("pre",edge.source+" → "+edge.relation+" → "+edge.target+"\n"+a.status+" → "+b.status));row.append(raw);
  $("memory-edges").append(row);
 }
 const details=element("details","");details.className="memory-overview";
 details.append(element("summary","전체 연결 펼쳐 보기 · "+graph.nodes.length+"개 기억"));
 const help=element("p","번호는 아래의 전체 제목과 대응합니다. 화살표는 에이전트 메모리에 저장된 관계 방향입니다.");details.append(help);
 const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg"),height=Math.max(160,graph.nodes.length*65);
 svg.setAttribute("viewBox","0 0 560 "+height);svg.setAttribute("role","img");svg.setAttribute("aria-label","기억 관계 전체 지도. 번호별 제목은 아래 목록에 표시합니다.");
 const defs=document.createElementNS(ns,"defs"),marker=document.createElementNS(ns,"marker"),arrow=document.createElementNS(ns,"path");
 for(const [k,v] of Object.entries({id:"memory-arrow",viewBox:"0 0 10 10",refX:"9",refY:"5",markerWidth:"6",markerHeight:"6",orient:"auto"}))marker.setAttribute(k,v);
 arrow.setAttribute("d","M 0 0 L 10 5 L 0 10 z");arrow.setAttribute("fill","#7b8790");marker.append(arrow);defs.append(marker);svg.append(defs);
 const positions=new Map(graph.nodes.map((n,i)=>[n.id,{x:100+(i%2)*320,y:40+i*65,index:i+1}]));
 for(const edge of graph.edges){
  const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)continue;
  const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy)||1,line=document.createElementNS(ns,"line");
  for(const [k,v] of Object.entries({x1:a.x+dx/length*18,y1:a.y+dy/length*18,x2:b.x-dx/length*20,y2:b.y-dy/length*20,stroke:"#7b8790","stroke-width":2,"marker-end":"url(#memory-arrow)"}))line.setAttribute(k,String(v));
  const label=document.createElementNS(ns,"title");label.textContent=memoryRelationLabel(edge.relation);line.append(label);svg.append(line);
 }
 const legend=element("ol","");legend.className="memory-graph-legend";
 for(const node of graph.nodes){
  const pos=positions.get(node.id),circle=document.createElementNS(ns,"circle"),text=document.createElementNS(ns,"text");
  for(const [k,v] of Object.entries({cx:pos.x,cy:pos.y,r:18,fill:node.status==="valid"?"#356d79":"#777"}))circle.setAttribute(k,String(v));
  svg.append(circle);for(const [k,v] of Object.entries({x:pos.x,y:pos.y+5,fill:"white","text-anchor":"middle","font-size":14}))text.setAttribute(k,String(v));text.textContent=String(pos.index);svg.append(text);
  const li=element("li",""),button=element("button",node.title);button.addEventListener("click",()=>readMemory({...node,memory_id:node.id}));li.append(button);legend.append(li);
 }
 details.append(svg,legend);$("memory-graph").append(details);
}
async function loadNoteMemories(){
 if(!selected)return;const item=selected,version=contentGeneration;$("note-memory-status").textContent="관련 기억을 확인하는 중…";
 try{
  const data=await request("/api/v1/agent-memory/references?"+new URLSearchParams({knowledge_id:item.knowledge_id,offset:String(noteMemoryOffset),limit:"20"}));
  if(version!==contentGeneration)return;if(noteMemoryOffset===0)$("note-memories").replaceChildren();
  for(const link of data.items){
   const b=element("button",link.memory.title+" · "+(link.status==="CURRENT"?"현재 근거":"재검토 필요"));b.className="note-row";
   b.addEventListener("click",()=>{chooseStore("memory");readMemory({...link.memory,memory_id:link.memory.id});});$("note-memories").append(b);
  }
  $("note-memory-status").textContent=data.items.length?"":"연결된 에이전트 메모리가 없습니다.";
  noteMemoryOffset=data.next_offset;$("note-memories-more").hidden=noteMemoryOffset==null;
 }catch(e){if(version===contentGeneration)$("note-memory-status").textContent="에이전트 메모리 연결을 조회할 수 없습니다.";}
}
$("memory-evidence-more").addEventListener("click",()=>{if(memorySelection&&memoryEvidenceOffset!=null)loadMemoryEvidence(memorySelection,memoryDetailGeneration);});
$("show-references").addEventListener("click",()=>{noteMemoryOffset=0;loadNoteMemories();});
$("note-memories-more").addEventListener("click",()=>{if(noteMemoryOffset!=null)loadNoteMemories();});

// User-approved principles are configuration, not editable retrieved knowledge.
let principleVersion=null, principleRules=[], principleDirty=false, principleEpoch=0, principleHistoryOffset=0;
const principleTemplates=[
 ["formal","존댓말","사용자에게 한국어 존댓말로 답한다. 사용자의 말투에 따라 반말이나 퉁명스러운 표현으로 바꾸지 않는다."],
 ["resolve","해결 중심","문제를 설명하는 데서 끝내지 않는다. 허용된 범위에서 해결을 진행하고, 막히면 구체적인 장애 원인과 다음 실행 방법을 제시한다."],
 ["plan","행동 전 계획","여러 단계의 작업은 실행 전에 목표·주요 단계·완료 기준을 짧게 정리한다. 단순한 질문이나 수정에는 불필요하게 긴 계획을 만들지 않는다."],
 ["simple","단순한 접근","요구를 충족하는 가장 단순한 방법부터 시도한다. 복잡한 구성이나 새 의존성은 필요한 이유가 확인됐을 때 추가한다."],
 ["correct","오류 인정·개선","잘못 안내했으면 무엇이 틀렸는지 인정하고 짧게 사과한다. 원인을 확인해 수정하고, 결과를 검증한다."],
 ["clear","쉬운 설명","배경지식이 없는 사람도 이해하도록 결론부터 설명한다. 어려운 용어는 풀어 쓰고 필요한 경우 구체적인 예를 든다. 정확성은 유지한다."]
];
const principleSuggestions={
 facts:["facts","확인 수준 구분","확인한 사실·추정·아직 확인하지 못한 내용을 구분하고, 실행이나 검증 없이 완료했다고 말하지 않는다."],
 context:["context","기존 맥락 유지","이어지는 요청에서는 기존 목표와 사용자 정정을 유지하고, 이미 알려준 정보를 반복해서 묻지 않는다."],
 verify:["verify","완료 확인","변경 후 사용자 관점에서 실제로 동작하는지 확인한다. 테스트 통과와 실제 운영 검증을 구분한다."]
};
function clearPrinciples(){principleEpoch++;principleVersion=null;principleRules=[];principleDirty=false;$("principles-rules").replaceChildren();$("principles-preview").textContent="";$("principles-history").replaceChildren();$("principles-save").disabled=true;$("principles-note").value="";$("principles-status").textContent="";}
function principlePreview(){
 const scope=$("principles-preview-scope").value.trim().toLowerCase();
 const rows=principleRules.filter(r=>r.enabled && (r.scope==="global" || r.scope===scope));
 $("principles-preview").textContent=`사용자 승인 원칙 · ${principleDirty?"미저장 초안":"버전 "+principleVersion}\n상위 지침과 현재 사용자의 명시적 요청을 우선합니다.\n\n`+rows.map((r,i)=>`${i+1}. ${r.title}\n${r.instruction}`).join("\n\n");
}
function markPrinciples(){principleDirty=true;$("principles-status").textContent="미저장 초안 · 승인하고 적용해야 다음 요청에 반영됩니다.";principlePreview();}
function renderPrinciples(){
 $("principles-rules").replaceChildren();
 principleRules.forEach((rule,index)=>{
  const box=element("fieldset","");box.append(element("legend",`${index+1}. 원칙`));
  for(const [key,label,max] of [["title","제목",100],["instruction","적용 문구",600],["scope","범위 (global 또는 project:이름)",108]]){
   const l=element("label",label),input=document.createElement(key==="instruction"?"textarea":"input");input.value=rule[key];input.maxLength=max;input.addEventListener("input",()=>{rule[key]=input.value;markPrinciples();});l.append(input);box.append(l);
  }
  const enabled=document.createElement("input");enabled.type="checkbox";enabled.checked=rule.enabled;enabled.addEventListener("change",()=>{rule.enabled=enabled.checked;markPrinciples();});const label=element("label"," 활성화 ");label.prepend(enabled);box.append(label);
  for(const [text,action,disabled] of [["위로",()=>{[principleRules[index-1],principleRules[index]]=[rule,principleRules[index-1]];},index===0],["아래로",()=>{[principleRules[index],principleRules[index+1]]=[principleRules[index+1],rule];},index===principleRules.length-1],["초안에서 제거",()=>principleRules.splice(index,1),false]]){
   const button=element("button",text);button.type="button";button.disabled=disabled;button.addEventListener("click",()=>{action();markPrinciples();renderPrinciples();});box.append(button);
  }
  $("principles-rules").append(box);
 });principlePreview();
}
async function loadPrinciples(){
 if(principleDirty && !confirm("저장하지 않은 원칙 초안을 버리고 다시 불러올까요?"))return;
 const epoch=++principleEpoch;
 try{const data=await request("/api/v1/principles");if(epoch!==principleEpoch)return;principleVersion=data.version;principleRules=data.rules;principleDirty=false;$("principles-save").disabled=false;renderPrinciples();$("principles-status").textContent=`저장 버전 ${data.version} · ${data.rules.length}개`;}
 catch(error){if(epoch===principleEpoch)handleError(error);}
}
function addPrinciple(template){
 if(principleVersion===null){$("principles-status").textContent="먼저 저장된 원칙을 불러오세요.";return;}
 if(principleRules.length>=20){$("principles-status").textContent="원칙은 최대 20개입니다.";return;}
 if(template && principleRules.some(r=>r.id===template[0]))return;
 principleRules.push({id:template?.[0] || crypto.randomUUID(),title:template?.[1] || "새 원칙",instruction:template?.[2] || "",scope:"global",enabled:true});markPrinciples();renderPrinciples();
}
async function savePrinciples(){
 if(principleVersion===null)return;
 const note=$("principles-note").value.trim();if(!note){$("principles-status").textContent="변경 이유를 입력해 주세요.";return;}
 if(!confirm("이 원칙을 승인하고 이후 요청에 적용할까요?"))return;
 const epoch=principleEpoch, submitted=JSON.stringify(principleRules);
 $("principles-save").disabled=true;
 try{const data=await request("/api/v1/principles",{method:"PUT",body:JSON.stringify({expected_version:principleVersion,approved:true,rules:JSON.parse(submitted),change_note:note})});if(epoch!==principleEpoch)return;principleVersion=data.version;principleDirty=JSON.stringify(principleRules)!==submitted;$("principles-note").value="";$("principles-status").textContent=`버전 ${data.version} 저장 완료 · ${principleDirty?"저장 중 편집한 내용은 아직 초안입니다":"원칙 지원 훅의 다음 요청부터 적용"}`;principlePreview();}
 catch(error){if(epoch===principleEpoch){$("principles-status").textContent="저장 실패 · 초안은 유지됩니다. 충돌이면 초안을 복사한 뒤 다시 불러오세요.";handleError(error);}}
 finally{if(epoch===principleEpoch)$("principles-save").disabled=false;}
}
async function principleHistory(reset){
 if(reset){principleHistoryOffset=0;$("principles-history").replaceChildren();}const epoch=principleEpoch;
 try{const data=await request(`/api/v1/principles/history?offset=${principleHistoryOffset}&limit=10`);if(epoch!==principleEpoch)return;
 for(const row of data.items){const d=element("details","");d.append(element("summary",`버전 ${row.version} · ${row.created_at} · ${row.change_note}`),element("pre",JSON.stringify(row.rules,null,2)));$("principles-history").append(d);}
 $("principles-history-more").hidden=data.next_offset===null;principleHistoryOffset=data.next_offset ?? 0;
 }catch(error){if(epoch===principleEpoch)handleError(error);}
}
$("principles-load").addEventListener("click",loadPrinciples);
$("principles-defaults").addEventListener("click",()=>principleTemplates.forEach(addPrinciple));
$("principles-add").addEventListener("click",()=>addPrinciple(null));
$("principles-suggest").addEventListener("click",()=>addPrinciple(principleSuggestions[$("principles-suggestion").value]));
$("principles-save").addEventListener("click",savePrinciples);
$("principles-preview-scope").addEventListener("input",principlePreview);
$("principles-history-load").addEventListener("click",()=>principleHistory(true));
$("principles-history-more").addEventListener("click",()=>principleHistory(false));
window.addEventListener("beforeunload",event=>{if(principleDirty){event.preventDefault();event.returnValue="";}});

$("sql-guide-toggle").addEventListener("click",()=>{
 const panel=$("sql-guide"), open=panel.hidden;
 panel.hidden=!open;
 $("sql-guide-toggle").setAttribute("aria-expanded",String(open));
 if(open)panel.scrollIntoView({block:"start"});
});
