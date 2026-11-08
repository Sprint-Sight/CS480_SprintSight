import type { FocusEvent } from "react";

const FIELD_SELECTOR = "input, textarea, select";

// Keeps a focused field visible when a phone keyboard shrinks the viewport.
export function scrollFieldIntoView(event: FocusEvent<HTMLElement>) {
  const target = event.target;
  if (!(target instanceof HTMLElement) || !target.matches(FIELD_SELECTOR)) return;
  target.scrollIntoView?.({ block: "center" });
}
