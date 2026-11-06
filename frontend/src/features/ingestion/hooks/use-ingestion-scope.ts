"use client";

import { useEffect, useState } from "react";

import { readScope, subscribeScope, writeScope, type IngestionScope } from "@/features/ingestion/scope-store";

/** Reads the persisted UI selection and re-reads it whenever the shell or another page changes it. */
export function useIngestionScope() {
  const [scope, setScope] = useState<IngestionScope>(() => readScope());

  useEffect(() => {
    setScope(readScope());
    return subscribeScope(() => setScope(readScope()));
  }, []);

  return { scope, updateScope: writeScope };
}
