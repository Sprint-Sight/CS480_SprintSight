"use client";

// ─────────────────────────────────────────────────────────────────────────────
// IDLE FEATURE: AUTH SHOWCASE (off by default)
// Only rendered when NEXT_PUBLIC_AUTH_SHOWCASE=true. See src/features/auth/auth-feature-flags.ts.
// Kept on purpose so it can be switched back on later; do not delete as "unused".
// ─────────────────────────────────────────────────────────────────────────────

import {
  PREVIEW_LANE_COUNT,
  SPRINT_PREVIEW_CAPTIONS,
  SprintPreview,
} from "@/features/auth/components/sprint-preview";
import { useLaneCycles } from "@/features/auth/hooks/use-lane-cycles";
import { useRotatingIndex } from "@/features/auth/hooks/use-rotating-index";

/** slate-50 (#f8fafc), the light end of the page and the mobile background. */
const LIGHT = "hsl(210 40% 98%)";

/** Where (as % of page width) the navy starts turning light, and where it is fully light. */
export const FADE_START = 38;
export const FADE_END = 88;

/**
 * Ease-in-out stops across the fade: [% through the fade, % of light mixed in].
 * A straight linear fade has a visible "kink" where it starts and ends, which the eye reads
 * as a vertical line; easing both ends removes it.
 */
const EASE_STOPS: ReadonlyArray<[through: number, light: number]> = [
  [0, 0],
  [10, 1.3],
  [20, 4.9],
  [30, 10.4],
  [40, 17.5],
  [48, 25.9],
  [55, 35.2],
  [61, 45],
  [67, 55],
  [73, 64.8],
  [78, 74.1],
  [83, 82.5],
  [88, 89.6],
  [93, 95.1],
  [97, 98.7],
  [100, 100],
];

/**
 * One page-wide background: navy on the left easing into slate-50 behind the form card.
 * Mixing in OKLab keeps the middle a soft blue instead of a muddy grey.
 */
export const PAGE_GRADIENT = `linear-gradient(to right in oklab, ${EASE_STOPS.map(([through, light]) => {
  const position = FADE_START + (through * (FADE_END - FADE_START)) / 100;
  return `color-mix(in oklab, hsl(var(--brand)), ${LIGHT} ${light}%) ${position}%`;
}).join(", ")})`;

type AuthShowcaseShellProps = {
  children: React.ReactNode;
};

/**
 * [IDLE: AUTH SHOWCASE] Auth layout. On large screens a single background spans the whole page (navy easing into
 * light, with shared glows), the animated preview sits on the navy side and the form card
 * floats on the light side, so it reads as one surface rather than a split screen.
 * Mobile shows only the form on slate-50.
 */
export function AuthShowcaseShell({ children }: AuthShowcaseShellProps) {
  const captionIndex = useRotatingIndex(SPRINT_PREVIEW_CAPTIONS.length);
  const { laneCycles, advanceLane } = useLaneCycles(PREVIEW_LANE_COUNT);

  return (
    <div className="relative min-h-dvh bg-slate-50 lg:grid lg:grid-cols-[1.5fr_1fr]">
      <div
        data-testid="auth-page-background"
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 hidden overflow-hidden lg:block"
        style={{ backgroundImage: PAGE_GRADIENT }}
      >
        {/* Glows span the page, including a faint one behind the form, so both sides share light. */}
        <div className="absolute -left-32 top-1/4 h-[28rem] w-[28rem] rounded-full bg-sky-500/20 blur-3xl" />
        <div className="absolute -bottom-32 left-[22%] h-96 w-96 rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="absolute left-[45%] top-[10%] h-80 w-80 rounded-full bg-sky-400/15 blur-3xl" />
        <div className="absolute right-[8%] top-1/2 h-[30rem] w-[30rem] -translate-y-1/2 rounded-full bg-sky-200/40 blur-3xl" />
      </div>
      <aside
        data-testid="auth-preview-panel"
        className="relative hidden py-12 pl-12 pr-[18%] text-white lg:sticky lg:top-0 lg:flex lg:h-dvh lg:items-center xl:pl-16"
      >
        <SprintPreview captionIndex={captionIndex} laneCycles={laneCycles} onLaneCycle={advanceLane} />
      </aside>
      <div className="relative min-w-0">{children}</div>
    </div>
  );
}
