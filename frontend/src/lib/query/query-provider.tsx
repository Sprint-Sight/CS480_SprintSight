"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { migrateLegacyScope } from "@/features/ingestion/scope-store";
import { createQueryClient } from "@/lib/query/query-client";
import { getSession, subscribeToSession } from "@/lib/auth/session";

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  useEffect(() => {
    migrateLegacyScope();
    // Drop cached course, project and ingestion data when the session ends so the next user never sees it.
    return subscribeToSession(() => {
      if (!getSession()) queryClient.clear();
    });
  }, [queryClient]);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
