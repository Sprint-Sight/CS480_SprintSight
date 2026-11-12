/// <reference types="vitest/globals" />
import "@testing-library/jest-dom";
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isAuthShowcaseEnabled } from "@/features/auth/auth-feature-flags";
import { AuthShell } from "@/features/auth/components/auth-shell";
import {
  AuthShowcaseShell,
  FADE_END,
  FADE_START,
  PAGE_GRADIENT,
} from "@/features/auth/components/auth-showcase-shell";
import { NAVY_AURA, THEMED_BACKGROUND } from "@/features/auth/components/auth-themed-background";
import {
  SPRINT_PREVIEW_CAPTIONS,
  PREVIEW_TICKETS,
  SprintPreview,
  heatmapIntensity,
  ticketForLane,
} from "@/features/auth/components/sprint-preview";

/**
 * jsdom has no AnimationEvent, so React listens for the webkit-prefixed name there (real
 * browsers use "animationiteration"), and animationName has to be set by hand.
 */
function fireAnimationIteration(element: Element, animationName: string) {
  const event = new Event("webkitAnimationIteration", { bubbles: true });
  Object.defineProperty(event, "animationName", { value: animationName });
  fireEvent(element, event);
}

describe("SprintPreview", () => {
  it("is hidden from assistive technology", () => {
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    expect(screen.getByTestId("sprint-preview")).toHaveAttribute("aria-hidden", "true");
  });

  it("renders the board, burndown line and a 7x12 heatmap", () => {
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    expect(screen.getAllByTestId("sprint-preview-card")).toHaveLength(4);
    expect(screen.getByTestId("burndown-line")).toHaveAttribute("pathLength", "1");
    expect(screen.getAllByTestId("heatmap-cell")).toHaveLength(84);
  });

  it("ends every ticket in the AI assessed column with an AI score", () => {
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    expect(screen.getByText("AI assessed")).toBeInTheDocument();
    const scores = screen.getAllByTestId("sprint-preview-score");
    expect(scores).toHaveLength(4);
    for (const score of scores) {
      expect(score).toHaveTextContent(/^AI \d{2}$/);
    }
  });

  it("turns animations off for reduced motion on every animated element", () => {
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    const animated = [
      ...screen.getAllByTestId("sprint-preview-card"),
      ...screen.getAllByTestId("sprint-preview-score"),
      screen.getByTestId("burndown-line"),
      ...screen.getAllByTestId("heatmap-cell"),
      screen.getByTestId("sprint-preview-caption"),
    ];
    for (const element of animated) {
      expect(element.getAttribute("class")).toContain("motion-reduce:animate-none");
    }
  });

  it("shows the logo in white instead of plain text, and centres the preview", () => {
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    const logo = screen.getByTestId("sprint-preview-logo");
    expect(logo.getAttribute("src")).toContain("logo.png");
    expect(logo.getAttribute("class")).toContain("brightness-0 invert");
    expect(screen.getByTestId("sprint-preview").getAttribute("class")).toContain("mx-auto");
  });

  it("shows the caption for the given index", () => {
    render(<SprintPreview captionIndex={2} laneCycles={[0, 0, 0, 0]} onLaneCycle={vi.fn()} />);
    expect(screen.getByTestId("sprint-preview-caption")).toHaveTextContent(SPRINT_PREVIEW_CAPTIONS[2]);
  });

  it("uses deterministic heatmap intensities so server and client markup match", () => {
    expect([0, 1, 2, 3, 4, 5].map(heatmapIntensity)).toEqual([0, 0.5, 1, 0.25, 0.75, 0]);
  });

  it("never shows the same ticket in two lanes at once, and uses the whole pool", () => {
    const seen = new Set<string>();
    for (let cycle = 0; cycle < 6; cycle += 1) {
      const onBoard = [0, 1, 2, 3].map((lane) => ticketForLane(lane, cycle).label);
      expect(new Set(onBoard).size).toBe(4);
      onBoard.forEach((label) => seen.add(label));
    }
    expect(seen.size).toBe(PREVIEW_TICKETS.length);
  });

  it("reports a finished trip only for the card's own animation, not the badge's", () => {
    const onLaneCycle = vi.fn();
    render(<SprintPreview captionIndex={0} laneCycles={[0, 0, 0, 0]} onLaneCycle={onLaneCycle} />);
    const card = screen.getAllByTestId("sprint-preview-card")[1];

    fireAnimationIteration(card, "badge-in");
    expect(onLaneCycle).not.toHaveBeenCalled();

    fireAnimationIteration(card, "card-flow");
    expect(onLaneCycle).toHaveBeenCalledWith(1);
  });
});

