"use client";

import { useState, type ReactNode } from "react";

export type ChartTableColumn<T> = {
  header: string;
  cell: (row: T) => ReactNode;
};

type ChartWithTableProps<T> = {
  summary: string;
  rows: T[];
  columns: ChartTableColumn<T>[];
  children: ReactNode;
};

export function ChartWithTable<T>({ summary, rows, columns, children }: ChartWithTableProps<T>) {
  const [showTable, setShowTable] = useState(false);

  return (
    <div role="group" aria-label={summary} className="min-w-0">
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setShowTable((visible) => !visible)}
          className="text-xs font-semibold text-blue-800 hover:text-blue-950"
        >
          {showTable ? "View as chart" : "View as table"}
        </button>
      </div>
      {showTable ? (
        <div className="mt-2 max-h-[360px] overflow-auto">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{summary}</caption>
            <thead className="sticky top-0 bg-white text-xs uppercase text-slate-500">
              <tr>
                {columns.map((column) => (
                  <th key={column.header} scope="col" className="px-2 py-1.5 font-semibold">
                    {column.header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex} className="border-t border-slate-100">
                  {columns.map((column) => (
                    <td key={column.header} className="px-2 py-1.5 text-slate-700">
                      {column.cell(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </div>
  );
}
