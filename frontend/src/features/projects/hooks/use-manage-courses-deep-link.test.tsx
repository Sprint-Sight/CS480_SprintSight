/// <reference types="vitest/globals" />
import { renderHook } from "@testing-library/react";
import { StrictMode, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

import { useManageCoursesDeepLink } from "@/features/projects/hooks/use-manage-courses-deep-link";

function setUrl(search: string) {
  window.history.replaceState({}, "", `/projects${search}`);
}

describe("useManageCoursesDeepLink", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setUrl("");
  });

  it("opens course management once and removes the param when it is set", () => {
    setUrl("?manageCourses=1");
    const onOpen = vi.fn();

    renderHook(() => useManageCoursesDeepLink(onOpen));

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith("/projects");
  });

  it("does nothing when the param is absent", () => {
    const onOpen = vi.fn();

    renderHook(() => useManageCoursesDeepLink(onOpen));

    expect(onOpen).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it("does not reopen the modal on the strict-mode double effect run", () => {
    setUrl("?manageCourses=1");
    const onOpen = vi.fn();
    const strictWrapper = ({ children }: { children: ReactNode }) => <StrictMode>{children}</StrictMode>;

    renderHook(() => useManageCoursesDeepLink(onOpen), { wrapper: strictWrapper });

    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledTimes(1);
  });
});
