"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Activity, ArrowDownToLine, ArrowLeft, ArrowRight, BarChart3, Check, ChevronRight, CircleHelp, ClipboardList, Database, FileText, Home, Inbox, Info, Menu, Package, Search, Settings2, ShieldCheck, Sparkles, X } from "lucide-react";
import { getDashboardData, getProductAnalysis, fixtureMetadata, issueLabel } from "@/lib/analytics/app-service.mjs";
import { P1Panel, P2Panel, TrendChart } from "@/components/analytics-extensions";
import { OperationsProvider, OperationsWorkspace } from "@/components/operations-workspace";
import { resolvePreparedSuggestions } from "@/lib/prepared-suggestions.mjs";
import { analyticsApi } from "@/lib/api/client";
import { useOperations } from "./operations-context";
import { useProductOperations, ProductOperationsSummary, ProductFollowupsPanel } from "./product-operations";

type Row = Record<string, any>;
type Section = "home" | "inquiries" | "followups" | "products" | "settings" | "customer";
type ProductTab = "catalog" | "voc";
type DetailTab = "basic" | "voc" | "followups";
const navItems = [
  {id:"home", label:"운영 홈", icon:Home}, {id:"inquiries",label:"문의",icon:Inbox},
  {id:"followups",label:"후속",icon:ClipboardList}, {id:"products",label:"제품",icon:Package},
  {id:"settings",label:"운영 설정",icon:Settings2},
] as const;
const initialDashboard = getDashboardData("ALL4");
const firstProduct = (data:Row) => data.products[0].product.product_id as string;
const n = (value:number|null|undefined, digits=0) => value == null ? "—" : value.toLocaleString("ko-KR",{minimumFractionDigits:digits,maximumFractionDigits:digits});
const pct = (value:number|null|undefined) => value == null ? "—" : n(value*100,1)+"%";
const stamp = (value:string) => new Intl.DateTimeFormat("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(new Date(value))+" KST";
const day = (value:string) => value?.replaceAll("-",".") ?? "—";
const previousDay = (value:string) => new Date(Date.parse(value+"T00:00:00Z")-86400000).toISOString().slice(0,10);
const statusText = (risk:Row) => risk.data_status !== "ELIGIBLE" ? ({LOW_SAMPLE:"표본 부족",DATA_MISSING:"자료 부족",QUALITY_BLOCKED:"품질 확인"} as Row)[risk.data_status] ?? "산정 제외" : risk.score >=60 ? "집중관리" : risk.score >=40 ? "관찰" : "일반";
const statusClass = (risk:Row) => risk.data_status !== "ELIGIBLE" ? "muted" : risk.score>=60 ? "danger" : risk.score>=40 ? "warning" : "success";
const componentNames:Row = {volume:"불만 건수",rate:"판매비",growth:"증가",repeat:"반복",unresolved:"미해결"};
const metricNames:Row = {C:"최근 7일 불만 사례",P:"직전 7일 불만 사례",S:"최근 28일 판매 주문",N:"판매 코호트 내 불만 주문",M:"최다 주요 유형의 불만 사례",U:"미해결 불만 사례",K:"불만 고객"};
const metricUnits:Row = {C:"건",P:"건",S:"건",N:"건",M:"건",U:"건",K:"명"};
function Badge({children,tone="muted"}:{children:React.ReactNode;tone?:string}) { return <span className={"badge "+tone}>{children}</span>; }
function Download({onClick}:{onClick:()=>void}) { return <button className="btn secondary" onClick={onClick}><ArrowDownToLine size={17}/>분석 결과 저장</button>; }
function saveJson(name:string,value:unknown) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json;charset=utf-8"}));
  const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

function appUrl(){ return new URL(window.location.href); }
export default function InsightDashboard(){
  return <OperationsProvider><ManagerDashboard/></OperationsProvider>;
}
function ManagerDashboard(){
  const { revision: operationsRevision, focusInquiry, focusFollowup } = useOperations();
  const [section,setSection]=useState<Section>("home");
  const [listTab,setListTab]=useState<ProductTab>("voc");
  const [detailTab,setDetailTab]=useState<DetailTab>("voc");
  const [detailOpen,setDetailOpen]=useState(false);
  const [scope,setScope]=useState("ALL4");
  const [batch,setBatch]=useState(fixtureMetadata.batch_id);
  const [selected,setSelected]=useState(firstProduct(initialDashboard));
  const [queries,setQueries]=useState({catalog:"",voc:""});
  const [categories,setCategories]=useState({catalog:"ALL",voc:"ALL"});
  const [routeReady,setRouteReady]=useState(false);
  const [routeError,setRouteError]=useState("");
  const [showExcluded,setShowExcluded]=useState(false);
  const [mobileOpen,setMobileOpen]=useState(false);
  const [notice,setNotice]=useState("");
  const [busy,setBusy]=useState(false);
  const [modelReady,setModelReady]=useState(false);
  const [prepared,setPrepared]=useState<{key:string;value:Row}|null>(null);
  const epoch=useRef(0);
  const modelAbort=useRef<AbortController|null>(null);
  const urlMode=useRef<"push"|"replace">("replace");
  const provenanceDialog=useRef<HTMLDialogElement>(null);
  const helpDialog=useRef<HTMLDialogElement>(null);
  const dashboard:Row=useMemo(()=>getDashboardData(scope),[scope]);
  const analysis:Row=useMemo(()=>getProductAnalysis(scope,selected),[scope,selected]);
  const {product,risk,coverage}=analysis.context;
  const key=[risk.batch_id,scope,selected].join("|");
  const shown=prepared?.key===key?prepared.value:analysis.suggestions;
  const query=queries[listTab], category=categories[listTab];
  const allCategories=[...new Set(dashboard.products.map((r:Row)=>r.product.category))] as string[];
  const eligible=dashboard.products.filter((r:Row)=>r.risk.data_status==="ELIGIBLE");
  const excluded=dashboard.products.filter((r:Row)=>r.risk.data_status!=="ELIGIBLE");
  const top10=eligible.slice(0,10);
  const listBase:Row[]=listTab==="voc"?top10:[...dashboard.products].sort((a:Row,b:Row)=>a.product.sku.localeCompare(b.product.sku));
  const rows=listBase.filter((r:Row)=>(category==="ALL"||r.product.category===category)&&[r.product.name,r.product.sku,r.product.product_id,issueLabel(r.risk.metrics.top_issue)].join(" ").replaceAll(" ","").toLowerCase().includes(query.replaceAll(" ","").toLowerCase()));
  const contextKey=section+"|"+detailOpen+"|"+detailTab+"|"+key;
  const currentOperations=useProductOperations(selected,routeReady&&!routeError&&section==="products"&&detailOpen,operationsRevision);
  const activeNav=navItems.find(item=>item.id===section) ?? {id:"customer",label:"고객 화면",icon:CircleHelp};
  const exclusionsReason=(r:Row)=>[r.metrics.S<30?"판매 30건 미만":null,r.metrics.C<5?"불만 사례 5건 미만":null,r.metrics.K<3?"불만 고객 3명 미만":null].filter(Boolean).join(" · ")||"원본 품질 상태 확인 필요";

  useEffect(()=>{
    function restore(){
      const url=appUrl(), bits=url.pathname.split("/").filter(Boolean);
      const sec=bits[0]==="customer"?"customer":bits[0]==="manager"&&navItems.some(x=>x.id===bits[1])?bits[1] as Section:"home";
      const requestedScope=url.searchParams.get("scope")??"ALL4";
      const validScope=initialDashboard.scopes.some((x:Row)=>x.scope_key===requestedScope);
      const newScope=validScope?requestedScope:"ALL4";
      const data:Row=getDashboardData(newScope);
      const isDetail=sec==="products"&&!!bits[2];
      const requestedProduct=isDetail?decodeURIComponent(bits[2]):url.searchParams.get("selected");
      const validProduct=!requestedProduct||data.products.some((x:Row)=>x.product.product_id===requestedProduct);
      const requestedBatch=url.searchParams.get("batch")??fixtureMetadata.batch_id;
      const tab=url.searchParams.get("tab");
      setRouteError(!validScope?"이 링크의 팀 범위를 확인할 수 없습니다.":!validProduct?"이 범위에서 제품을 찾을 수 없습니다.":requestedBatch!==fixtureMetadata.batch_id?"이 링크의 분석 배치를 확인할 수 없습니다.":"");
      setSection(sec);setScope(newScope);setSelected(validProduct&&requestedProduct?requestedProduct:firstProduct(data));setBatch(requestedBatch);
      setDetailOpen(isDetail&&validProduct);
      setDetailTab(tab==="basic"||tab==="followups"?tab:"voc");
      const nextList=url.searchParams.get("from")==="catalog"||tab==="catalog"?"catalog":"voc";
      setListTab(nextList);
      setQueries(p=>({...p,[nextList]:url.searchParams.get("q")??""}));
      setCategories(p=>({...p,[nextList]:url.searchParams.get("category")??"ALL"}));
      setNotice("");setMobileOpen(false);urlMode.current="replace";setRouteReady(true);
    }
    restore();window.addEventListener("popstate",restore);window.addEventListener("hashchange",restore);
    return ()=>{window.removeEventListener("popstate",restore);window.removeEventListener("hashchange",restore);};
  },[]);
  useEffect(()=>{
    if(!routeReady||routeError)return;
    const params=new URLSearchParams();
    if(section==="products"){
      params.set("tab",detailOpen?detailTab:listTab);params.set("scope",scope);params.set("batch",batch);
      if(detailOpen)params.set("from",listTab);else params.set("selected",selected);
      if(query)params.set("q",query);if(category!=="ALL")params.set("category",category);
    }
    const target=(section==="customer"?"/customer":"/manager/"+section)+(section==="products"&&detailOpen?"/"+selected:"")+(params.size?"?"+params.toString():"");
    const current=appUrl();
    if(current.pathname+current.search!==target)window.history[urlMode.current==="push"?"pushState":"replaceState"]({},"",target);
    urlMode.current="replace";
  },[routeReady,routeError,section,detailOpen,detailTab,listTab,scope,batch,selected,query,category]);
  useEffect(()=>{
    let active=true;const preparedEpoch=++epoch.current;modelAbort.current?.abort();setBusy(false);setPrepared(null);
    if(!routeError&&section==="products"){
      Promise.resolve(resolvePreparedSuggestions(analysis.bundle)).then(value=>{if(active&&preparedEpoch===epoch.current&&value)setPrepared({key,value});});
    }
    return ()=>{active=false;epoch.current+=1;modelAbort.current?.abort();};
  },[key,routeError,section,risk.batch_id,scope,selected]);
  useEffect(()=>{
    const controller=new AbortController();
    analyticsApi.status(controller.signal).then(result=>setModelReady(Boolean(result.live_generation_configured))).catch(()=>setModelReady(false));
    return ()=>controller.abort();
  },[]);
  useEffect(()=>{setNotice("");},[contextKey]);

  function navigate(next:Section){urlMode.current="push";setSection(next);setMobileOpen(false);setRouteError("");setBatch(fixtureMetadata.batch_id);if(next!=="products")setDetailOpen(false);window.scrollTo({top:0,behavior:"instant"});}
  function openProduct(id:string,tab:DetailTab="voc"){urlMode.current="push";setSelected(id);setDetailTab(tab);setDetailOpen(true);setRouteError("");window.scrollTo({top:0,behavior:"instant"});}
  function returnList(){urlMode.current="push";setDetailOpen(false);setRouteError("");setBatch(fixtureMetadata.batch_id);window.scrollTo({top:0,behavior:"instant"});}
  function changeScope(next:string){
    epoch.current+=1;modelAbort.current?.abort();urlMode.current="push";setScope(next);setSelected(firstProduct(getDashboardData(next)));setDetailOpen(false);setPrepared(null);setBusy(false);setShowExcluded(false);setRouteError("");setBatch(fixtureMetadata.batch_id);
  }
  async function generate(){
    if(!modelReady||busy)return;
    const id=++epoch.current;const requestKey=key;const controller=new AbortController();modelAbort.current=controller;setBusy(true);setNotice("");
    try{
      const result=await analyticsApi.generate({scope_key:scope,product_id:selected,batch_id:risk.batch_id},controller.signal);
      if(id!==epoch.current)return;
      if(result.suggestion)setPrepared({key:requestKey,value:result.suggestion});
      setNotice(result.message??"개선 제안을 갱신했습니다.");
    }catch(error){if(id===epoch.current&&!controller.signal.aborted)setNotice(error instanceof Error?error.message:"연결을 확인하지 못했습니다. 기본 제안을 유지합니다.");}
    finally{if(id===epoch.current)setBusy(false);}
  }
  function exportAnalysis(){
    saveJson("CS_Flow_"+product.sku+"_"+scope+".json",{data_origin:"SYNTHETIC",product,batch:analysis.context.batch,risk,evidence:analysis.bundle,suggestion:shown,anomaly:analysis.anomaly});
    setNotice("선택한 제품의 분석 결과를 저장했습니다.");
  }
  function openRelatedTicket(ticketId:string){focusInquiry(ticketId);navigate("inquiries");}
  function openRelatedFollowup(ticketId:string,followupId:string){focusFollowup(ticketId,followupId);navigate("followups");}
  function renderCurrentActions(){
    return <aside className="card current-actions" aria-label="현재 조치와 연결"><ProductOperationsSummary lookup={currentOperations} onOpenFollowups={()=>{urlMode.current="push";setDetailTab("followups");window.scrollTo({top:0,behavior:"instant"});}} onOpenTicket={openRelatedTicket}/><div className="quick-links"><span>이 제품에서 확인</span><button onClick={()=>{setDetailTab("voc");setTimeout(()=>document.getElementById("p1-panel")?.scrollIntoView({behavior:"smooth",block:"start"}),30);}}><Sparkles size={16}/>P1 개선 제안<ArrowRight size={15}/></button><button onClick={()=>{setDetailTab("voc");setTimeout(()=>document.getElementById("p2-panel")?.scrollIntoView({behavior:"smooth",block:"start"}),30);}}><Activity size={16}/>P2 이상 탐지<ArrowRight size={15}/></button></div></aside>;
  }
  function renderScoreEvidence(){
    const parts=Object.entries(risk.components??{}) as [string,Row][];
    const valid=parts.length===5&&parts.every(([,v])=>Number.isFinite(v.contribution)&&Number.isFinite(v.weight)&&Number.isFinite(v.normalized))&&risk.score!=null&&Math.abs(parts.reduce((s,[,v])=>s+v.contribution,0)-risk.score)<0.00001;
    return <section className="card score-evidence"><div className="card-title"><h2>점수 구성과 해석</h2><BarChart3 size={19}/></div>{valid?<><div className="contribution-list">{parts.map(([name,value])=><div key={name}><span>{componentNames[name]??name}</span><div className="contribution-track"><i style={{width:Math.min(100,value.normalized*100)+"%"}}/></div><strong>{n(value.contribution,2)}</strong></div>)}</div><details className="disclosure"><summary>정규화 · 가중치 · 규칙 확인</summary><div className="table-scroll"><table><thead><tr><th>항목</th><th>정규화</th><th>가중치</th><th>기여점수</th></tr></thead><tbody>{parts.map(([name,v])=><tr key={name}><td>{componentNames[name]}</td><td>{n(v.normalized,4)}</td><td>{pct(v.weight)}</td><td>{n(v.contribution,4)}</td></tr>)}</tbody></table></div><p>규칙 {risk.rule_version} · 초기 설정<br/>규칙 해시: 원본에서 미제공<br/>파일 무결성은 데이터 기준의 SHA-256에서 확인합니다.</p></details></>:<div className="compact-empty"><Info size={22}/><p>{risk.score==null?"이 제품은 산정 대상에서 제외되어 점수 구성을 표시하지 않습니다.":"기여점수와 최종 점수를 확인해야 합니다."}</p></div>}</section>;
  }

  return <div className="manager-shell">
    <aside className={"manager-sidebar"+(mobileOpen?" is-open":"")}>
      <a className="manager-brand" href="/manager/products?tab=voc" onClick={e=>{e.preventDefault();navigate("products");returnList();}}><span className="brand-symbol">C</span><strong>CS Flow</strong></a>
      <button className="sidebar-close icon-button" aria-label="메뉴 닫기" onClick={()=>setMobileOpen(false)}><X size={22}/></button>
      <p className="workspace-label">WORKSPACE</p>
      <nav aria-label="주 메뉴">{navItems.map(item=><button key={item.id} className={"manager-nav-item"+(section===item.id?" active":"")} aria-label={item.label} aria-current={section===item.id?"page":undefined} onClick={()=>navigate(item.id)}><item.icon size={21}/><span>{item.label}</span>{item.id==="products"&&<span className="nav-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="workspace-context"><ShieldCheck size={19}/><div><strong>관리자 작업 공간</strong><p>L2 안내 · L3 요청 이관</p></div></div><button className="demo-card" onClick={()=>provenanceDialog.current?.showModal()}><span><i/>DEMO</span><strong>L2 · L3 v2 시연</strong><small>데이터 기준 확인 <ChevronRight size={14}/></small></button><button className="help-link" onClick={()=>helpDialog.current?.showModal()}><CircleHelp size={18}/>사용 안내</button></div>
    </aside>
    {mobileOpen&&<button className="sidebar-backdrop" aria-label="메뉴 바깥 영역 닫기" onClick={()=>setMobileOpen(false)}/>}
    <div className="manager-workspace">
      <header className="manager-topbar"><div className="topbar-left"><button className="icon-button mobile-menu" aria-label="메뉴 열기" onClick={()=>setMobileOpen(!mobileOpen)}><Menu size={23}/></button><div className="breadcrumb"><span>워크스페이스</span><ChevronRight size={15}/><strong>{activeNav.label}</strong>{detailOpen&&section==="products"&&<><ChevronRight size={15}/><span>제품 상세</span></>}</div></div><div className="topbar-right"><span className="environment-label"><span className="v2-version-chip">v2</span> 로컬 API 연결</span><button className="btn secondary customer-switch" onClick={()=>navigate(section==="customer"?"home":"customer")}>{section==="customer"?"관리자 화면":"고객 화면"}</button><span className="manager-role"><span className="role-avatar">M</span><span>E-commerce Manager<small>{section==="customer"?"합성 고객 화면":"로컬 관리자 시연"}</small></span></span></div></header>
      <main className="manager-content" id="main-content">
      {!routeReady?<section className="card loading-state" aria-busy="true">v2 작업 공간을 불러오고 있습니다.</section>:routeError?<section className="card unavailable-state"><Database size={32}/><h1>분석 맥락을 확인해 주세요</h1><p>{routeError}</p><p>다른 제품·팀·배치의 결과로 대신 표시하지 않습니다.</p><button className="btn primary" onClick={()=>{setScope("ALL4");setSelected(firstProduct(initialDashboard));setBatch(fixtureMetadata.batch_id);setRouteError("");setSection("products");returnList();}}>확인된 제품 목록 열기<ArrowRight size={17}/></button></section>:section!=="products"?<OperationsWorkspace section={section} onNavigate={navigate}/>:<>
        <div className="page-title"><div>{detailOpen&&<button className="back-link" onClick={returnList}><ArrowLeft size={16}/>{listTab==="voc"?"VOC TOP 10":"제품 목록"}으로</button>}<div className="eyebrow">PRODUCT WORKSPACE</div><h1>{detailOpen?product.name+(detailTab==="voc"?" VOC 상세":detailTab==="basic"?" 기본 정보":" 후속"):listTab==="voc"?"제품 VOC TOP 10":"제품 목록"}</h1><p>{detailOpen?"근거를 확인하고, 다음 점검으로 이어가세요.":listTab==="voc"?"최근 7일의 불만을 바탕으로 먼저 살펴볼 제품을 확인하세요.":"제품을 검색하고 기본 정보와 VOC 분석을 함께 확인하세요."}</p></div>{detailOpen?<Download onClick={exportAnalysis}/>:<button className="btn secondary" onClick={()=>provenanceDialog.current?.showModal()}><Database size={17}/>데이터 기준</button>}</div>
        {notice&&<div className="notice" role="status"><Check size={18}/><span>{notice}</span><button className="icon-button" aria-label="알림 닫기" onClick={()=>setNotice("")}><X size={17}/></button></div>}
        <div className="snapshot-bar"><div><span className="snapshot-dot"/><strong>로컬 합성 분석</strong><span className="snapshot-time">기준 {stamp(risk.source_as_of)}</span><span className="snapshot-batch">배치 {risk.batch_id.slice(0,8)}</span></div><button onClick={()=>provenanceDialog.current?.showModal()}>원본·시안 차이 <Info size={15}/></button></div>
        <div className="product-toolbar"><div className="tabs" role="tablist" aria-label={detailOpen?"제품 상세 구역":"제품 보기"}>{(detailOpen?[{id:"basic",name:"기본 정보"},{id:"voc",name:"VOC 분석"},{id:"followups",name:"후속"}]:[{id:"catalog",name:"제품 목록"},{id:"voc",name:"VOC TOP 10"}]).map(t=><button key={t.id} role="tab" aria-selected={(detailOpen?detailTab:listTab)===t.id} className={(detailOpen?detailTab:listTab)===t.id?"active":""} onClick={()=>{urlMode.current="push";if(detailOpen)setDetailTab(t.id as DetailTab);else{setListTab(t.id as ProductTab);setShowExcluded(false);}}}>{t.name}</button>)}</div><label className="scope-control"><span>시연 팀 범위</span><select aria-label="시연 팀 범위" value={scope} onChange={e=>changeScope(e.target.value)}>{dashboard.scopes.map((s:Row)=><option key={s.scope_key} value={s.scope_key}>{s.label}</option>)}</select></label></div>
        {(!detailOpen||detailTab==="voc")&&<div className="priority-note"><ShieldCheck size={17}/><span>관리 우선순위이며 제품 결함 확정이 아닙니다.</span><small>최근 7일 · {day(risk.window_end.slice(0,10))}까지의 완료 구간</small></div>}

        {!detailOpen?<><div className="product-grid">
          <section className="card product-list-card"><div className="card-heading"><div><h2>{listTab==="voc"?"최근 7일 TOP 10":"전체 제품"}<span className="count-chip">{listTab==="voc"?Math.min(10,eligible.length):dashboard.stats.products}</span></h2><p>{listTab==="voc"?"원본에 저장된 순위와 점수를 표시합니다.":"상품명, SKU 또는 제품 ID로 검색할 수 있습니다."}</p></div>{listTab==="voc"&&<Badge tone="purple">원본 순위</Badge>}</div>
            <div className="list-filters"><label className="search-control"><Search size={18}/><input aria-label="제품 검색" placeholder="제품명, SKU, ID 또는 주요 이슈 검색" value={query} onChange={e=>setQueries(p=>({...p,[listTab]:e.target.value}))}/>{query&&<button className="icon-button" aria-label="검색 지우기" onClick={()=>setQueries(p=>({...p,[listTab]:""}))}><X size={15}/></button>}</label><select aria-label="제품 카테고리" value={category} onChange={e=>setCategories(p=>({...p,[listTab]:e.target.value}))}><option value="ALL">전체 분류</option>{allCategories.map(c=><option key={c}>{c}</option>)}</select></div>
            <div className="table-scroll risk-table"><table><thead><tr>{listTab==="voc"&&<th className="rank-col">순위</th>}<th>제품</th>{listTab==="voc"?<><th title="최근 7일 불만 사례 수">사례 C</th><th title="판매 코호트 내 불만 주문 N / 판매 주문 S">판매비 R</th><th>주요 이슈</th><th className="align-right">점수</th></>:<><th>카테고리</th><th>활성 상태</th><th>VOC 상태</th></>}</tr></thead><tbody>{rows.map((r:Row)=><tr key={r.product.product_id} className={selected===r.product.product_id?"selected-row":""} onClick={()=>setSelected(r.product.product_id)}>{listTab==="voc"&&<td className="rank-value">{String(r.risk.rank).padStart(2,"0")}</td>}<td><button className="product-select" aria-label={r.product.name+" 선택"} aria-pressed={selected===r.product.product_id} onClick={()=>setSelected(r.product.product_id)}><span className="product-tile"><Package size={17}/></span><span><strong>{r.product.name}</strong><small>{r.product.sku}{listTab==="voc"?" · "+r.product.category:""}</small></span></button></td>{listTab==="voc"?<><td className="numeric">{n(r.risk.metrics.C)}</td><td className="numeric">{pct(r.risk.metrics.raw_rate)}</td><td className="issue-cell">{issueLabel(r.risk.metrics.top_issue)}</td><td className={"score-value align-right "+statusClass(r.risk)}>{n(r.risk.score,2)}</td></>:<><td>{r.product.category}</td><td><Badge tone={r.product.active?"success":"muted"}>{r.product.active?"활성":"비활성"}</Badge></td><td><Badge tone={statusClass(r.risk)}>{statusText(r.risk)}</Badge></td></>}</tr>)}</tbody></table>{!rows.length&&<div className="empty-state"><Search size={28}/><strong>일치하는 제품이 없습니다.</strong><p>{listTab==="voc"?"검색은 현재 TOP 10 안에서 적용됩니다. 전체 제품은 제품 목록에서 확인하세요.":"검색어나 분류를 바꿔 보세요."}</p><button className="text-link" onClick={()=>{setQueries(p=>({...p,[listTab]:""}));setCategories(p=>({...p,[listTab]:"ALL"}));}}>필터 초기화</button></div>}</div>
            <div className="list-summary"><span>{listTab==="voc"?"전체 유효 "+eligible.length+"개 중 TOP "+Math.min(10,eligible.length):"전체 "+dashboard.stats.products+"개"} · 현재 {rows.length}개 표시</span>{listTab==="voc"&&<button className="text-link" onClick={()=>setShowExcluded(!showExcluded)}>산정 제외 {excluded.length}개 {showExcluded?"접기":"보기"}<ChevronRight size={15}/></button>}</div>
          </section>
          <aside className="card selected-product" aria-label="선택 제품 요약"><div className="card-title"><h2>선택 제품</h2><span className="selected-indicator"/></div><div className="selected-product-icon"><Package size={30}/></div><span className="product-category">{product.category} · {product.sku}</span><h3>{product.name}</h3><div className="selected-score">{n(risk.score,2)}<span>{risk.score!=null?"/ 100":""}</span></div><Badge tone={statusClass(risk)}>{statusText(risk)}</Badge><dl className="summary-metrics"><div><dt>원본 순위</dt><dd>{risk.rank==null?"산정 제외":risk.rank+"위"}</dd></div><div><dt>최근 불만 사례</dt><dd>{n(risk.metrics.C)}건</dd></div><div><dt>판매비 N/S</dt><dd>{pct(risk.metrics.raw_rate)}</dd></div><div><dt>주요 이슈</dt><dd>{issueLabel(risk.metrics.top_issue)}</dd></div></dl><button className="btn primary full" onClick={()=>openProduct(selected,listTab==="catalog"?"basic":"voc")}>{listTab==="catalog"?"제품 상세 열기":"상세 근거 · 개선 제안"}<ArrowRight size={17}/></button><p className="selection-footnote">같은 제품·팀 범위·배치를 이어서 확인합니다.</p></aside>
        </div>
        {showExcluded&&listTab==="voc"&&<section className="card excluded-card"><div className="card-heading"><div><h2>산정 제외 제품 <span className="count-chip">{excluded.length}</span></h2><p>표본 부족과 품질 상태는 0점으로 표시하지 않습니다.</p></div><button className="icon-button" aria-label="제외 목록 닫기" onClick={()=>setShowExcluded(false)}><X size={19}/></button></div><div className="table-scroll"><table><thead><tr><th>제품</th><th>상태</th><th>제외 사유</th><th>C / S / K</th><th>확인</th></tr></thead><tbody>{excluded.map((r:Row)=><tr key={r.product.product_id}><td>{r.product.name}</td><td><Badge>{statusText(r.risk)}</Badge></td><td>{exclusionsReason(r.risk)}</td><td>{r.risk.metrics.C} / {r.risk.metrics.S} / {r.risk.metrics.K}</td><td><button className="text-link" onClick={()=>openProduct(r.product.product_id)}>근거 열기<ArrowRight size={14}/></button></td></tr>)}</tbody></table></div></section>}
        <div className="page-hint"><Sparkles size={18}/><p>제품을 선택하고 <strong>상세 근거 · 개선 제안</strong>을 열면 P1 개선 제안과 P2 이상 탐지를 확인할 수 있습니다.</p></div></>:detailTab==="basic"?<div className="detail-layout"><section className="card basic-info"><div className="card-title"><h2>제품 기본 정보</h2><Badge tone={product.active?"success":"muted"}>{product.active?"활성":"비활성"}</Badge></div><div className="basic-product"><span className="selected-product-icon"><Package size={33}/></span><div><span className="product-category">{product.category}</span><h2>{product.name}</h2><p>{product.sku}</p></div></div><dl className="definition-grid"><dt>제품 ID</dt><dd className="mono">{product.product_id}</dd><dt>SKU</dt><dd>{product.sku}</dd><dt>카테고리</dt><dd>{product.category}</dd><dt>데이터 구분</dt><dd>공유 합성 제품</dd></dl><button className="btn primary" onClick={()=>setDetailTab("voc")}>VOC 근거 · 개선 제안 보기<ArrowRight size={16}/></button></section>{renderCurrentActions()}</div>:detailTab==="followups"?<div className="detail-layout"><ProductFollowupsPanel lookup={currentOperations} productName={product.name} onOpenFollowup={openRelatedFollowup} onOpenTicket={openRelatedTicket}/>{renderCurrentActions()}</div>:<div className="detail-layout">
          <div className="detail-main"><div className="evidence-grid"><section className="card raw-evidence"><div className="card-title"><h2>점수와 원시 관측값</h2><Badge tone={statusClass(risk)}>{statusText(risk)}</Badge></div><div className="detail-score">{n(risk.score,2)}<span>{risk.rank==null?"산정 제외":"원본 "+risk.rank+"위"}</span></div><div className="raw-metrics">{Object.keys(metricNames).map(k=><div key={k} title={metricNames[k]}><span>{k}</span><strong>{n(risk.metrics[k])}</strong></div>)}</div><details className="disclosure"><summary>지표의 뜻 · 분모 확인</summary><dl className="metric-definitions">{Object.entries(metricNames).map(([k,v])=><div key={k}><dt>{k}</dt><dd>{String(v)} · {n(risk.metrics[k])}{metricUnits[k]}</dd></div>)}</dl><p>판매비 R = N/S · {pct(risk.metrics.raw_rate)}<br/>보정율 {pct(risk.metrics.smoothed_rate)} · 코호트 외 불만 {n(risk.metrics.outside_cohort)}건<br/>판매 분모는 제품 공통, 불만은 선택한 팀 범위입니다.<br/>초기 표본 기준: S≥30, C≥5, K≥3 및 품질 통과.</p></details></section>{renderScoreEvidence()}</div>
            <section className="card trend-card"><div className="card-heading"><div><h2>{coverage.days}일 불만 사례 추세</h2><p>{day(coverage.start_day)}–{day(previousDay(coverage.end_day_exclusive))} · 확보된 일별 자료</p></div><Badge tone="purple">{scope}</Badge></div><TrendChart points={analysis.daily} label="일별 불만 사례"/><div className="history-coverage-note"><Info size={17}/><p>직전 7일 합계 P는 {n(risk.metrics.P)}건입니다. 해당 기간의 일별 원본은 제공되지 않아 14일 그래프로 확장하지 않았습니다.</p></div><div className="issue-distribution"><h3>주요 불편 유형</h3>{analysis.issues.slice(0,4).map((item:Row)=><div key={item.issue}><span>{issueLabel(item.issue)}</span><div><i style={{width:Math.max(2,item.count/Math.max(1,risk.metrics.C)*100)+"%"}}/></div><strong>{item.count}건</strong></div>)}</div></section>
            <div id="p1-panel" className="extension-anchor"><P1Panel analysis={analysis} suggestion={shown} modelReady={modelReady} busy={busy} onGenerate={generate}/></div>
            <div id="p2-panel" className="extension-anchor"><P2Panel analysis={analysis}/></div>
          </div>{renderCurrentActions()}
        </div>}
      </>}
      <footer className="manager-footer"><span>CS Flow AI · v2 로컬 API · 임시 RAG</span><button onClick={()=>helpDialog.current?.showModal()}><CircleHelp size={15}/>사용 안내</button></footer>
      </main>
    </div>
    <dialog className="manager-dialog" ref={provenanceDialog} aria-labelledby="provenance-title"><div className="dialog-heading"><div><span className="eyebrow">DATA CONTEXT</span><h2 id="provenance-title">데이터와 화면 기준</h2></div><button className="icon-button" aria-label="데이터 기준 닫기" onClick={()=>provenanceDialog.current?.close()}><X size={22}/></button></div><div className="dialog-body"><div className="soft-note"><Info size={19}/><p>새 운영 스토리보드의 화면 구조와, 실제 확보된 공유 원본 데이터를 사용합니다.</p></div><dl className="definition-grid"><dt>화면 기준</dt><dd>E-commerce Manager 운영 스토리보드 v2<br/>UI/UX 상세 스토리보드 v1 · 기존 UI v0.1 비교</dd><dt>분석 원본</dt><dd>11/2 합성운영데이터 및 후속검증<br/>20개 제품 · 15개 팀 조합</dd><dt>기준 시각</dt><dd>{stamp(risk.source_as_of)}</dd><dt>확보 일별 이력</dt><dd>{day(coverage.start_day)}–{day(previousDay(coverage.end_day_exclusive))} · {coverage.days}일</dd><dt>배치 상태</dt><dd>VALIDATED · is_current=false<br/>운영 Fabric 게시 전의 로컬 합성 검증 자료</dd><dt>시안과의 차이</dt><dd>시안은 품질보완 v3의 유효 제품 12개·14일 이력을 사용합니다. 해당 원본을 찾지 못해 현재 확인된 자료의 유효 제품 15개·7일 이력을 유지했습니다.</dd><dt>점수와 해시</dt><dd>점수·순위는 원본을 유지합니다. 입력 파일 4개의 SHA-256이 전달 목록과 일치합니다. 개별 규칙 해시는 원본에서 제공되지 않았습니다.</dd><dt>AI 생성</dt><dd>{modelReady?"실시간 생성 설정 있음. 버튼 실행 결과로 확인합니다.":"실시간 연결 대기. 사전 작성 AI 제안과 규칙 기반 제안을 구분합니다."}</dd><dt>실제 권한</dt><dd>현재 팀 선택은 합성 데이터 탐색용입니다. 상담 API의 관리자·고객 역할도 로컬 시연용이며 팀 서비스의 로그인을 대신하지 않습니다.</dd></dl></div><div className="dialog-footer"><button className="btn primary" onClick={()=>provenanceDialog.current?.close()}>확인</button></div></dialog>
    <dialog className="manager-dialog" ref={helpDialog} aria-labelledby="help-title"><div className="dialog-heading"><div><span className="eyebrow">QUICK GUIDE</span><h2 id="help-title">v2 로컬 워크스페이스 사용법</h2></div><button className="icon-button" aria-label="사용 안내 닫기" onClick={()=>helpDialog.current?.close()}><X size={22}/></button></div><div className="dialog-body"><div className="soft-note"><ShieldCheck size={18}/><p><strong>상담 시연:</strong> 운영 홈에서 사례를 선택하고, 문의에서 자동 처리 또는 사람 인수·승인·답변을 확인합니다. 고객 화면에서는 공개 답변·재문의·사람 연결을 볼 수 있습니다. 처리 결과는 로컬 데이터베이스에 저장되어 새로고침과 서버 재시작 후에도 이어집니다. 초기화는 운영 설정에서 선택합니다.</p></div><h3 style={{marginTop:22,marginBottom:16}}>기존 제품 분석</h3><ol className="guide-steps"><li><strong>제품을 고릅니다.</strong><p>제품 목록에서는 20개 제품을 검색할 수 있습니다. VOC TOP 10은 선택한 팀 범위의 저장 순위입니다.</p></li><li><strong>상세 근거와 P1 제안을 읽습니다.</strong><p>판매비 N/S, 불만 사례와 점수 구성을 먼저 확인하세요. 제안의 ‘사전 작성 AI’ 또는 ‘규칙 기반’ 표시를 함께 봅니다.</p></li><li><strong>P2 탐지를 확인합니다.</strong><p>원본은 필요한 28일 이력이 부족합니다. ‘검증 시나리오’에서는 하루 급증과 지속 증가 등 8개 상황을 직접 바꿔 볼 수 있습니다.</p></li><li><strong>분석 결과를 저장합니다.</strong><p>제품·배치·근거·제안·탐지 결과를 JSON으로 받습니다. 고객 개인정보는 포함하지 않습니다.</p></li></ol><div className="soft-note"><ShieldCheck size={18}/><p>고객 화면에서 직접 문장을 입력하면 임시 정책을 검색하고, 허용되는 안내는 자동으로 완료합니다. 운영 설정의 임시 RAG 작업 공간에서 문서와 조항을 확인할 수 있습니다. 실제 팀 인증과 고객 발송은 팀 API 연결 후 검증합니다.</p></div></div><div className="dialog-footer"><button className="btn primary" onClick={()=>helpDialog.current?.close()}>시작하기</button></div></dialog>
  </div>;
}
