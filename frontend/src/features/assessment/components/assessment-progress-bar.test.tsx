/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { AssessmentProgressBar } from "@/features/assessment/components/assessment-progress-bar";

describe("AssessmentProgressBar", () => {
  it("is exposed as a progressbar with its current value", () => {
    renderComponent(<AssessmentProgressBar message="Analyzing commits" progress={42} />);
    const bar = screen.getByRole("progressbar", { name: "Assessment progress" });
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
    expect(bar).toHaveAttribute("aria-valuenow", "42");
    expect(bar).toHaveAttribute("aria-valuetext", "42%");
  });

  it("announces the status message politely", () => {
    renderComponent(<AssessmentProgressBar message="Analyzing commits" progress={42} />);
    expect(screen.getByText("Analyzing commits")).toHaveAttribute("aria-live", "polite");
  });

  it("rounds and clamps the value to the 0–100 range", () => {
    const { unmount } = renderComponent(<AssessmentProgressBar message="Working" progress={42.6} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "43");
    unmount();

    renderComponent(<AssessmentProgressBar message="Working" progress={140} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});
