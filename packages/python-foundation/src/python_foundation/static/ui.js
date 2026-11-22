/* Foundation UI: safe native HTML factories and light-DOM custom elements. */
(() => {
 "use strict";
 const paths={
  document:["M6 3h8l4 4v14H6z","M14 3v5h4","M9 12h6M9 16h6"],
  search:["M20 20l-5-5","M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0"],
  grid:["M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"],
  memory:["M8 3h8l5 5v8l-5 5H8l-5-5V8z","M9 9h6v6H9z"],
  graph:["M6 6l12 5M6 6v12l12-7","M8 6a2 2 0 1 1-4 0 2 2 0 0 1 4 0M20 11a2 2 0 1 1-4 0 2 2 0 0 1 4 0M8 18a2 2 0 1 1-4 0 2 2 0 0 1 4 0"],
  settings:["M4 7h16M4 17h16","M8 4v6M16 14v6"],
  code:["M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"],
  arrow:["M19 12H5M11 6l-6 6 6 6"],
  close:["M6 6l12 12M18 6L6 18"],
  folder:["M3 6h7l2 3h9v11H3z"],
  check:["M5 12l4 4L19 6"]
 };
 function element(tag,text="",className="") {
  const node=document.createElement(tag);node.textContent=text;
  if(className)node.className=className;
  if(tag==="button"){node.classList.add("ui-button");node.type="button";}
  if(["input","select","textarea"].includes(tag))node.classList.add("ui-input");
  return node;
 }
 function icon(name) {
  const ns="http://www.w3.org/2000/svg",svg=document.createElementNS(ns,"svg");
  svg.classList.add("ui-icon");svg.setAttribute("viewBox","0 0 24 24");svg.setAttribute("aria-hidden","true");
  for(const d of paths[name] || paths.document){const p=document.createElementNS(ns,"path");p.setAttribute("d",d);svg.append(p);}
  return svg;
 }
 function badge(text,tone="neutral") {
  const safe=["success","info","warning","danger"].includes(tone)?tone:"neutral";
  return element("span",text,"ui-badge ui-badge--"+safe);
 }
 function record({title,meta=[],preview="",iconName="document",onSelect}) {
  const row=element("button","","ui-record note-row"),image=element("span","","ui-record__icon"),body=element("span","","ui-record__body");
  image.append(icon(iconName));body.append(element("strong",title,"ui-record__title"));
  const line=element("span","","ui-record__meta");
  for(const item of meta.filter(Boolean))line.append(typeof item==="string"?element("span",item):item);
  body.append(line);
  if(preview)body.append(element("span",preview,"ui-record__preview"));
  row.append(image,body);if(onSelect)row.addEventListener("click",onSelect);return row;
 }
 function emptyState(heading,description,iconName="document",action) {
  const state=element("div","","ui-empty-state"),image=element("span","","ui-empty-state__icon");
  image.append(icon(iconName));state.append(image,element("h3",heading),element("p",description));
  if(action){const b=element("button",action.label,"ui-button--small");b.addEventListener("click",action.run);state.append(b);}
  return state;
 }
 class PageHeader extends HTMLElement {
  static observedAttributes=["heading","description"];
  connectedCallback(){this.classList.add("ui-page-header");this.render();}
  attributeChangedCallback(){if(this.isConnected)this.render();}
  render(){const copy=element("div");copy.append(element("h1",this.getAttribute("heading") || ""),element("p",this.getAttribute("description") || ""));this.replaceChildren(copy);}
 }
 class EmptyState extends HTMLElement {
  static observedAttributes=["heading","description","icon"];
  connectedCallback(){this.classList.add("ui-empty-state");this.render();}
  attributeChangedCallback(){if(this.isConnected)this.render();}
  render(){const content=emptyState(this.getAttribute("heading") || "표시할 내용이 없습니다",this.getAttribute("description") || "",this.getAttribute("icon") || "document");this.replaceChildren(...content.childNodes);}
 }
 class Badge extends HTMLElement {connectedCallback(){this.classList.add("ui-badge");}}
 for(const [name,type] of [["ui-page-header",PageHeader],["ui-empty-state",EmptyState],["ui-badge",Badge]])if(!customElements.get(name))customElements.define(name,type);
 window.FoundationUI=Object.freeze({element,icon,badge,record,emptyState});
 for(const node of document.querySelectorAll("[data-icon]"))node.prepend(icon(node.dataset.icon));
})();
