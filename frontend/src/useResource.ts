import { useEffect, useState } from "react";
import { ApiError } from "./api";

export type Resource<T> =
  | { key: string; status: "loading" }
  | { key: string; status: "ready"; data: T }
  | { key: string; status: "error"; error: ApiError };
export function useResource<T>(
  key: string,
  load: (signal: AbortSignal) => Promise<T>,
): Resource<T> {
  const [state, setState] = useState<Resource<T>>({ key, status: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setState({ key, status: "loading" });
    load(controller.signal)
      .then((data) => {
        if (current && !controller.signal.aborted)
          setState({ key, status: "ready", data });
      })
      .catch((error) => {
        if (current && !controller.signal.aborted)
          setState({
            key,
            status: "error",
            error:
              error instanceof ApiError
                ? error
                : new ApiError(0, "NETWORK_ERROR"),
          });
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [key, load]);
  // Old protected data must disappear during render, before effect cleanup runs.
  return state.key === key ? state : { key, status: "loading" };
}
