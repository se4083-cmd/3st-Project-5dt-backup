import { Badge, DataTimestamp } from "../../components";
import type { Comparison } from "./contracts";
export function Activation() { return <p className="notice"><strong>운영 활성화 미지원 · activation=NOT_SUPPORTED</strong><br />승인은 P1 검토 상태만 변경합니다. 운영 정책 적용·RAG 인덱스 갱신·Azure AI Search 반영은 제공하지 않습니다.</p>; }
export function Diff({ data }: { data: Comparison["diff"] }) {
  return <section className="card" aria-label="줄 단위 diff"><h2>버전 비교 · {data.kind}</h2><p>제목: {data.title_before ?? "기준 버전 없음"} → {data.title_after}</p><p className="notice">줄 번호·범위는 0 기반·끝 제외 [시작, 끝)입니다. 텍스트 차이가 의미적·법적 영향의 확정은 아닙니다.</p>
    {data.changes.length ? data.changes.map((c, i) => <article key={i}><h3>{c.operation}</h3><div className="policy-diff-grid">{([
      ["이전", c.old_start, c.old_end, c.before, "before"], ["이후", c.new_start, c.new_end, c.after, "after"],
    ] as const).map(([label, start, end, rows, side]) => <section className={`policy-diff-${side}`} key={label} aria-label={`${label} 범위 [${start}, ${end})`}><h4>{label} [{start}, {end})</h4>{rows.length ? rows.map((row, j) => <div className="policy-diff-line" key={j}><span aria-label={`${label} 줄 ${start + j}`}>{start + j}</span><pre>{row}</pre></div>) : <p>빈 구간</p>}</section>)}</div></article>) : <p role="status">본문의 줄 변경이 없습니다.</p>}
    <p className="small p1-id">이전 hash: {data.from_hash ?? "기준 없음"}</p><p className="small p1-id">이후 hash: {data.to_hash}</p>
  </section>;
}
function Domain({ title, data }: { title: string; data: Comparison["impact"]["faq"] }) {
  return <article className="policy-domain"><h3>{title}</h3><Badge tone={data.status === "RECORDED_LINKS" ? "purple" : "amber"}>{data.status === "RECORDED_LINKS" ? "과거 연결 기록 확인 · RECORDED_LINKS" : "영향 미확인 · UNCONFIRMED"}</Badge><p>이 분석의 과거 참조: {data.observed_reference_count}건</p><p>실제 영향 건수: 미확인 · 향후 실행 영향: UNCONFIRMED</p><p className="small">사유 코드: {data.reason}</p>
    {data.links.length ? <details><summary>{title} 과거 참조 보기</summary><p className="notice">기록된 인용·정확한 규칙 버전의 동시 사용입니다. 직접 조건 의존성이나 미래의 확정적인 영향이 아닙니다.</p><div className="table-scroll" role="region" aria-label={`${title} 과거 참조`} tabIndex={0}><table><caption className="sr-only">분석 당시 로컬 과거 참조</caption><thead><tr><th scope="col">제안 / 문서</th><th scope="col">관계 / 분류</th><th scope="col">분석 당시 상태·출처</th><th scope="col">규칙 동시 사용</th></tr></thead><tbody>{data.links.map((l, i) => <tr key={i}><td className="p1-id">{l.suggestion_id}<small>문서 {l.document_id} · v{l.document_version}</small></td><td>{l.relation}<small>{l.category}</small></td><td>문서 {l.source_active_at_analysis ? "활성" : "비활성"}<small>제안 {l.origin} / 문서 {l.document_origin}</small></td><td className="p1-id">{l.rule_id ? <>{l.rule_id}<small>v{l.rule_version} · {l.rule_active ? "활성" : "비활성"} · {l.rule_origin}</small></> : "규칙 미제공"}</td></tr>)}</tbody></table></div></details> : <p className="notice">확인된 과거 연결이 없다는 뜻이며 실제 영향 0건을 뜻하지 않습니다.</p>}
  </article>;
}
export function Impact({ data, teams }: { data: Comparison["impact"]; teams: string[] }) {
  return <section className="card" aria-label="정책 영향 분석"><h2>영향 분석</h2><DataTimestamp value={data.as_of} label="분석 기준" /><p className="p1-id">정책 전체 팀 UUID: {teams.join(", ")}</p><p className="notice">범위: SCOPED_LOCAL_RECORDED_SUGGESTIONS. 허용 팀의 로컬 제안 기록을 최대1000개 스캔합니다. 과거 참조를 미래의 확정적 영향으로 해석하지 않습니다.</p>
    <Badge tone={data.source_validation === "VERIFIED_SNAPSHOT" ? "purple" : "amber"}>{data.source_validation}</Badge><p className="small">분석 당시 로컬 출처 대조: {data.source_reason}. 외부 RAG 검증이 아닙니다.</p><p>스캔 기록: {data.scanned_count}개 · {data.truncated ? "1000개 초과 기록 제외·분석 범위 제한 있음" : "서버 응답에 스캔 잘림 없음"}</p>
    <Domain title="FAQ" data={data.faq} /><Domain title="상담 자동응답" data={data.auto_replies} /><Domain title="자동화 규칙" data={data.automation_rules} />
    <h3>연결 관계 미확인 · UNCONFIRMED</h3><ul>{["FAQ 카탈로그 전체", "규칙 조건의 정책 의존성", "Backend B 런타임", "RAG 인덱스", "Azure AI Search"].map(s => <li key={s}>{s}: UNCONFIRMED</li>)}</ul><p className="small">영역별 참조는 겹칠 수 있어 합산하지 않습니다. 외부 연결이나 인덱스 갱신을 수행하지 않습니다.</p>
  </section>;
}
