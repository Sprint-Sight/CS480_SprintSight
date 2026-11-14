/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DegradedNotice, RevealComparison } from "@/features/insights/components/reveal-panels";
import type { RevealDimension } from "@/features/insights/types";

const dimensions: RevealDimension[] = [
  {
    dimension: "requirements",
    label: "Requirements",
    aiScore: 7,
    aiScoreCurrent: 5,
    overridden: true,
    yourScore: 5,
    yourReason: null,
    diff: -2,
    within1: null,
  },
  {
    dimension: "testing",
    label: "Testing",
    aiScore: 6,
    aiScoreCurrent: 6,
    overridden: false,
    yourScore: 6,
    yourReason: null,
    diff: 0,
    within1: null,
  },
];

describe("RevealComparison", () => {
  it("override mode has no within-1 column, so it cannot be read as AI accuracy", () => {
    render(<RevealComparison dimensions={dimensions} mode="override" />);
    expect(screen.getByText("Instructor override")).toBeInTheDocument();
    expect(screen.getByText("Adjustment")).toBeInTheDocument();
    expect(screen.queryByText("Within 1 point")).not.toBeInTheDocument();
    expect(screen.getByText("changed")).toBeInTheDocument(); // only requirements changed
    expect(screen.getByText("-2")).toBeInTheDocument();
  });

  it("blind mode keeps the within-1 column", () => {
    render(
      <RevealComparison
        mode="blind_label"
        dimensions={[{ ...dimensions[1], yourScore: 7, diff: 1, within1: true }]}
      />,
    );
    expect(screen.getByText("Within 1 point")).toBeInTheDocument();
    expect(screen.getByText(/Yes/)).toBeInTheDocument();
  });
});

describe("DegradedNotice", () => {
  it("renders the MLflow-unreachable notice", () => {
    render(<DegradedNotice notice="MLflow is unreachable right now." />);
    expect(screen.getByRole("status")).toHaveTextContent("MLflow is unreachable right now.");
  });

  it("renders nothing without a notice", () => {
    const { container } = render(<DegradedNotice notice={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
