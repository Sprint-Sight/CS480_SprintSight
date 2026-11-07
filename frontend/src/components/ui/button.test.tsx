/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { Button } from "@/components/ui/button";

describe("Button", () => {
  it("renders the danger variant with its color class", () => {
    renderComponent(<Button variant="danger">Delete</Button>);
    expect(screen.getByRole("button", { name: "Delete" })).toHaveClass("bg-red-600");
  });

  it("defaults to type=button so it never submits a surrounding form", () => {
    renderComponent(<Button>Open</Button>);
    expect(screen.getByRole("button", { name: "Open" })).toHaveAttribute("type", "button");
  });

  it("disables itself and sets aria-busy while isPending", () => {
    const onClick = vi.fn();
    renderComponent(
      <Button isPending onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("includes focus-visible ring and pressed styles", () => {
    renderComponent(<Button>Focus</Button>);
    const button = screen.getByRole("button", { name: "Focus" });
    expect(button.className).toContain("focus-visible:ring-2");
    expect(button.className).toContain("active:scale-[0.98]");
  });
});
