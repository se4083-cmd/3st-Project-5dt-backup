import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, operationsApi, requestId } from "@/lib/api/client";
import type { DemoRole, JsonObject } from "@/lib/api/client";

type Data = JsonObject;
type UiNotice = { kind: "error" | "success"; message: string; code?: string; scope: "staff" | "customer" };
type Pending = { kind: "action" | "rag"; body: Data; role: DemoRole };
type InquiryFocus = { ticketId: string };
type FollowupFocus = { ticketId: string; followupId?: string };

type OperationsContextValue = {
  state: Data;
  runtime: Data;
  revision: number;
  loaded: boolean;
  loading: boolean;
  busy: boolean;
  error: string;
  notice: UiNotice | null;
  clearNotice: () => void;
  uncertain: boolean;
  retryPending: () => Promise<Data>;
  selectedId: string;
  setSelectedId: (id: string) => void;
  inquiryFocus: InquiryFocus | null;
  focusInquiry: (id: string) => void;
  clearInquiryFocus: () => void;
  followupFocus: FollowupFocus | null;
  focusFollowup: (ticketId: string, followupId?: string) => void;
  clearFollowupFocus: () => void;
  customerId: string;
  setCustomerId: (id: string) => void;
  customerTickets: Data[];
  customerLoaded: boolean;
  refresh: (signal?: AbortSignal) => Promise<Data | null>;
  refreshCustomer: (signal?: AbortSignal) => Promise<Data | null>;
  act: (action: Data) => Promise<Data>;
  actCustomer: (action: Data) => Promise<Data>;
  createScenario: (scenarioId: string, run?: boolean) => Promise<Data>;
  createRagInquiry: (query: string, orderId?: string) => Promise<Data>;
};

const emptyState = { tickets: [], events: [], automation: { enabled: false } };
const OperationsContext = createContext<OperationsContextValue | null>(null);

function describeError(error: unknown) {
  return error instanceof Error ? error.message : "요청을 확인하지 못했습니다.";
}

