// IDLE FEATURE: AUTH SHOWCASE (off by default). Only used by auth-showcase-shell.tsx, which
// renders when NEXT_PUBLIC_AUTH_SHOWCASE=true. See src/features/auth/auth-feature-flags.ts.
import Image from "next/image";

export const SPRINT_PREVIEW_CAPTIONS = [
  "AI grades every sprint against your rubric",
  "Every score is backed by Git and Jira evidence",
  "Instructors review and edit before students see it",
] as const;

const COLUMNS = ["To do", "In progress", "AI assessed"] as const;

/** A student team's Jira tickets; each gets an AI score once it reaches "AI assessed". */
export const PREVIEW_TICKETS = [
  { label: "SP-12 User login", score: 92 },
  { label: "SP-14 DB schema", score: 85 },
  { label: "SP-17 Demo slides", score: 78 },
  { label: "SP-21 Unit tests", score: 88 },
  { label: "SP-23 Sprint review", score: 81 },
  { label: "SP-25 Jira sync", score: 90 },
  { label: "SP-28 API docs", score: 74 },
  { label: "SP-30 CI pipeline", score: 87 },
  { label: "SP-31 Search page", score: 83 },
  { label: "SP-34 Bug fixes", score: 79 },
  { label: "SP-36 UI polish", score: 91 },
  { label: "SP-38 Retro notes", score: 76 },
] as const;

/** Board lanes: one card each, staggered a quarter of the 12s cycle apart. */
const LANES = [
  { accent: "bg-sky-400", delay: "0s" },
  { accent: "bg-emerald-400", delay: "-3s" },
  { accent: "bg-amber-400", delay: "-6s" },
  { accent: "bg-rose-400", delay: "-9s" },
] as const;

export const PREVIEW_LANE_COUNT = LANES.length;

/**
 * Ticket shown in a lane on its Nth trip across the board. Lanes step through the pool
 * in strides of the lane count, so two lanes never show the same ticket at once.
 */
export function ticketForLane(lane: number, cycle: number) {
  return PREVIEW_TICKETS[(lane + cycle * LANES.length) % PREVIEW_TICKETS.length];
}

/** Badge colours follow the app's score bands: >= 85, >= 75, below 75. */
function scoreBadgeClass(score: number): string {
  if (score >= 85) return "bg-emerald-100 text-emerald-800";
  if (score >= 75) return "bg-amber-100 text-amber-800";
  return "bg-rose-100 text-rose-800";
}

const HEATMAP_ROWS = 7;
const HEATMAP_COLS = 12;
const CELL = 10;
const CELL_GAP = 3;

/** Fixed pseudo-random intensity (0, .25, .5, .75 or 1), identical on server and client. */
export function heatmapIntensity(index: number): number {
  return ((index * 37) % 5) / 4;
}

const HEATMAP_CELLS = Array.from({ length: HEATMAP_ROWS * HEATMAP_COLS }, (_, i) => ({
  i,
  x: Math.floor(i / HEATMAP_ROWS) * (CELL + CELL_GAP),
  y: (i % HEATMAP_ROWS) * (CELL + CELL_GAP),
  intensity: heatmapIntensity(i),
}));

type SprintPreviewProps = {
  captionIndex: number;
  /** How many trips each lane's card has finished; picks the ticket it shows. */
  laneCycles: readonly number[];
  /** Called when a lane's card finishes a trip (it is invisible at that moment). */
  onLaneCycle: (lane: number) => void;
};

