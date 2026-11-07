"use client";

import { useCallback, useRef, useState } from "react";

// Ignores re-entrant calls while an action is in flight, so a double-click cannot fire two requests.
// Errors are rethrown; the action's caller decides how to report them.
export function useAsyncAction<TArgs extends unknown[], TResult>(
  action: (...args: TArgs) => Promise<TResult> | TResult,
) {
  const [isPending, setIsPending] = useState(false);
  const inFlightRef = useRef(false);

  const run = useCallback(
    async (...args: TArgs): Promise<TResult | undefined> => {
      if (inFlightRef.current) return undefined;
      inFlightRef.current = true;
      setIsPending(true);
      try {
        return await action(...args);
      } finally {
        inFlightRef.current = false;
        setIsPending(false);
      }
    },
    [action],
  );

  return { run, isPending };
}
