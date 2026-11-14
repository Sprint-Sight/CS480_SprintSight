/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { BlindLabelForm } from "@/features/insights/components/blind-label-form";
import { DIMENSION_LABELS, DIMENSIONS, MAX_REASON } from "@/features/insights/types";

const renderForm = (onSave = vi.fn()) =>
  render(<BlindLabelForm initial={[]} locked={false} saving={false} onSave={onSave} />);

describe("BlindLabelForm", () => {
  it("blocks submit until all six dimensions have a score", () => {
    const onSave = vi.fn();
    renderForm(onSave);
    const submit = screen.getByRole("button", { name: /submit and reveal/i });
    expect(submit).toBeDisabled();
    DIMENSIONS.slice(0, 5).forEach((d) =>
      fireEvent.change(screen.getByLabelText(`${DIMENSION_LABELS[d]} score`), {
        target: { value: "7" },
      }),
    );
    expect(submit).toBeDisabled();
    expect(screen.getByText("5 of 6 scored")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(`${DIMENSION_LABELS[DIMENSIONS[5]]} score`), {
      target: { value: "4" },
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toHaveLength(6);
    expect(onSave.mock.calls[0][1]).toBe(true);
  });

  it("limits each reason to 1000 characters and shows a counter", () => {
    renderForm();
    const reason = screen.getByLabelText("Requirements reason");
    expect(reason).toHaveAttribute("maxLength", String(MAX_REASON));
    fireEvent.change(reason, { target: { value: "abc" } });
    expect(screen.getByText(`3/${MAX_REASON}`)).toBeInTheDocument();
  });

  it("disables every field when the labels are locked", () => {
    render(<BlindLabelForm initial={[]} locked saving={false} onSave={vi.fn()} />);
    expect(screen.getByLabelText("Requirements score")).toBeDisabled();
    expect(
      screen.getByText("These labels are locked because the AI results were revealed."),
    ).toBeInTheDocument();
  });
});
