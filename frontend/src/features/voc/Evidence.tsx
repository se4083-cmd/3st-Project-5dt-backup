import { Badge, DataTimestamp } from "../../components";
import type { VOC } from "./contracts";
const shown = (v: number | string | null) => v === null ? "미제공" : v;
const percent = (v: number | null) => v === null ? "미제공" : `${(v * 100).toLocaleString("ko-KR", { maximumFractionDigits: 4 })}%`;
function Facts({ rows }: { rows: [string, string | number][] }) { return <dl className="p1-facts">{rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>; }
export function Evidence({ data }: { data: VOC }) {
  const { meta: m, facts: f } = data.evidence;
  return <section className="card" aria-label="VOC 생성 근거"><h2>생성 당시 근거·분석 기간</h2><p className="notice">생성 당시 고정한 근거입니다. 현재 게시 상태를 보증하지 않습니다. 위험도는 관리 우선순위이며 확정 결함률이나 개선 효과가 아닙니다.</p>
    {m ? <><p><Badge>{m.source}</Badge> <Badge tone={m.stale ? "amber" : "neutral"}>{m.stale ? "생성 당시 오래된 데이터" : "생성 당시 최신성 기준 충족"}</Badge></p><p className="small">출처는 서비스 선언입니다. Fabric 연결은 UNVERIFIED이며 독립 검증하지 않았습니다.</p><p className="p1-id">배치 UUID: {m.batch_id}</p><p><DataTimestamp value={m.source_as_of} label="원천 기준" /> · <DataTimestamp value={m.generated_at} label="분석 생성" /> · <DataTimestamp value={m.published_at} label="게시" /></p>
      <dl className="p1-facts">{Object.entries(m.windows).map(([key, value]) => <div key={key}><dt>{({ history_start: "이력 시작", operational_start: "운영 기간 시작", sales_start: "판매 기간 시작", prior_start: "이전 기간 시작", recent_start: "최근 기간 시작", window_end: "기간 종료" } as Record<string, string>)[key]}</dt><dd><DataTimestamp value={value} label="" /></dd></div>)}</dl></> : <p>분석 기간·출처가 제공되지 않았습니다.</p>}
    {f ? <><h3>위험도 · risk</h3><Facts rows={[["위험도 점수", shown(f.risk.score)], ["위험 구간", shown(f.risk.risk_band)], ["데이터 상태", f.risk.data_status], ["산정 규칙", f.risk.rule_version]]} />
      <h3>불만 집중도 · repeat</h3><Facts rows={[["최근 VOC 에피소드 (C)", f.repeat.C], ["최대 주 이슈 에피소드 (M)", f.repeat.M], ["고유 고객 (K)", f.repeat.K], ["상위 이슈", shown(f.repeat.top_issue)], ["서버 M/C 집중도", percent(f.repeat.issue_concentration)]]} /><p className="small">동일 고객의 반복 접촉 횟수로 해석하지 않습니다.</p>
      <h3>판매 코호트 불만 주문 비율 · rate</h3><Facts rows={[["코호트 내 불만 주문 (N)", f.rate.N], ["전역 상품 유료 주문 28일 (S)", f.rate.S], ["서버 N/S", percent(f.rate.cohort_inquiry_ratio)], ["게시 raw_rate", percent(f.rate.raw_rate)], ["게시 smoothed_rate", percent(f.rate.smoothed_rate)]]} /><p className="small">전체 문의 대비 비율이나 팀별 주문 분모가 아닙니다. 서버 비율을 다시 산정하지 않습니다.</p>
      <h3>기간 추세 · trend</h3><Facts rows={[["최근 에피소드", f.trend.recent_count], ["이전 에피소드", f.trend.prior_count], ["게시 growth (비율 값)", shown(f.trend.growth)]]} /><p className="small">누락 날짜를 0으로 채우거나 중복 가능 행을 합산하지 않습니다.</p><div className="table-scroll" role="region" aria-label="VOC 날짜별 근거" tabIndex={0}><table><caption className="sr-only">서버 제공 날짜·이슈별 추세</caption><thead><tr><th scope="col">날짜</th><th scope="col">주 이슈</th><th scope="col">에피소드</th><th scope="col">미해결</th></tr></thead><tbody>{f.trend.daily.map((d, i) => <tr key={i}><td>{d.day}</td><td>{d.primary_issue}</td><td>{d.episode_count}</td><td>{d.unresolved_count}</td></tr>)}</tbody></table></div></> : <p>위험도·집중도·문의 비율·추세 근거가 제공되지 않았습니다.</p>}
    <p className="small p1-id">저장 근거 해시: {data.evidence_hash} · 브라우저 원천 검증을 뜻하지 않습니다.</p>
  </section>;
}
