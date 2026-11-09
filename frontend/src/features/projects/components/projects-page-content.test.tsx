import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProjectsPageContent from "@/features/projects/components/projects-page-content";
import { ApiError, apiRequest } from "@/lib/api/client";
import { setSession, signOut } from "@/lib/auth/session";
import { createTestWrapper } from "@/test-utils";

const router = { push: vi.fn(), replace: vi.fn(), refresh: vi.fn() };
vi.mock("next/navigation", () => ({
  useRouter: () => router,
  usePathname: () => "/projects",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  apiRequest: vi.fn(),
}));

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const ROSTER_URL = `/courses/${COURSE_ID}/students?include_other_sections=true`;
const course = {
  id: COURSE_ID,
  code: "CS111",
  name: "Intro",
  section: "2",
  year: 2026,
  term: "Fall",
};
const freeStudent = {
  id: "s3",
  email: "free@example.com",
  full_name: "Free Student",
  is_active: true,
  role: "student",
};

function mockBackend() {
  vi.mocked(apiRequest).mockImplementation(async (path: string, options?: { method?: string }) => {
    if (options?.method === "POST" && path === `/courses/${COURSE_ID}/students/${freeStudent.id}`) {
      throw new ApiError("Free Student is already enrolled in CS111 · Section 1 (Fall 2026).", {
        status: 409,
      });
    }
    if (path === "/courses") return [course];
    if (path === ROSTER_URL) return [];
    if (path === `/courses/${COURSE_ID}/projects`) return [];
    if (path === "/users") return [freeStudent];
    if (path.startsWith("/settings/jira-credentials")) {
      return { jira_email: "", jira_token_configured: false, is_saved: false };
    }
    return [];
  });
}

const rosterLoads = () =>
  vi.mocked(apiRequest).mock.calls.filter(([path]) => path === ROSTER_URL).length;
const directoryLoads = () =>
  vi.mocked(apiRequest).mock.calls.filter(([path]) => path === "/users").length;

describe("ProjectsPageContent roster refresh", () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
    setSession({
      token: "token",
      user: { id: "i1", role: "instructor", email: "prof@example.com", fullName: "Prof" },
    });
    mockBackend();
  });

  afterEach(() => {
    signOut();
  });

  async function openRoster() {
    render(<ProjectsPageContent />, { wrapper: createTestWrapper() });
    await waitFor(() => expect(rosterLoads()).toBeGreaterThanOrEqual(1));
    fireEvent.click(screen.getByRole("button", { name: /^Students$/ }));
    await screen.findByRole("button", { name: "Enroll Free Student in the course" });
  }

  it("reloads enrollments and the directory when the roster opens", async () => {
    render(<ProjectsPageContent />, { wrapper: createTestWrapper() });
    await waitFor(() => expect(rosterLoads()).toBeGreaterThanOrEqual(1));
    const rosterBefore = rosterLoads();

    fireEvent.click(screen.getByRole("button", { name: /^Students$/ }));

    await waitFor(() => expect(rosterLoads()).toBe(rosterBefore + 1));
    expect(directoryLoads()).toBe(1);
  });

  it("Refresh reloads both the directory and enrollments", async () => {
    await openRoster();
    const rosterBefore = rosterLoads();
    const directoryBefore = directoryLoads();

    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(rosterLoads()).toBe(rosterBefore + 1));
    expect(directoryLoads()).toBe(directoryBefore + 1);
  });

  it("reloads enrollments after an enroll conflict (409)", async () => {
    await openRoster();
    const rosterBefore = rosterLoads();

    fireEvent.click(screen.getByRole("button", { name: "Enroll Free Student in the course" }));

    await waitFor(() => expect(rosterLoads()).toBe(rosterBefore + 1));
  });
});
