import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";

import { renderComponent } from "@/test-utils";
import DashboardShell from "@/components/layout/dashboard-shell";
import { writeScope } from "@/features/ingestion/scope-store";

let loadScopeProjects: () => Promise<unknown[]> = async () => [];

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/lib/auth/session", () => ({
  useSession: () => ({ user: { role: "instructor", fullName: "Sample Instructor", email: "instructor@example.com" } }),
  signOut: vi.fn(),
}));

vi.mock("@/features/auth/login-api", () => ({
  restoreSession: vi.fn().mockResolvedValue({
    user: { role: "instructor", fullName: "Sample Instructor", email: "instructor@example.com" },
  }),
}));

vi.mock("@/features/projects/course-projects-api", () => ({
  scopeProjectsQueryOptions: () => ({ queryKey: ["scope-projects"], queryFn: () => loadScopeProjects() }),
}));

vi.mock("@/features/ingestion/scope-store", () => ({
  SEMESTER_STORAGE_KEY: "semester",
  readScope: () => ({}),
  writeScope: vi.fn(),
}));

vi.mock("@/features/ingestion/scope-options", () => ({
  buildSprintOptions: () => [],
  semesterLabel: () => "Fall 2024",
}));

vi.mock("@/features/ingestion/hooks/use-ingestion-sync", () => ({
  useIngestionSync: () => ({ gitRuns: [], jiraSnapshots: [] }),
}));

vi.mock("@/hooks/use-notifications", () => ({
  useNotifications: () => ({
    notifications: [],
    unreadCount: 0,
    isLoading: false,
    error: null,
    announcement: "",
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
  }),
}));

vi.mock("@/components/ui/notifications-modal", () => ({
  NotificationsDropdown: ({ children }: { children: React.ReactElement }) => children,
}));

function stubViewport(isDesktop: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: isDesktop,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

describe("DashboardShell sidebar header", () => {
  beforeEach(() => {
    stubViewport(false);
  });

  it("centers the logo in its header box", async () => {
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    const logo = await screen.findByAltText("SprintSight Logo");
    const header = logo.parentElement as HTMLElement;

    expect(header).toHaveClass("justify-center");
    expect(header).not.toHaveClass("justify-between");
  });

  it("keeps the mobile close button out of the logo's centering flow", async () => {
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    const closeButton = await screen.findByRole("button", { name: "Close sidebar" });

    expect(closeButton).toHaveClass("absolute");
    expect(closeButton).toHaveClass("right-2");
    expect(closeButton).toHaveClass("md:hidden");
  });
});

describe("DashboardShell saved scope", () => {
  beforeEach(() => {
    stubViewport(true);
    vi.mocked(writeScope).mockClear();
  });

  it("does not overwrite the saved team or sprint with empty values before scope loads", async () => {
    loadScopeProjects = () => new Promise(() => {});
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    await new Promise((resolve) => setTimeout(resolve, 50));

    const writes = vi.mocked(writeScope).mock.calls.map(([patch]) => patch);
    expect(writes.some((patch) => patch.selectedProjectId === "" || patch.selectedCourseId === "")).toBe(false);
    expect(writes.some((patch) => patch.selectedSprintId === "sprint-1")).toBe(false);
  });
});

describe("DashboardShell mobile drawer", () => {
  it("is inert while closed on phones so its links are skipped by keyboard focus", async () => {
    stubViewport(false);
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    const aside = (await screen.findByRole("button", { name: "Close sidebar" })).closest("aside") as HTMLElement;

    expect(aside.inert).toBe(true);
  });

  it("is not inert on desktop, where the sidebar is always visible", async () => {
    stubViewport(true);
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    const aside = (await screen.findByRole("button", { name: "Close sidebar" })).closest("aside") as HTMLElement;

    expect(aside.inert).toBe(false);
  });

  it("opens from the toggle, moves focus into the drawer, and closes on Escape with focus returned", async () => {
    stubViewport(false);
    renderComponent(<DashboardShell><div>content</div></DashboardShell>);

    const toggle = await screen.findByRole("button", { name: "Toggle sidebar" });
    const closeButton = screen.getByRole("button", { name: "Close sidebar" });
    const aside = closeButton.closest("aside") as HTMLElement;

    fireEvent.click(toggle);
    expect(aside.inert).toBe(false);
    expect(document.activeElement).toBe(closeButton);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(aside.inert).toBe(true);
    expect(document.activeElement).toBe(toggle);
  });
});
