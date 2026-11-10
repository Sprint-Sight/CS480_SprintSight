import fs from "fs";
import path from "path";
import { describe, expect, it } from "vitest";

import { CHART_GRID_STROKE, CHART_TICK, chartColor } from "@/lib/chart-theme";

function listSourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return listSourceFiles(fullPath);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name)
      ? [fullPath]
      : [];
  });
}

describe("chart theme", () => {
  it("builds token colors and shares one readable tick style", () => {
    expect(chartColor("chart-1")).toBe("hsl(var(--chart-1))");
    expect(CHART_TICK).toEqual({ fill: "hsl(var(--muted))", fontSize: 12 });
    expect(CHART_GRID_STROKE).toBe("hsl(var(--border))");
  });

  it("only references tokens that are defined in globals.css", () => {
    const css = fs.readFileSync(path.join(process.cwd(), "src/app/globals.css"), "utf-8");
    const defined = new Set([...css.matchAll(/--([a-z0-9-]+):/g)].map((match) => match[1]));

    const used = new Set<string>();
    for (const file of listSourceFiles(path.join(process.cwd(), "src"))) {
      const source = fs.readFileSync(file, "utf-8");
      for (const match of source.matchAll(/chartColor\("([a-z0-9-]+)"\)/g)) used.add(match[1]);
      for (const match of source.matchAll(/hsl\(var\(--([a-z0-9-]+)\)\)/g)) used.add(match[1]);
    }

    const missing = [...used].filter((token) => !defined.has(token));
    expect(missing).toEqual([]);
    expect(used.size).toBeGreaterThan(5);
  });
});
