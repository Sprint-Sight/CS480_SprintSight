/// <reference types="vitest/globals" />
import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";

/**
 * Structural Tests
 *
 * Verify architectural constraints:
 * - Route files are thin adapters (10-15 lines)
 * - Presentational components don't make API calls
 * - Presentational components don't access sessionStorage/localStorage
 * - Hooks encapsulate side effects
 */

function readFile(filePath: string): string {
  return fs.readFileSync(filePath, "utf-8");
}

function countLines(content: string): number {
  return content.split("\n").length;
}

describe("Structural Architecture Tests", () => {
  it("route files should be thin adapters (max 15 lines excluding imports/exports)", () => {
    const routeFiles = [
      "src/app/(dashboard)/audit-log/page.tsx",
      "src/app/admin/audit-log/page.tsx",
    ];

    routeFiles.forEach((filePath) => {
      const content = readFile(path.join(process.cwd(), filePath));
      const lines = content.split("\n").filter((line) => line.trim().length > 0);
      expect(
        lines.length,
        `Route file ${filePath} should be under 15 lines but has ${lines.length}`
      ).toBeLessThanOrEqual(15);
    });
  });

  it("presentational components should not directly call fetch or apiRequest", () => {
    const componentPath = "src/features/audit/components/audit-log-page.tsx";
    const content = readFile(path.join(process.cwd(), componentPath));

    expect(content).not.toMatch(/fetch\s*\(/);
    expect(content).not.toMatch(/apiRequest\s*\(/);
    expect(content).not.toMatch(/useEffect\s*\(\s*\(\s*\)\s*=>/);
  });

  it("presentational components should not access sessionStorage or localStorage directly", () => {
    const componentPaths = [
      "src/features/audit/components/audit-log-page.tsx",
      "src/features/audit/components/action-audit-table.tsx",
      "src/features/audit/components/override-audit-table.tsx",
    ];

    componentPaths.forEach((filePath) => {
      const content = readFile(path.join(process.cwd(), filePath));
      expect(content).not.toMatch(/sessionStorage\s*\./);
      expect(content).not.toMatch(/localStorage\s*\./);
    });
  });

  it("hooks should encapsulate state and side effects", () => {
    const hookPath = "src/features/audit/hooks/use-audit-log.ts";
    const content = readFile(path.join(process.cwd(), hookPath));

    // Hooks should export a function starting with 'use'
    expect(content).toMatch(/export\s+function\s+use/);
    // Hooks should use useState or useEffect
    expect(content).toMatch(/useState|useEffect|useCallback|useMemo/);
  });

  it("feature API files should centralize API requests", () => {
    const apiPath = "src/features/audit/audit-api.ts";
    const content = readFile(path.join(process.cwd(), apiPath));

    // API file should export functions, not components
    expect(content).not.toMatch(/export\s+(function|const)\s+\w+\(\)\s*\{?\s*return\s*<|export\s+default\s+function|export\s+default\s+(class|const)/);
    // API file should use apiRequest or similar
    expect(content).toMatch(/apiRequest|fetch/);
  });

  it("route files should only import and render page content components", () => {
    const routePath = "src/app/(dashboard)/audit-log/page.tsx";
    const content = readFile(path.join(process.cwd(), routePath));

    // Should import page content component
    expect(content).toMatch(/AuditLogPageContent/);
    // Should NOT use "use client" directive (only page-content components have it)
    expect(content).not.toMatch(/"use client"/);
    // Should be a default export function
    expect(content).toMatch(/export\s+default\s+function/);
  });

  it("page-content components should be the only place for orchestration", () => {
    const pageContentPath = "src/features/audit/components/audit-log-page-content.tsx";
    const content = readFile(path.join(process.cwd(), pageContentPath));

    // Should use "use client"
    expect(content).toMatch(/"use client"/);
    // Should use feature hooks
    expect(content).toMatch(/useAuditLog/);
    // Should render presentational component
    expect(content).toMatch(/<AuditLogPage/);
  });
});
