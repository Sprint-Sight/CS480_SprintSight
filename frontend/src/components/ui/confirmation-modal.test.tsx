/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { ConfirmationModal } from "@/components/ui/confirmation-modal";

describe("ConfirmationModal - UI Component", () => {
  const mockOnClose = vi.fn();
  const mockOnConfirm = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("should not render when isOpen is false", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={false}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Test Title"
        message="Test message"
      />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("should render dialog when isOpen is true", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={true}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Test Title"
        message="Test message"
      />
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Test Title")).toBeInTheDocument();
    expect(screen.getByText("Test message")).toBeInTheDocument();
  });

  it("should use custom button text when provided", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={true}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Title"
        message="Message"
        confirmText="Delete"
        cancelText="Keep"
      />
    );
    expect(screen.getByText("Delete")).toBeInTheDocument();
    expect(screen.getByText("Keep")).toBeInTheDocument();
  });

  it("should call onClose when cancel button is clicked", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={true}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Title"
        message="Message"
        cancelText="Cancel"
      />
    );
    const cancelButton = screen.getByText("Cancel");
    fireEvent.click(cancelButton);
    expect(mockOnClose).toHaveBeenCalledOnce();
    expect(mockOnConfirm).not.toHaveBeenCalled();
  });

  it("should call onConfirm when confirm button is clicked", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={true}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Title"
        message="Message"
        confirmText="Confirm"
      />
    );
    const confirmButton = screen.getByText("Confirm");
    fireEvent.click(confirmButton);
    expect(mockOnConfirm).toHaveBeenCalledOnce();
    expect(mockOnClose).not.toHaveBeenCalled();
  });

  it("should have proper aria attributes for accessibility", () => {
    renderComponent(
      <ConfirmationModal
        isOpen={true}
        onClose={mockOnClose}
        onConfirm={mockOnConfirm}
        title="Title"
        message="Message"
      />
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });
});
