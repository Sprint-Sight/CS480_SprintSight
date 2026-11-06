/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

function renderDialog(props: { onOpenChange: (open: boolean) => void; dismissOnOutsideClick?: boolean }) {
  return renderComponent(
    <Dialog open onOpenChange={props.onOpenChange}>
      <DialogContent dismissOnOutsideClick={props.dismissOnOutsideClick}>
        <DialogTitle>Edit project</DialogTitle>
        <DialogDescription>Update the project details.</DialogDescription>
        <button type="button">Save</button>
      </DialogContent>
    </Dialog>
  );
}

describe("Dialog - UI Component", () => {
  it("renders a labelled modal dialog", () => {
    renderDialog({ onOpenChange: vi.fn() });

    const dialog = screen.getByRole("dialog", { name: "Edit project" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveClass("overflow-y-auto");
  });

  it("closes on Escape", () => {
    const onOpenChange = vi.fn();
    renderDialog({ onOpenChange });

    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("keeps focus inside the dialog", () => {
    renderDialog({ onOpenChange: vi.fn() });

    const dialog = screen.getByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});
