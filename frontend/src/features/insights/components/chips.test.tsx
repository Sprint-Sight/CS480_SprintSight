/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SyncChip } from "@/features/insights/components/chips";

describe("SyncChip", () => {
  it.each([
    ["synced", "Synced"], ["pending", "Pending"], ["failed", "Failed"],
    ["no_trace", "No trace"], ["not_needed", "No changes"],
  ] as const)("shows %s as %s", (status, label) => {
    render(<SyncChip status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("shows a dash when nothing was saved", () => {
    render(<SyncChip status={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});