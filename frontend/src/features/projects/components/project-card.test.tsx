/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { ProjectCard } from "@/features/projects/components/project-card";
import type { Project } from "@/features/projects/types";

const project = {
  id: "p-1",
  project_name: "Sprint Alpha",
  team_name: "Team 1",
  module: "CS480",
  members: [{ id: "s-1", full_name: "Grace Hopper" }],
} as unknown as Project;

describe("ProjectCard controls", () => {
  it("labels the edit and delete icon buttons with the project name", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    renderComponent(
      <ProjectCard
        project={project}
        onEdit={onEdit}
        onDelete={onDelete}
        onAddMember={vi.fn()}
        onRemoveMember={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit project Sprint Alpha" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete project Sprint Alpha" }));

    expect(onEdit).toHaveBeenCalledOnce();
    expect(onDelete).toHaveBeenCalledWith("p-1", expect.anything());
  });

  it("labels the remove-member button with the student name", () => {
    renderComponent(
      <ProjectCard
        project={project}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onAddMember={vi.fn()}
        onRemoveMember={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Remove Grace Hopper from project" })).toBeInTheDocument();
  });
});
