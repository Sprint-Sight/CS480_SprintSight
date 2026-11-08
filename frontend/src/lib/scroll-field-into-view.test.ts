/// <reference types="vitest/globals" />
import { describe, it, expect, vi } from "vitest";
import type { FocusEvent } from "react";
import { scrollFieldIntoView } from "@/lib/scroll-field-into-view";

function focusEventFor(target: HTMLElement) {
  return { target } as unknown as FocusEvent<HTMLElement>;
}

describe("scrollFieldIntoView", () => {
  it("scrolls a focused text input into view", () => {
    const input = document.createElement("input");
    const scrollIntoView = vi.fn();
    input.scrollIntoView = scrollIntoView;

    scrollFieldIntoView(focusEventFor(input));

    expect(scrollIntoView).toHaveBeenCalledWith({ block: "center" });
  });

  it("ignores focus on non-field elements", () => {
    const button = document.createElement("button");
    const scrollIntoView = vi.fn();
    button.scrollIntoView = scrollIntoView;

    scrollFieldIntoView(focusEventFor(button));

    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
