/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { FirstRunChecklist } from "@/features/dashboard/components/first-run-checklist";

describe("FirstRunChecklist", () => {
  it("marks completed steps and leaves later steps open", () => {
    renderComponent(<FirstRunChecklist hasCourse hasProject={false} />);
    expect(screen.getByText("Create a course", { exact: false })).toHaveClass("line-through");
    expect(screen.queryByRole("link", { name: "Create a course" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create a project" })).toHaveAttribute("href", "/projects");
    expect(screen.getByRole("link", { name: "Generate an assessment" })).toHaveAttribute("href", "/assessment-report");
  });

  it("links the open course step to the course management entry point", () => {
    renderComponent(<FirstRunChecklist hasCourse={false} hasProject={false} />);
    expect(screen.getByRole("link", { name: "Create a course" })).toHaveAttribute("href", "/projects?manageCourses=1");
  });

  it("shows no completed markers when nothing is done yet", () => {
    renderComponent(<FirstRunChecklist hasCourse={false} hasProject={false} />);
    expect(screen.queryByText("(done)", { exact: false })).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });
});
