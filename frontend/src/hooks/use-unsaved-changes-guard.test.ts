import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

import { useUnsavedChangesGuard } from "@/hooks/use-unsaved-changes-guard";

const MESSAGE = "You have unsaved changes. Leave this page without saving?";

function dispatchBeforeUnload() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event;
}

function clickAnchor(href: string, init: MouseEventInit = {}) {
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.textContent = "link";
  document.body.appendChild(anchor);
  const event = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...init });
  anchor.dispatchEvent(event);
  anchor.remove();
  return event;
}

describe("useUnsavedChangesGuard", () => {
  beforeEach(() => {
    push.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("does not prompt on unload when nothing is unsaved", () => {
    renderHook(() => useUnsavedChangesGuard(false, MESSAGE));

    expect(dispatchBeforeUnload().defaultPrevented).toBe(false);
  });

  it("prompts on unload when there are unsaved changes", () => {
    renderHook(() => useUnsavedChangesGuard(true, MESSAGE));

    expect(dispatchBeforeUnload().defaultPrevented).toBe(true);
  });

  it("shows the caller-supplied message before in-app navigation", () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderHook(() => useUnsavedChangesGuard(true, MESSAGE));

    const event = clickAnchor("/projects?course=1#top");

    expect(event.defaultPrevented).toBe(true);
    expect(window.confirm).toHaveBeenCalledWith(MESSAGE);
    expect(push).toHaveBeenCalledWith("/projects?course=1#top");
  });

  it("stays on the page when the user cancels leaving", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderHook(() => useUnsavedChangesGuard(true, MESSAGE));

    const event = clickAnchor("/projects");

    expect(event.defaultPrevented).toBe(true);
    expect(push).not.toHaveBeenCalled();
  });

  it("ignores clicks when nothing is unsaved", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderHook(() => useUnsavedChangesGuard(false, MESSAGE));

    const event = clickAnchor("/projects");

    expect(event.defaultPrevented).toBe(false);
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it("lets modified clicks and external links through", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderHook(() => useUnsavedChangesGuard(true, MESSAGE));

    expect(clickAnchor("/projects", { ctrlKey: true }).defaultPrevented).toBe(false);
    expect(clickAnchor("https://example.com/docs").defaultPrevented).toBe(false);
    expect(window.confirm).not.toHaveBeenCalled();
  });
});
