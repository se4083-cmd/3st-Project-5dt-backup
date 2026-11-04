import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { AuthManager } from "./store";

const Context = createContext<AuthManager | null>(null);
export function AuthProvider({ children, manager }: { children: ReactNode; manager?: AuthManager }) {
  const [auth] = useState(() => manager ?? new AuthManager());
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "hidden" && ["ready", "blocked"].includes(auth.getSnapshot().phase)) void auth.refresh();
    };
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    const timer = setInterval(() => { if (auth.getSnapshot().phase === "ready") refresh(); }, 60_000);
    return () => {
      clearInterval(timer); window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh); auth.dispose();
    };
  }, [auth]);
  return <Context.Provider value={auth}>{children}</Context.Provider>;
}
export function useAuthManager() {
  const auth = useContext(Context);
  if (!auth) throw new Error("AuthProvider required");
  return auth;
}
export function useAuth() {
  const auth = useAuthManager();
  return useSyncExternalStore(auth.subscribe, auth.getSnapshot, auth.getSnapshot);
}
