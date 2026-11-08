/// <reference types="vitest/globals" />
import { describe, it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useAsyncAction } from "@/hooks/use-async-action";

describe("useAsyncAction", () => {
  it("ignores a second call while the first is still in flight", async () => {
    let resolveFirst: () => void = () => undefined;
    const action = vi.fn(
      () => new Promise<void>((resolve) => {
        resolveFirst = resolve;
      }),
    );
    const { result } = renderHook(() => useAsyncAction(action));

    let first: Promise<unknown> | undefined;
    act(() => {
      first = result.current.run();
    });
    expect(result.current.isPending).toBe(true);

    let second: unknown;
    await act(async () => {
      second = await result.current.run();
    });
    expect(action).toHaveBeenCalledOnce();
    expect(second).toBeUndefined();

    await act(async () => {
      resolveFirst();
      await first;
    });
    expect(result.current.isPending).toBe(false);
  });

  it("clears pending and rethrows when the action fails", async () => {
    const action = vi.fn(async () => {
      throw new Error("boom");
    });
    const { result } = renderHook(() => useAsyncAction(action));

    await act(async () => {
      await expect(result.current.run()).rejects.toThrow("boom");
    });
    expect(result.current.isPending).toBe(false);
  });

  it("returns the action result on success", async () => {
    const { result } = renderHook(() => useAsyncAction(async (value: number) => value * 2));

    let output: number | undefined;
    await act(async () => {
      output = await result.current.run(21);
    });
    expect(output).toBe(42);
  });
});
