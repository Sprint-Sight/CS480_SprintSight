/**
 * Feature flags for the auth screens (login, forgot password, set password).
 *
 * AUTH SHOWCASE (idle, OFF by default)
 *   On:  animated "AI grading" sprint preview on the left, page-wide navy -> light fade,
 *        and a "Welcome to SprintSight" heading on the login card.
 *   Off: the original centred login card (logo + tagline) on a soft diagonal themed background.
 *
 * Toggle it in frontend/.env.local, then restart `npm run dev` (NEXT_PUBLIC_ values are read
 * when the dev server starts or the app is built):
 *   NEXT_PUBLIC_AUTH_SHOWCASE=true
 */
export function isAuthShowcaseEnabled(value: string | undefined): boolean {
  return value?.trim().toLowerCase() === "true";
}

// Next.js only inlines NEXT_PUBLIC_ variables written out in full like this.
export const AUTH_SHOWCASE_ENABLED = isAuthShowcaseEnabled(process.env.NEXT_PUBLIC_AUTH_SHOWCASE);
