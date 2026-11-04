import { act, renderHook } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useResource } from "../useResource";

it("clears prior scope data immediately and ignores a late old response even if the transport ignores abort", async () => {
  let finishOld!: (s: string) => void, finishNew!: (s: string) => void;
  let oldSignal!: AbortSignal;
  const oldLoad = vi.fn((signal: AbortSignal) => {
    oldSignal = signal;
    return new Promise<string>((resolve) => {
      finishOld = resolve;
    });
  });
  const newLoad = vi.fn(
    () =>
      new Promise<string>((resolve) => {
        finishNew = resolve;
      }),
  );
  const { result, rerender } = renderHook(
    ({ id, load }) => useResource(id, load),
    { initialProps: { id: "user-a:ALL4", load: oldLoad } },
  );
  rerender({ id: "user-b:DELIVERY", load: newLoad });
  expect(oldSignal.aborted).toBe(true);
  await act(async () => {
    finishOld("private old scope");
  });
  expect(result.current).toMatchObject({
    key: "user-b:DELIVERY",
    status: "loading",
  });
  expect(result.current).not.toHaveProperty("data");
  await act(async () => {
    finishNew("delivery only");
  });
  expect(result.current).toMatchObject({
    key: "user-b:DELIVERY",
    status: "ready",
    data: "delivery only",
  });
});

it("removes a successful result while refreshing and aborts on unmount", async () => {
  let signal!: AbortSignal;
  const load = vi.fn((s: AbortSignal) => {
    signal = s;
    return Promise.resolve("old result");
  });
  const next = vi.fn((s: AbortSignal) => {
    signal = s;
    return new Promise<string>(() => {});
  });
  const { result, rerender, unmount } = renderHook(
    ({ id, loader }) => useResource(id, loader),
    { initialProps: { id: "one", loader: load } },
  );
  await act(async () => {});
  expect(result.current.status).toBe("ready");
  rerender({ id: "two", loader: next });
  expect(result.current).not.toHaveProperty("data");
  unmount();
  expect(signal.aborted).toBe(true);
});
