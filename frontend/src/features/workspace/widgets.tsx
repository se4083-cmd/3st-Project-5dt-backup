import { useEffect, useMemo, useRef, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { useAuthManager } from "../../auth/AuthProvider";
import { AsyncState, Badge } from "../../components";
import { mutations, type Intent, type Mutations } from "./mutations";
import "./workspace.css";
export function useWrites() { const auth = useAuthManager(), store = useMemo(() => mutations(auth), [auth]); return { store, entries: useSyncExternalStore(store.subscribe, store.getSnapshot) }; }
export function useWriteRefresh(entry: Intent | undefined, refresh: () => void) {
  const handled = useRef("");
  useEffect(() => { if (entry && ["done", "conflict"].includes(entry.phase) && handled.current !== `${entry.key}:${entry.phase}`) { handled.current = `${entry.key}:${entry.phase}`; refresh(); } }, [entry, refresh]);
}
export function WriteResult({ entry, store, slot, reset }: { entry?: Intent; store: Mutations; slot: string; reset?: () => void }) {
  if (!entry) return null;
  if (entry.phase === "sending") return <p className="notice" role="status">요청 처리 중입니다. 중복 제출하지 마세요.</p>;
  if (entry.phase === "done") return <div className="notice" role="status"><p>요청 이력이 저장되었습니다. {entry.saved?.replayed ? "같은 멱등키의 기존 응답입니다." : "저장 당시 응답입니다."} 최신 상태는 상세 조회로 확인하세요.</p>{entry.saved?.status && <Badge>{entry.saved.status}</Badge>}{entry.saved?.reason && <p>사유 코드: {entry.saved.reason}</p>} <Link to={entry.saved!.href}>저장 결과 상세 보기</Link>{entry.saved?.requestId && <p className="small">요청 ID: {entry.saved.requestId}</p>}{reset && <button className="button secondary" onClick={reset}>새 요청 작성</button>}</div>;
  return <div>{entry.phase === "conflict" ? <p role="alert" className="notice">409 충돌 · {entry.error?.code}. 최신 상태를 다시 조회합니다. 자동 재제출하지 않습니다.</p> : <><AsyncState kind="error" error={entry.error} /><p className="notice">결과가 확정되지 않았을 수 있습니다. 동일 요청 재시도는 원래 본문과 같은 멱등키를 사용합니다.</p><button className="button secondary" onClick={() => void store.retry(slot)}>동일 요청 재시도</button></>}{entry.phase === "conflict" && entry.error?.traceId && <p className="small">추적 ID: {entry.error.traceId}</p>}{reset && <details><summary>최신 이력 확인 후 다른 요청 작성</summary><p>기존 요청의 저장 여부를 확인하세요. 새 요청은 새 키로 별도 이력을 만들 수 있습니다.</p><button className="button secondary" onClick={reset}>최신 상태로 다시 작성</button></details>}</div>;
}