/** Decorative, animated product preview for the auth screens. Hidden from assistive tech. */
export function SprintPreview({ captionIndex, laneCycles, onLaneCycle }: SprintPreviewProps) {
  const caption = SPRINT_PREVIEW_CAPTIONS[captionIndex % SPRINT_PREVIEW_CAPTIONS.length];

  return (
    <div
      aria-hidden="true"
      data-testid="sprint-preview"
      className="mx-auto flex w-full max-w-xl flex-col gap-8 2xl:max-w-2xl"
    >
      <div>
        {/* The logo file is dark navy; the filter turns it white so it shows on the navy side. */}
        <Image
          data-testid="sprint-preview-logo"
          src="/logo.png"
          alt=""
          width={711}
          height={441}
          className="h-14 w-auto brightness-0 invert"
        />
        <p className="mt-2 text-3xl font-semibold leading-tight">AI grading for every sprint.</p>
        <p className="mt-3 text-base text-white/70">
          Your team&apos;s Git and Jira work in, rubric-based grades and feedback out.
        </p>
      </div>

      <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
        <div className="grid grid-cols-3 gap-3 text-xs font-medium text-white/60">
          {COLUMNS.map((column) => (
            <p key={column}>{column}</p>
          ))}
        </div>
        <div className="relative mt-2 h-40">
          <div className="absolute inset-0 grid grid-cols-3 gap-3">
            {COLUMNS.map((column) => (
              <div key={column} className="rounded-lg bg-white/5" />
            ))}
          </div>
          {LANES.map((lane, index) => {
            const ticket = ticketForLane(index, laneCycles[index] ?? 0);
            return (
              <div
                key={index}
                data-testid="sprint-preview-card"
                onAnimationIteration={(event) => {
                  // The badge's own animation bubbles up here too; only count the card's trip.
                  if (event.animationName === "card-flow") onLaneCycle(index);
                }}
                className="absolute left-0 flex w-[calc((100%-1.5rem)/3)] animate-card-flow items-center gap-2 rounded-md bg-white px-2 py-1.5 text-xs font-medium text-slate-800 shadow-sm motion-reduce:translate-x-[calc(200%+1.5rem)] motion-reduce:animate-none"
                style={{ top: `${0.5 + index * 2.4}rem`, animationDelay: lane.delay }}
              >
                <span className={`h-3 w-1 shrink-0 rounded-full ${lane.accent}`} />
                <span className="min-w-0 flex-1 truncate">{ticket.label}</span>
                <span
                  data-testid="sprint-preview-score"
                  className={`shrink-0 animate-badge-in rounded px-1 text-xs font-semibold motion-reduce:animate-none ${scoreBadgeClass(ticket.score)}`}
                  style={{ animationDelay: lane.delay }}
                >
                  AI {ticket.score}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
          <p className="text-xs font-medium text-white/60">Sprint burndown</p>
          <svg viewBox="0 0 200 100" className="mt-2 h-24 w-full">
            <path d="M10 90 H190" stroke="currentColor" strokeOpacity={0.2} fill="none" />
            <path d="M10 10 L190 90" stroke="currentColor" strokeOpacity={0.4} strokeDasharray="4 4" fill="none" />
            <path
              data-testid="burndown-line"
              d="M10 10 L40 22 L70 26 L100 48 L130 56 L160 74 L190 86"
              pathLength={1}
              strokeDasharray={1}
              className="animate-draw stroke-sky-300 motion-reduce:animate-none"
              strokeWidth={3}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </svg>
        </div>
        <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
          <p className="text-xs font-medium text-white/60">Commit evidence</p>
          <svg
            viewBox={`0 0 ${HEATMAP_COLS * (CELL + CELL_GAP) - CELL_GAP} ${HEATMAP_ROWS * (CELL + CELL_GAP) - CELL_GAP}`}
            className="mt-2 h-24 w-full"
          >
            {HEATMAP_CELLS.map((cell) => (
              <rect
                key={cell.i}
                data-testid="heatmap-cell"
                x={cell.x}
                y={cell.y}
                width={CELL}
                height={CELL}
                rx={2}
                className="animate-cell-pop fill-emerald-400 [transform-box:fill-box] [transform-origin:center] motion-reduce:animate-none"
                fillOpacity={0.12 + cell.intensity * 0.88}
                style={{ animationDelay: `${cell.i * 30}ms` }}
              />
            ))}
          </svg>
        </div>
      </div>

      <p
        key={captionIndex}
        data-testid="sprint-preview-caption"
        className="animate-fade-up text-lg font-medium text-white/90 motion-reduce:animate-none"
      >
        {caption}
      </p>
    </div>
  );
}
