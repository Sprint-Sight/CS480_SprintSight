"use client";

import { useState, useEffect } from "react";
import { Lock, Unlock, Calendar, Loader2 } from "lucide-react";
import type {
  PeerEvaluationConfigResponse,
  SetConfigPayload,
} from "@/features/peer-evaluation/peer-evaluation-api";

type EvaluationConfigPanelProps = {
  config: PeerEvaluationConfigResponse | null;
  isLoading: boolean;
  onUpdateConfig: (payload: SetConfigPayload) => Promise<PeerEvaluationConfigResponse>;
};

function toDateTimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

function toISOStringOrNull(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function EvaluationConfigPanel({
  config,
  isLoading,
  onUpdateConfig,
}: EvaluationConfigPanelProps) {
  const [isOpen, setIsOpen] = useState(config?.is_open ?? false);
  const [opensAt, setOpensAt] = useState(toDateTimeLocal(config?.opens_at));
  const [expiresAt, setExpiresAt] = useState(toDateTimeLocal(config?.expires_at));
  const [isSaving, setIsSaving] = useState(false);

  // Sync prop changes to local state (for page refresh and parent updates)
  useEffect(() => {
    if (config) {
      setIsOpen(config.is_open);
      setOpensAt(toDateTimeLocal(config.opens_at));
      setExpiresAt(toDateTimeLocal(config.expires_at));
    }
  }, [config?.is_open, config?.opens_at, config?.expires_at]);

  const createPayload = (nextIsOpen: boolean): SetConfigPayload => ({
    is_open: nextIsOpen,
    opens_at: toISOStringOrNull(opensAt),
    expires_at: toISOStringOrNull(expiresAt),
  });

  const handleToggle = async () => {
    setIsSaving(true);
    try {
      await onUpdateConfig(createPayload(!isOpen));
      setIsOpen(!isOpen);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveSchedule = async () => {
    setIsSaving(true);
    try {
      await onUpdateConfig(createPayload(isOpen));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6">
      <h3 className="text-lg font-semibold text-slate-900 mb-4">Evaluation Window Control</h3>

      <div className="space-y-4">
        {/* Status */}
        <div className="rounded-lg bg-slate-50 p-4">
          <p className="text-sm font-medium text-slate-700 mb-2">Current Status</p>
          <div className="flex items-center gap-2">
            {isOpen ? (
              <>
                <Unlock className="h-5 w-5 text-green-600" />
                <span className="text-sm font-medium text-green-600">Open for Evaluations</span>
              </>
            ) : (
              <>
                <Lock className="h-5 w-5 text-red-600" />
                <span className="text-sm font-medium text-red-600">Closed</span>
              </>
            )}
          </div>
        </div>

        {/* Toggle Button */}
        <button
          type="button"
          onClick={handleToggle}
          disabled={isSaving || isLoading}
          className={`w-full rounded-lg px-4 py-2 text-sm font-medium text-white transition-all disabled:opacity-50 ${
            isOpen
              ? "bg-red-600 hover:bg-red-700"
              : "bg-green-600 hover:bg-green-700"
          }`}
        >
          {isSaving ? (
            <>
              <Loader2 className="inline h-4 w-4 animate-spin mr-2" />
              Saving...
            </>
          ) : isOpen ? (
            "Close Evaluation Window"
          ) : (
            "Open Evaluation Window"
          )}
        </button>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="evaluation-opens-at" className="mb-2 block text-sm font-medium text-slate-700">
              Opens at (optional)
            </label>
            <div className="relative">
              <Calendar className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                id="evaluation-opens-at"
                type="datetime-local"
                value={opensAt}
                onChange={(event) => setOpensAt(event.target.value)}
                disabled={isSaving || isLoading}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 pl-10 text-sm focus:border-blue-500 focus:outline-none disabled:bg-slate-100"
              />
            </div>
            {config?.opens_at && (
              <p className="mt-2 text-xs text-slate-600">
                Current opening: {new Date(config.opens_at).toLocaleString()}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="evaluation-expires-at" className="mb-2 block text-sm font-medium text-slate-700">
              Expires at (optional)
            </label>
            <div className="relative">
              <Calendar className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
              <input
                id="evaluation-expires-at"
                type="datetime-local"
                value={expiresAt}
                onChange={(event) => setExpiresAt(event.target.value)}
                disabled={isSaving || isLoading}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 pl-10 text-sm focus:border-blue-500 focus:outline-none disabled:bg-slate-100"
              />
            </div>
            {config?.expires_at && (
              <p className="mt-2 text-xs text-slate-600">
                Current expiry: {new Date(config.expires_at).toLocaleString()}
              </p>
            )}
          </div>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleSaveSchedule}
            disabled={isSaving || isLoading}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save schedule"}
          </button>
        </div>
      </div>
    </div>
  );
}