describe("AuthShowcaseShell (idle feature)", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: false,
        media: query,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the auth form next to the preview", () => {
    render(
      <AuthShowcaseShell>
        <form aria-label="Sign in form" />
      </AuthShowcaseShell>,
    );
    expect(screen.getByRole("form", { name: "Sign in form" })).toBeInTheDocument();
    expect(screen.getByTestId("sprint-preview-caption")).toHaveTextContent(SPRINT_PREVIEW_CAPTIONS[0]);
  });

  it("shows a new ticket in a lane after its card finishes a trip", () => {
    render(
      <AuthShowcaseShell>
        <form aria-label="Sign in form" />
      </AuthShowcaseShell>,
    );
    const card = screen.getAllByTestId("sprint-preview-card")[0];
    expect(card).toHaveTextContent(PREVIEW_TICKETS[0].label);

    fireAnimationIteration(card, "card-flow");
    expect(card).toHaveTextContent(PREVIEW_TICKETS[4].label);
  });

  it("paints one page-wide background instead of a separate dark panel", () => {
    render(
      <AuthShowcaseShell>
        <form aria-label="Sign in form" />
      </AuthShowcaseShell>,
    );
    const background = screen.getByTestId("auth-page-background");
    // Fixed behind the whole page (both columns), and only on large screens.
    expect(background.getAttribute("class")).toContain("fixed inset-0");
    expect(background.getAttribute("class")).toContain("hidden");
    expect(background.getAttribute("class")).toContain("lg:block");
    // The preview column no longer paints its own navy block or a solid fade over the glows.
    expect(screen.getByTestId("auth-preview-panel").getAttribute("class")).not.toContain("bg-brand");
    expect(screen.queryByTestId("auth-preview-fade")).not.toBeInTheDocument();
  });

  it("eases from the exact navy to the exact slate-50 behind the form card", () => {
    expect(PAGE_GRADIENT).toContain(`hsl(var(--brand)), hsl(210 40% 98%) 0%) ${FADE_START}%`);
    expect(PAGE_GRADIENT).toContain(`hsl(210 40% 98%) 100%) ${FADE_END}%`);
    // The fade ends inside the form column (which starts at 60% of the width), behind the card.
    expect(FADE_END).toBeGreaterThan(60);
  });
});

describe("AuthShell feature flag", () => {
  it("reads only an explicit 'true' as on, so the showcase is off by default", () => {
    expect(isAuthShowcaseEnabled(undefined)).toBe(false);
    expect(isAuthShowcaseEnabled("")).toBe(false);
    expect(isAuthShowcaseEnabled("false")).toBe(false);
    expect(isAuthShowcaseEnabled("1")).toBe(false);
    expect(isAuthShowcaseEnabled("true")).toBe(true);
    expect(isAuthShowcaseEnabled(" TRUE ")).toBe(true);
  });

  it("by default shows only the form on the diagonal themed background", () => {
    render(
      <AuthShell>
        <form aria-label="Sign in form" />
      </AuthShell>,
    );
    expect(screen.getByRole("form", { name: "Sign in form" })).toBeInTheDocument();
    expect(screen.getByTestId("auth-themed-background")).toBeInTheDocument();
    expect(screen.queryByTestId("sprint-preview")).not.toBeInTheDocument();
    expect(screen.queryByTestId("auth-page-background")).not.toBeInTheDocument();
  });

  it("uses a top-left to bottom-right theme instead of a left-to-right fade", () => {
    expect(THEMED_BACKGROUND).toContain("linear-gradient(135deg");
    expect(THEMED_BACKGROUND).not.toContain("to right");
    expect(NAVY_AURA).toContain("hsl(var(--brand)");
  });

  it("drifts the navy and sky auras slowly, and stops them for reduced motion", () => {
    render(
      <AuthShell>
        <form aria-label="Sign in form" />
      </AuthShell>,
    );
    const auras = screen.getAllByTestId("auth-aura");
    expect(auras).toHaveLength(2);
    expect(auras[0].getAttribute("class")).toContain("animate-aura-drift-a");
    expect(auras[1].getAttribute("class")).toContain("animate-aura-drift-b");
    for (const aura of auras) {
      expect(aura.getAttribute("class")).toContain("motion-reduce:animate-none");
    }
  });

  it("switches to the showcase layout when the flag is on", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
    );
    render(
      <AuthShell showcase>
        <form aria-label="Sign in form" />
      </AuthShell>,
    );
    expect(screen.getByTestId("sprint-preview")).toBeInTheDocument();
    expect(screen.queryByTestId("auth-themed-background")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
