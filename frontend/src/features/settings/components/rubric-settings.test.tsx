import { describe, it, expect, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderComponent } from "@/test-utils";
import { RubricSettings } from "@/features/settings/components/rubric-settings";
import type { RubricWeight } from "@/features/settings/types";

const rubric: RubricWeight[] = [
  { id: "correctness", label: "Correctness", value: 60 },
  { id: "documentation", label: "Documentation", value: 40 },
] as RubricWeight[];

function renderRubric(overrides: Partial<React.ComponentProps<typeof RubricSettings>> = {}) {
  const props: React.ComponentProps<typeof RubricSettings> = {
    rubric,
    totalWeight: 100,
    isValidTotal: true,
    hasUnsavedChanges: false,
    courses: [],
    selectedCourseId: "",
    isDisabled: false,
    isLoading: false,
    error: "",
    onCourseChange: vi.fn(),
    onChange: vi.fn(),
    ...overrides,
  };
  renderComponent(<RubricSettings {...props} />);
  return props;
}

describe("RubricSettings", () => {
  it("pairs each slider with a labelled number input", () => {
    renderRubric();

    const slider = screen.getByLabelText("Correctness");
    expect(slider).toHaveAttribute("type", "range");
    const numberInput = screen.getByLabelText("Correctness weight (percent)");
    expect(numberInput).toHaveAttribute("type", "number");
    expect(numberInput).toHaveValue(60);
  });

  it("reports number input changes as numeric weights", () => {
    const props = renderRubric();

    fireEvent.change(screen.getByLabelText("Documentation weight (percent)"), { target: { value: "25" } });

    expect(props.onChange).toHaveBeenCalledWith("documentation", 25);
  });

  it("shows an inline alert when the total is not 100%", () => {
    renderRubric({ totalWeight: 90, isValidTotal: false, hasUnsavedChanges: true });

    expect(screen.getByRole("alert")).toHaveTextContent("must add up to 100%");
  });

  it("shows no alert when the total is 100%", () => {
    renderRubric();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
