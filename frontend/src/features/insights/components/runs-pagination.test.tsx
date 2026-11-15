/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RunsPagination } from "@/features/insights/components/runs-pagination";

describe("RunsPagination", () => {
  it("renders nothing for a single page", () => {
    const { container } = render(<RunsPagination page={1} pages={1} onPageChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("disables Previous on the first page and Next on the last", () => {
    const { rerender } = render(<RunsPagination page={1} pages={3} onPageChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled();

    rerender(<RunsPagination page={3} pages={3} onPageChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("asks for the neighbouring page", () => {
    const onPageChange = vi.fn();
    render(<RunsPagination page={2} pages={3} onPageChange={onPageChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPageChange.mock.calls).toEqual([[1], [3]]);
  });
});
