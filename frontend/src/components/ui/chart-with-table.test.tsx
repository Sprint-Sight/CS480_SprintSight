/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { describe, it, expect } from "vitest";
import { fireEvent, screen, within } from "@testing-library/react";
import { renderComponent } from "@/test-utils";
import { ChartWithTable, type ChartTableColumn } from "@/components/ui/chart-with-table";

type Row = { name: string; commits: number };

const rows: Row[] = [
  { name: "Ada", commits: 4 },
  { name: "Grace", commits: 9 },
];

const columns: ChartTableColumn<Row>[] = [
  { header: "Member", cell: (row) => row.name },
  { header: "Commits", cell: (row) => row.commits },
];

describe("ChartWithTable", () => {
  it("exposes the chart summary as an accessible group label", () => {
    renderComponent(
      <ChartWithTable summary="Commits by member" rows={rows} columns={columns}>
        <div>chart body</div>
      </ChartWithTable>,
    );
    expect(screen.getByRole("group", { name: "Commits by member" })).toBeInTheDocument();
    expect(screen.getByText("chart body")).toBeInTheDocument();
  });

  it("switches to an accessible data table and back", () => {
    renderComponent(
      <ChartWithTable summary="Commits by member" rows={rows} columns={columns}>
        <div>chart body</div>
      </ChartWithTable>,
    );

    fireEvent.click(screen.getByRole("button", { name: "View as table" }));

    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Member" })).toBeInTheDocument();
    expect(within(table).getByRole("columnheader", { name: "Commits" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "Grace" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "9" })).toBeInTheDocument();
    expect(screen.queryByText("chart body")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "View as chart" }));

    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText("chart body")).toBeInTheDocument();
  });
});
