/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { PageSkeleton } from "@/components/ui/page-skeleton";

describe("PageSkeleton", () => {
  it("announces a polite loading status to screen readers", () => {
    renderComponent(<PageSkeleton />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading…");
  });

  it("renders the table variant rows inside the status region", () => {
    const { container } = renderComponent(<PageSkeleton variant="table" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(container.querySelectorAll("[aria-hidden='true']").length).toBeGreaterThanOrEqual(6);
  });
});
