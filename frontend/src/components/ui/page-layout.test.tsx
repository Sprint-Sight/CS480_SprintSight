/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";

describe("PageContainer", () => {
  it("applies responsive padding and spacing", () => {
    const { container } = renderComponent(<PageContainer>content</PageContainer>);
    const root = container.firstElementChild as HTMLElement;
    expect(root).toHaveClass("p-4");
    expect(root).toHaveClass("sm:p-6");
    expect(root).toHaveClass("lg:p-8");
    expect(root).toHaveClass("space-y-5");
    expect(root).toHaveTextContent("content");
  });

  it("appends a custom className", () => {
    const { container } = renderComponent(<PageContainer className="bg-slate-50">content</PageContainer>);
    expect(container.firstElementChild).toHaveClass("bg-slate-50");
  });
});

describe("PageHeader", () => {
  it("renders the title as a responsive h1", () => {
    renderComponent(<PageHeader title="Projects" />);
    const heading = screen.getByRole("heading", { level: 1, name: "Projects" });
    expect(heading).toHaveClass("text-2xl");
    expect(heading).toHaveClass("sm:text-3xl");
  });

  it("renders the description and actions when provided", () => {
    renderComponent(
      <PageHeader
        title="Projects"
        description="Manage your teams"
        actions={<button type="button">New project</button>}
      />,
    );
    expect(screen.getByText("Manage your teams")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "New project" })).toBeInTheDocument();
  });

  it("omits the description and actions wrappers when they are not provided", () => {
    const { container } = renderComponent(<PageHeader title="Settings" />);
    expect(container.querySelectorAll("p")).toHaveLength(0);
    expect(container.querySelector(".flex-wrap.gap-2")).toBeNull();
  });
});
