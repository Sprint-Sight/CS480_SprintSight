/**
 * Shared Recharts styling, so every chart reads its colors from the CSS tokens in
 * app/globals.css (and follows any future theme change) and uses one tick size.
 */

/** `hsl(var(--<token>))`, for Recharts props that need a plain color string. */
export function chartColor(token: string): string {
  return `hsl(var(--${token}))`;
}

/** Axis tick style: muted text at 12px (the smallest readable size we allow). */
export const CHART_TICK = { fill: chartColor("muted"), fontSize: 12 } as const;

/** Grid line color for CartesianGrid / PolarGrid. */
export const CHART_GRID_STROKE = chartColor("border");
