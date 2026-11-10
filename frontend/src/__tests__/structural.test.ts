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
      "src/app/(dashboard)/profile/page.tsx",
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

describe("Tooling configuration", () => {
  it("lints with the jsx-a11y recommended rules on top of next/core-web-vitals", () => {
    const eslintConfig = readFile(".eslintrc.json");
    expect(eslintConfig).toContain('"next/core-web-vitals"');
    expect(eslintConfig).toContain('"plugin:jsx-a11y/recommended"');
  });

  it("provides Prettier format scripts and a pinned Prettier dependency", () => {
    const packageJson = JSON.parse(readFile("package.json")) as {
      scripts: Record<string, string>;
      devDependencies: Record<string, string>;
    };
    expect(packageJson.scripts.format).toBe("prettier --write .");
    expect(packageJson.scripts["format:check"]).toBe("prettier --check .");
    expect(packageJson.devDependencies.prettier).toMatch(/^\d+\.\d+\.\d+$/);
    expect(fs.existsSync(".prettierrc.json")).toBe(true);
  });

  it("keeps previously minified files formatted across multiple lines", () => {
    const formattedFiles = [
      "src/features/settings/components/rubric-settings.tsx",
      "src/features/dashboard/components/commit-activity-chart.tsx",
      "src/features/sprints/components/sprint-overview-page-content.tsx",
      "src/features/assessment/hooks/use-assessment-report.ts",
    ];

    formattedFiles.forEach((filePath) => {
      const lineLengths = readFile(filePath)
        .split("\n")
        .map((line) => line.length);
      const longestLine = Math.max(...lineLengths);
      expect(longestLine, `${filePath} has a ${longestLine}-character line`).toBeLessThanOrEqual(
        200,
      );
    });
  });
});

function listSourceFiles(directory: string): string[] {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) return listSourceFiles(fullPath);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.(ts|tsx)$/.test(entry.name) ? [fullPath] : [];
  });
}

function toRepoPath(filePath: string) {
  return path.relative(process.cwd(), filePath).split(path.sep).join("/");
}

describe("API client and session boundaries", () => {
  const sourceFiles = listSourceFiles(path.join(process.cwd(), "src")).filter(
    (filePath) => !toRepoPath(filePath).startsWith("src/__tests__/") && !filePath.endsWith("test-utils.tsx"),
  );

  it("only the shared API client calls fetch (plus the assessment event stream)", () => {
    const allowed = new Set(["src/lib/api/client.ts", "src/features/assessment/hooks/use-assessment-report.ts"]);
    const offenders = sourceFiles
      .filter((filePath) => !allowed.has(toRepoPath(filePath)))
      .filter((filePath) => /(^|[^.\w])fetch\s*\(/.test(readFile(filePath)))
      .map(toRepoPath);
    expect(offenders).toEqual([]);
  });

  it("only the session module reads or writes auth storage keys", () => {
    const offenders = sourceFiles
      .filter((filePath) => toRepoPath(filePath) !== "src/lib/auth/session.ts")
      .filter((filePath) => /sprintsight-(auth-|access-token|session)/.test(readFile(filePath)))
      .map(toRepoPath);
    expect(offenders).toEqual([]);
  });

  it("reads the API base URL from a single place", () => {
    const offenders = sourceFiles
      .filter((filePath) => toRepoPath(filePath) !== "src/lib/api/client.ts")
      .filter((filePath) => /NEXT_PUBLIC_API/.test(readFile(filePath)))
      .map(toRepoPath);
    expect(offenders).toEqual([]);
  });

  it("keeps text and chart ticks at 12px or larger", () => {
    const offenders = sourceFiles
      .filter((filePath) => /text-\[(?:[0-9]|1[01])px\]|fontSize:\s*(?:[0-9]|1[01])\b/.test(readFile(filePath)))
      .map(toRepoPath);
    expect(offenders).toEqual([]);
  });

  it("turns errors into messages with getErrorMessage, not ad-hoc instanceof checks", () => {
    const offenders = sourceFiles
      .filter((filePath) => /instanceof Error\s*\?/.test(readFile(filePath)))
      .map(toRepoPath);
    expect(offenders).toEqual([]);
  });
});
