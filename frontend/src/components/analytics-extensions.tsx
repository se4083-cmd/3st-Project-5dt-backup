"use client";

import { useEffect, useId, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Activity, ArrowDownToLine, Check, CheckCircle2, ChevronDown, CircleHelp, FlaskConical, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react";
import { runScenario, scenarioOptions, statusLabel } from "@/lib/analytics/app-service.mjs";
import { DETECTOR_PARAMETERS } from "@/lib/analytics/detector.mjs";
import "./analytics-extensions.css";

type AnyRecord = Record<string, any>;
export type TrendPoint = {
  day: string;
  episode_count: number | null;
  expected_count?: number | null;
  phase?: string;
  signals?: string[];
  source_state?: string;
};

const formatNumber = (value: number | null | undefined, digits = 0) => value == null || !Number.isFinite(value) ? "—" : value.toLocaleString("ko-KR", { maximumFractionDigits: digits });
const shortDay = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${Number(value.slice(5, 7))}.${Number(value.slice(8, 10))}` : value;
const phaseLabel = (phase?: string) => (({ context: "이전 참고", baseline: "비교 기준", monitor: "최근 관찰" } as Record<string, string>)[phase ?? ""] ?? "—");
const signalLabel = (type: string) => (({ POINT_SPIKE: "하루 급증", SUSTAINED_INCREASE: "지속 증가", NEW_ACTIVITY: "신규 발생" } as Record<string, string>)[type] ?? type);

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`ext-badge ext-badge-${tone}`}>{children}</span>;
}

function downloadJson(filename: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Plot source values without filling missing dates or computing an alternative score. */
export function TrendChart({ points, label, large = false }: { points: TrendPoint[]; label: string; large?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const gradientId = `voc-area-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const titleId = `${gradientId}-title`;
  const width = 780, height = large ? 280 : 220, left = 48, right = 24, top = 24, bottom = 38;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const roof = Math.ceil(Math.max(5, ...points.map(p => p.episode_count ?? 0), ...points.map(p => p.expected_count ?? 0)) / 5) * 5;
  const x = (index: number) => left + index * plotWidth / Math.max(1, points.length - 1);
  const y = (value: number) => top + plotHeight * (1 - value / roof);
  const pathFor = (key: "episode_count" | "expected_count") => {
    let pen = false;
    return points.map((point, index) => {
      const value = point[key];
      if (value == null || !Number.isFinite(value)) { pen = false; return ""; }
      const result = `${pen ? "L" : "M"}${x(index)},${y(value)}`;
      pen = true;
      return result;
    }).join(" ");
  };
  const dateIndices = points.length <= 7
    ? points.map((_, index) => index)
    : [...new Set(Array.from({ length: 6 }, (_, index) => Math.round(index * (points.length - 1) / 5)))];
  const monitorStart = points.findIndex(point => point.phase === "monitor");
  const hasExpected = points.some(point => point.expected_count != null);
  const active = hover == null ? null : points[hover];

  return <div className="voc-trend">
    <div className="voc-trend-caption">
      <strong>{label}</strong>
      <span>{active ? `${active.day} · ${active.episode_count == null ? "수집 누락" : `${formatNumber(active.episode_count)}건`}` : "단위: 불만 사례 · KST"}</span>
    </div>
    {points.length ? <div className="voc-chart-scroll"><svg className={`voc-chart ${large ? "voc-chart-large" : ""}`} viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={titleId} onMouseLeave={() => setHover(null)}>
      <title id={titleId}>{label}. {points.length}일의 원본 수치를 표시합니다. 일별 수치 표에서 누락 여부와 값을 확인할 수 있습니다.</title>
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5844E8" stopOpacity=".14"/><stop offset="100%" stopColor="#5844E8" stopOpacity=".015"/></linearGradient></defs>
      {large && hasExpected && monitorStart >= 0 && <rect x={x(monitorStart) - 6} y={top - 8} width={width - right - x(monitorStart) + 6} height={plotHeight + 16} rx="7" fill="#f4f0ff"/>}
      {[0, 1, 2, 3, 4].map(step => <g key={step}><line x1={left} x2={width - right} y1={y(roof * step / 4)} y2={y(roof * step / 4)} stroke="#e7e5ef" strokeDasharray={step ? "3 5" : "0"}/><text x={left - 12} y={y(roof * step / 4) + 5} textAnchor="end" fill="#706b83" fontSize="16">{formatNumber(roof * step / 4, 1)}</text></g>)}
      {points.every(point => point.episode_count != null) && <path d={`${pathFor("episode_count")} L${x(points.length - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={`url(#${gradientId})`}/>}
      {hasExpected && <path d={pathFor("expected_count")} fill="none" stroke="#8d879f" strokeWidth="2" strokeDasharray="6 5"/>}
      <path d={pathFor("episode_count")} fill="none" stroke="#5844E8" strokeWidth="3" strokeLinejoin="round" strokeLinecap="round"/>
      {points.map((point, index) => <g key={point.day}>
        {point.episode_count != null && (points.length <= 14 || Boolean(point.signals?.length) || index === hover) && <circle cx={x(index)} cy={y(point.episode_count)} r={point.signals?.length ? 5.5 : 3.5} fill={point.signals?.length ? "#c55f18" : "#5844E8"} stroke="white" strokeWidth="2"/>}
        <rect x={x(index) - plotWidth / Math.max(1, points.length - 1) / 2} y={top} width={Math.max(12, plotWidth / Math.max(1, points.length - 1))} height={plotHeight} fill="transparent" onMouseEnter={() => setHover(index)}/>
      </g>)}
      {hover != null && active?.episode_count != null && <line x1={x(hover)} x2={x(hover)} y1={top} y2={height - bottom} stroke="#5844E8" opacity=".3"/>}
      {dateIndices.map(index => <text key={index} x={x(index)} y={height - 12} textAnchor="middle" fill="#706b83" fontSize="16">{shortDay(points[index].day)}</text>)}
    </svg></div> : <p className="ext-empty">표시할 일별 수치가 없습니다. 수집 범위를 확인해 주세요.</p>}
    {hasExpected && <div className="voc-chart-legend"><span><i className="voc-line"/>관측 건수</span><span><i className="voc-line voc-line-dashed"/>같은 요일 기준</span>{large && <span><i className="voc-area"/>최근 관찰 구간</span>}</div>}
    <details className="ext-details voc-values"><summary>일별 수치 표 <ChevronDown size={16}/></summary><div className="ext-table-scroll" tabIndex={0} role="region" aria-label={`${label} 일별 수치`}><table>
      <caption className="ext-sr-only">{label} · 누락은 0건과 구분합니다.</caption>
      <thead><tr><th scope="col">일자</th><th scope="col">불만 사례</th>{hasExpected && <th scope="col">같은 요일 기준</th>}<th scope="col">수집 상태</th>{large && <th scope="col">구간</th>}</tr></thead>
      <tbody>{points.map(point => <tr key={point.day}><th scope="row">{point.day}</th><td>{point.episode_count == null ? "—" : `${formatNumber(point.episode_count)}건`}</td>{hasExpected && <td>{point.expected_count == null ? "—" : `${formatNumber(point.expected_count, 1)}건`}</td>}<td>{point.episode_count == null ? "수집 누락" : point.source_state === "confirmed_zero" ? "0건 확인" : "수집됨"}</td>{large && <td>{phaseLabel(point.phase)}</td>}</tr>)}</tbody>
    </table></div></details>
  </div>;
}

function EvidenceList({ items }: { items: AnyRecord[] }) {
  return <ul className="ext-evidence-list">{items.map((item, index) => <li key={item.id ?? index}>
    <span className="ext-evidence-label">{item.label ?? item.id}</span>
    <span>{item.text ?? `${formatNumber(item.value, 2)} ${item.unit ?? ""}`}</span>
    {item.period && <small>{item.period}</small>}
  </li>)}</ul>;
}

export function P1Panel({ analysis, suggestion = null, modelReady = false, busy = false, onGenerate }: {
  analysis: AnyRecord;
  suggestion?: AnyRecord | null;
  modelReady?: boolean;
  busy?: boolean;
  onGenerate?: () => void;
}) {
  const headingId = useId();
  const shown = suggestion ?? analysis.suggestions ?? {};
  const observations: AnyRecord[] = analysis.bundle?.observations ?? [];
  const isPrepared = shown.mode === "CHATGPT_PREPARED";
  const isLive = shown.mode === "GENERATED" || shown.mode === "GENERATIVE";
  const modeLabel = isPrepared ? "사전 작성 AI" : isLive ? "실시간 AI" : "규칙 기반";
  const description = isPrepared ? "현재 근거에 맞춰 사전 작성하고 검증한 제안입니다." : isLive ? "연결된 모델이 현재 근거로 생성한 제안입니다." : "확인된 집계에 따라 제안하는 기본 점검입니다.";
  const [downloaded, setDownloaded] = useState(false);
  const context = analysis.bundle?.context ?? analysis.context?.risk ?? {};
  useEffect(() => { setDownloaded(false); }, [analysis.bundle?.evidence_bundle_id]);

  return <section className="ext-panel ext-p1" aria-labelledby={headingId}>
    <div className="ext-heading"><div className="ext-heading-copy"><span className="ext-icon"><Sparkles size={21}/></span><div><div className="ext-kicker">P1 · 개선 제안</div><h3 id={headingId}>다음으로 확인할 점검</h3></div></div><Badge tone={isPrepared || isLive ? "purple" : "neutral"}>{modeLabel}</Badge></div>
    <p className="ext-description">{description}</p>
    {shown.summary && <p className="ext-summary">{shown.summary}</p>}
    <div className="ext-action-list">{(shown.actions ?? []).map((action: AnyRecord, index: number) => {
      const ids: string[] = action.evidence_ids ?? [];
      const evidence: AnyRecord[] = ids.map(id => observations.find(item => item.id === id) ?? action.evidence?.find((item: AnyRecord) => item.id === id)).filter((item): item is AnyRecord => Boolean(item));
      return <article className="ext-action" key={action.id ?? action.action_key ?? index}><span className="ext-action-number">{String(index + 1).padStart(2, "0")}</span><div className="ext-action-body">
        <h4>{action.title}</h4><p>{action.description}</p>
        {action.checks?.length > 0 && <ul className="ext-checks">{action.checks.map((check: string, checkIndex: number) => <li key={checkIndex}><Check size={16}/><span>{check}</span></li>)}</ul>}
        {evidence.length > 0 && <details className="ext-details ext-action-evidence"><summary>이 제안의 근거 {evidence.length}개 <ChevronDown size={16}/></summary><EvidenceList items={evidence}/></details>}
      </div></article>;
    })}</div>
    {!(shown.actions?.length) && <p className="ext-empty">현재 근거로 표시할 점검 제안이 없습니다. 집계 상태를 확인해 주세요.</p>}
    {shown.additional_information?.length > 0 && <details className="ext-details ext-additional"><summary>함께 확인할 자료 <ChevronDown size={16}/></summary><ul>{shown.additional_information.map((item: string, index: number) => <li key={index}>{item}</li>)}</ul></details>}
    <details className="ext-details ext-provenance"><summary>근거와 생성 정보 <ChevronDown size={16}/></summary><dl>
      <dt>작성 방식</dt><dd>{modeLabel}{isPrepared && " · 실시간 API 호출 아님"}</dd>
      {shown.period && <><dt>관찰 기간</dt><dd>{shown.period}</dd></>}
      <dt>팀 범위</dt><dd>{context.scope_key ?? "—"}</dd>
      <dt>배치</dt><dd className="ext-mono">{context.batch_id ?? "—"}</dd>
      {shown.provenance?.model_label && <><dt>작성 정보</dt><dd>{shown.provenance.model_label}</dd></>}
      {shown.provenance?.prepared_date && <><dt>작성일</dt><dd>{shown.provenance.prepared_date}</dd></>}
      {(shown.model_version || shown.model) && <><dt>모델</dt><dd>{shown.model_version ?? shown.model}</dd></>}
      {(shown.prompt_version || shown.provenance?.prompt_version) && <><dt>프롬프트</dt><dd>{shown.prompt_version ?? shown.provenance.prompt_version}</dd></>}
      <dt>근거 묶음</dt><dd className="ext-mono">{shown.evidence_bundle_id ?? analysis.bundle?.evidence_bundle_id ?? "—"}</dd>
      {shown.input_sha256 && <><dt>입력 SHA-256</dt><dd className="ext-mono">{shown.input_sha256}</dd></>}
    </dl></details>
    <div className="ext-footer"><span className="ext-review-note"><ShieldCheck size={17}/>실행 전 담당자가 검토합니다.</span><div className="ext-footer-actions">
      <button type="button" className="ext-button ext-button-secondary" onClick={() => { downloadJson(`csflow-p1-${analysis.context?.product?.sku ?? "product"}-${context.scope_key ?? "scope"}.json`, { data_origin: "SYNTHETIC", evidence: analysis.bundle, suggestion: shown }); setDownloaded(true); }}><ArrowDownToLine size={16}/>제안 저장</button>
      {modelReady && onGenerate ? <button type="button" className="ext-button ext-button-primary" onClick={onGenerate} disabled={busy}><Sparkles size={16}/>{busy ? "생성 중…" : "AI 제안 새로 생성"}</button> : <span className="ext-connection-state">실시간 생성 연결 대기</span>}
    </div></div>
    {downloaded && <p className="ext-inline-status" role="status">현재 제안과 근거를 JSON으로 저장했습니다.</p>}
  </section>;
}

function SignalList({ signals }: { signals: AnyRecord[] }) {
  if (!signals.length) return null;
  return <div className="ext-signals">{signals.map((signal, index) => <article key={`${signal.type}-${signal.start_day ?? index}`}><strong>{signal.label ?? signalLabel(signal.type)}</strong><p>{signal.message ?? signal.description}</p>{signal.start_day && <span>{signal.start_day}{signal.end_day && signal.end_day !== signal.start_day ? ` – ${signal.end_day}` : ""}</span>}</article>)}</div>;
}

export function P2Panel({ analysis }: { analysis: AnyRecord }) {
  const headingId = useId();
  const result: AnyRecord = analysis.anomaly ?? {};
  const evidence: AnyRecord = result.evidence ?? {};
  const parameters: AnyRecord = result.parameters ?? DETECTOR_PARAMETERS;
  const baselineDays = evidence.baseline_days ?? parameters.baseline_days;
  const monitorDays = evidence.monitor_days ?? parameters.monitor_days;
  const requiredDays = evidence.required_history_days ?? baselineDays + monitorDays;
  const coverageDays = evidence.coverage_days ?? analysis.context?.coverage?.days;
  const blocked = !result.status || ["INSUFFICIENT_HISTORY", "INCOMPLETE_DATA", "DATA_BLOCKED", "INVALID_INPUT", "LOW_BASELINE"].includes(result.status);
  const tone = result.status === "ALERT" || result.status === "WATCH" ? "amber" : result.status === "NORMAL" ? "green" : "neutral";
  return <section className="ext-panel ext-p2" aria-labelledby={headingId}>
    <div className="ext-heading"><div className="ext-heading-copy"><span className="ext-icon"><Activity size={21}/></span><div><div className="ext-kicker">P2 · 이상 탐지</div><h3 id={headingId}>평소와 다른 불만 흐름</h3></div></div><Badge tone={tone}>{result.status ? statusLabel(result.status) : "분석 대기"}</Badge></div>
    <p className="ext-description">같은 요일의 평소 수준과 비교해 하루 급증과 지속 증가를 구분합니다.</p>
    <div className={`ext-detection-summary ${blocked ? "ext-detection-held" : ""}`}>
      {blocked ? <CircleHelp size={21}/> : result.status === "NORMAL" ? <CheckCircle2 size={21}/> : <TriangleAlert size={21}/>}<p>{result.summary || "조회할 수 있는 일별 이력과 데이터 상태를 확인해 주세요."}</p>
    </div>
    <div className="ext-history-metrics"><div><span>확인된 일별 이력</span><strong>{formatNumber(coverageDays)}<small>일</small></strong></div><div><span>탐지에 필요한 이력</span><strong>{formatNumber(requiredDays)}<small>일</small></strong></div><div className="ext-history-rule"><span>비교 기준</span><strong>기준 {baselineDays}일 + 관찰 {monitorDays}일</strong></div></div>
    <SignalList signals={result.signals ?? []}/>
    <p className="ext-footnote">이 결과는 점검할 신호이며 제품 결함이나 원인을 확정하지 않습니다. 원본 점수와 순위는 유지됩니다.</p>
    <details className="ext-lab-disclosure"><summary><span><FlaskConical size={18}/>별도 검증 시나리오로 탐지 확인</span><ChevronDown size={18}/></summary><AnomalyLab/></details>
  </section>;
}

export function AnomalyLab({ initialScenario = "spike" }: { initialScenario?: string } = {}) {
  const options: AnyRecord[] = useMemo(() => scenarioOptions(), []);
  const [scenario, setScenario] = useState(options.some(option => option.id === initialScenario) ? initialScenario : "spike");
  const [downloaded, setDownloaded] = useState(false);
  const selectId = useId();
  const headingId = useId();
  const result: AnyRecord = useMemo(() => runScenario(scenario), [scenario]);
  const selected = options.find(option => option.id === scenario) ?? {};
  const evidence = result.evidence ?? {};
  const points: TrendPoint[] = result.daily_series ?? [];
  const tone = result.status === "ALERT" || result.status === "WATCH" ? "amber" : result.status === "NORMAL" ? "green" : "neutral";

  return <section className="ext-lab" aria-labelledby={headingId}>
    <div className="ext-lab-intro"><div><h4 id={headingId}>탐지 시나리오 {options.length}가지</h4><p>원본 제품 이력과 별도로 만든 합성 데이터입니다. 상황을 바꾸면 같은 탐지 코드가 결과를 계산합니다.</p></div><Badge tone="purple">검증용 합성 데이터</Badge></div>
    <div className="ext-scenario-control"><label htmlFor={selectId}>확인할 상황</label><select id={selectId} value={scenario} onChange={event => { setScenario(event.target.value); setDownloaded(false); }}>{options.map(option => <option value={option.id} key={option.id}>{option.name ?? option.title}</option>)}</select><button type="button" className="ext-button ext-button-secondary" onClick={() => { downloadJson(`csflow-p2-${scenario}.json`, { data_origin: "SYNTHETIC_DETECTOR_SCENARIO", scenario: selected, result }); setDownloaded(true); }}><ArrowDownToLine size={16}/>결과 저장</button></div>
    <p className="ext-scenario-description">{scenario === "short" ? "필요한 이력보다 짧은 7일을 별도로 구성해 판단 보류를 확인합니다." : selected.description}</p>
    <div className="ext-lab-result" aria-live="polite"><div className="ext-lab-result-heading"><Badge tone={tone}>{statusLabel(result.status)}</Badge><span>{evidence.coverage_start} – {points.at(-1)?.day ?? "—"} · {formatNumber(evidence.coverage_days)}일</span></div><p>{result.summary}</p></div>
    <TrendChart points={points} label={selected.name ?? selected.title ?? "일별 불만 사례"} large/>
    <div className="ext-lab-metrics"><div><span>기준 기간 합계</span><strong>{formatNumber(evidence.baseline_total)}<small>{evidence.baseline_total == null ? "" : "건"}</small></strong><small>관찰 직전 {evidence.baseline_days ?? DETECTOR_PARAMETERS.baseline_days}일</small></div><div><span>관찰 기간 합계</span><strong>{formatNumber(evidence.monitor_total)}<small>{evidence.monitor_total == null ? "" : "건"}</small></strong><small>최근 {evidence.monitor_days ?? DETECTOR_PARAMETERS.monitor_days}일</small></div><div><span>확인된 신호</span><strong>{formatNumber(result.signals?.length ?? 0)}<small>개</small></strong><small>{result.status === "NORMAL" ? "현재 기준의 평소 범위" : ["ALERT", "WATCH"].includes(result.status) ? "추가 점검 필요" : "판정 보류 상태"}</small></div></div>
    <SignalList signals={result.signals ?? []}/>
    <details className="ext-details ext-method"><summary>탐지 기준과 해석 <ChevronDown size={16}/></summary><ul><li>직전 {DETECTOR_PARAMETERS.baseline_days / 7}주의 같은 요일을 기준으로 평소 수준을 비교합니다.</li><li>하루 급증과 여러 날 이어진 증가를 분리하고, 누적 변화는 CUSUM 방식으로 확인합니다.</li><li>수집 누락·이력 부족·적은 표본을 구분하고, 판단이 어려우면 결과를 보류합니다.</li><li>임계값은 합성 검증을 위한 초기 설정입니다. 실제 운영 정확도와 오경보율은 추가 검증이 필요합니다.</li></ul></details>
    {downloaded && <p className="ext-inline-status" role="status">선택한 시나리오의 탐지 결과를 JSON으로 저장했습니다.</p>}
  </section>;
}