/** State is a server snapshot, never a browser-owned copy of the workflow engine. */
export function OperationsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<Data>(emptyState);
  const stateRef = useRef<Data>(emptyState);
  const revisionRef = useRef(0);
  const customerRevision = useRef(0);
  const [revision, setRevision] = useState(0);
  const [runtime, setRuntime] = useState<Data>({});
  const [loaded, setLoaded] = useState(false);
  const loadedRef = useRef(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState<UiNotice | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const pending = useRef<Pending | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [inquiryFocus, setInquiryFocus] = useState<InquiryFocus | null>(null);
  const [followupFocus, setFollowupFocus] = useState<FollowupFocus | null>(null);
  const [customerId, setCustomerId] = useState("");
  const [customerTickets, setCustomerTickets] = useState<Data[]>([]);
  const [customerLoaded, setCustomerLoaded] = useState(false);

  const receiveState = useCallback((result: Data) => {
    if (!result.state || !Array.isArray(result.state.tickets) || !Number.isInteger(result.revision)) {
      throw new ApiError("서버 상태 형식을 확인하지 못했습니다.", "INVALID_STATE_RESPONSE");
    }
    if (result.revision < revisionRef.current) return;
    stateRef.current = result.state;
    revisionRef.current = result.revision;
    setState(result.state);
    setRevision(result.revision);
    if (result.runtime) setRuntime(result.runtime);
    setSelectedId(previous => result.state.tickets.some((ticket: Data) => ticket.id === previous)
      ? previous : result.state.tickets.find((ticket: Data) => ticket.status !== "RESOLVED")?.id ?? result.state.tickets[0]?.id ?? "");
    loadedRef.current = true;
    setLoaded(true);
    setError("");
  }, []);

  const receiveCustomer = useCallback((result: Data) => {
    if (!Array.isArray(result.tickets) || !Number.isInteger(result.revision)) {
      throw new ApiError("고객 문의 응답 형식을 확인하지 못했습니다.", "INVALID_CUSTOMER_RESPONSE");
    }
    if (result.revision < customerRevision.current) return;
    setCustomerTickets(result.tickets);
    customerRevision.current = result.revision;
    setCustomerLoaded(true);
    setCustomerId(previous => result.ticket?.id ?? (result.tickets.some((ticket: Data) => ticket.id === previous) ? previous : result.tickets[0]?.id ?? ""));
  }, []);

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!loadedRef.current) setLoading(true);
    try {
      const result = await operationsApi.state(signal);
      if (signal?.aborted) return null;
      receiveState(result);
      return result;
    } catch (cause) {
      if (signal?.aborted) return null;
      setError(describeError(cause));
      return null;
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [receiveState]);

  const refreshCustomer = useCallback(async (signal?: AbortSignal) => {
    try {
      const result = await operationsApi.customerTickets(signal);
      if (signal?.aborted) return null;
      receiveCustomer(result);
      return result;
    } catch (cause) {
      if (!signal?.aborted) setNotice({ kind: "error", message: describeError(cause), scope: "customer" });
      return null;
    }
  }, [receiveCustomer]);

  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);

  const execute = useCallback(async (command: Pending): Promise<Data> => {
    if (busyRef.current) return { notice: { kind: "error", message: "앞선 요청을 처리하고 있습니다." } };
    busyRef.current = true;
    setBusy(true);
    const scope: UiNotice["scope"] = command.role === "customer" ? "customer" : "staff";
    setNotice(null);
    pending.current = command;
    try {
      const result = command.kind === "action"
        ? await operationsApi.act(command.body, command.role)
        : await operationsApi.rag(command.body, command.role);
      if (command.role === "customer") receiveCustomer(result);
      else receiveState(result);
      pending.current = null;
      setUncertain(false);
      const serverNotice = command.role === "customer" ? result.notice : result.state?.notice;
      setNotice({
        kind: serverNotice?.kind === "error" ? "error" : "success",
        message: serverNotice?.message ?? (result.replayed ? "이미 처리된 요청의 결과를 확인했습니다." : "처리 결과를 저장했습니다."),
        scope,
      });
      return result;
    } catch (cause) {
      const apiError = cause instanceof ApiError ? cause : null;
      const unknownResult = !apiError || apiError.status === 0;
      if (!unknownResult) pending.current = null;
      setUncertain(unknownResult);
      const message = apiError?.status === 409
        ? `${describeError(cause)} 최신 상태를 불러왔습니다. 내용을 확인하고 다시 진행해 주세요.`
        : describeError(cause);
      const failure = { kind: "error" as const, message, code: apiError?.code, scope };
      setNotice(failure);
      if (apiError?.status === 409) {
        if (command.role === "customer") await refreshCustomer();
        else await refresh();
      }
      return { error: { code: apiError?.code ?? "UNKNOWN_ERROR", message }, notice: failure };
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }, [receiveState, receiveCustomer, refresh, refreshCustomer]);

  const mutate = useCallback(async (kind: "action" | "rag", body: Data, role: DemoRole = "admin") => {
    if (pending.current) {
      return { notice: { kind: "error", message: "앞선 요청의 처리 결과를 먼저 확인해 주세요." } };
    }
    return execute({
      kind, role,
      body: { ...body, expectedStateRevision: role === "customer" ? customerRevision.current : revisionRef.current, requestId: requestId() },
    });
  }, [execute]);

  const act = useCallback(async (action: Data) => {
    const result = await mutate("action", { action });
    return result.state ?? { ...stateRef.current, notice: result.notice };
  }, [mutate]);

  const actCustomer = useCallback((action: Data) => mutate("action", { action }, "customer"), [mutate]);

  const createRagInquiry = useCallback((query: string, orderId?: string) => mutate("rag", {
    query, createTicket: true, ...(orderId ? { orderId } : {}),
  }, "customer"), [mutate]);

  const createScenario = useCallback(async (scenarioId: string, run = true) => {
    let next = await act({ type: "CREATE_CASE", scenarioId });
    if (next.notice?.kind === "error") return next;
    const ticket = next.tickets?.find((item: Data) => item.id === next.lastCreatedTicketId);
    if (ticket) {
      setSelectedId(ticket.id);
      setCustomerId(ticket.id);
      if (run && ticket.route === "AUTO" && !ticket.humanRequested) {
        next = await act({ type: "RUN_AUTO", ticketId: ticket.id, expectedCycle: ticket.cycle, expectedVersion: ticket.version });
      }
    }
    return next;
  }, [act]);

  const retryPending = useCallback(async () => {
    if (!pending.current) return {};
    return execute(pending.current);
  }, [execute]);

  const clearNotice = useCallback(() => setNotice(null), []);
  const focusInquiry = useCallback((ticketId: string) => {
    setSelectedId(ticketId);
    setInquiryFocus({ ticketId });
  }, []);
  const clearInquiryFocus = useCallback(() => setInquiryFocus(null), []);
  const focusFollowup = useCallback((ticketId: string, followupId?: string) => {
    setSelectedId(ticketId);
    setFollowupFocus({ ticketId, ...(followupId ? { followupId } : {}) });
  }, []);
  const clearFollowupFocus = useCallback(() => setFollowupFocus(null), []);
  const value = useMemo(() => ({
    state, runtime, revision, loaded, loading, busy, error, notice, clearNotice, uncertain, retryPending,
    selectedId, setSelectedId, inquiryFocus, focusInquiry, clearInquiryFocus, followupFocus, focusFollowup, clearFollowupFocus,
    customerId, setCustomerId, customerTickets, customerLoaded,
    refresh, refreshCustomer, act, actCustomer, createScenario, createRagInquiry,
  }), [state, runtime, revision, loaded, loading, busy, error, notice, clearNotice, uncertain, retryPending,
    selectedId, inquiryFocus, focusInquiry, clearInquiryFocus, followupFocus, focusFollowup, clearFollowupFocus,
    customerId, customerTickets, customerLoaded, refresh, refreshCustomer, act, actCustomer, createScenario, createRagInquiry]);

  return <OperationsContext.Provider value={value}>{children}</OperationsContext.Provider>;
}

export function useOperations() {
  const context = useContext(OperationsContext);
  if (!context) throw new Error("OperationsProvider is required");
  return context;
}
