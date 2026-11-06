"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export const UNSAVED_CHANGES_MESSAGE = "You have unsaved rubric changes. Leave this page without saving?";

/**
 * Warns before leaving the page while `hasUnsavedChanges` is true.
 * Covers closing or refreshing the tab (beforeunload) and same-origin link clicks inside the app.
 * Browser back/forward is not intercepted.
 */
export function useUnsavedChangesGuard(hasUnsavedChanges: boolean) {
  const router = useRouter();

  useEffect(() => {
    if (!hasUnsavedChanges) return;

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };

    // Capture phase runs before Next.js Link's React handler, which skips clicks that were already prevented.
    const handleClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!(event.target instanceof Element)) return;

      const anchor = event.target.closest("a[href]");
      if (!(anchor instanceof HTMLAnchorElement)) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;

      const destination = new URL(anchor.href);
      if (destination.origin !== window.location.origin) return;

      const currentPath = `${window.location.pathname}${window.location.search}`;
      const nextPath = `${destination.pathname}${destination.search}`;
      if (nextPath === currentPath && destination.hash) return;

      event.preventDefault();
      if (window.confirm(UNSAVED_CHANGES_MESSAGE)) {
        router.push(`${nextPath}${destination.hash}`);
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("click", handleClick, true);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleClick, true);
    };
  }, [hasUnsavedChanges, router]);
}
