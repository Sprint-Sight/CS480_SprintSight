"use client";

import { useState, useEffect } from "react";
import { Lock, Unlock, Calendar, Loader2 } from "lucide-react";
import type { PeerEvaluationConfigResponse } from "@/features/peer-evaluation/peer-evaluation-api";

type EvaluationConfigPanelProps = {
  config: PeerEvaluationConfigResponse | null;
  isLoading: boolean;
  onUpdateConfig: (isOpen: boolean, expiresAt?: string) => Promise<PeerEvaluationConfigResponse>;
};

export function EvaluationConfigPanel({
  config,
  isLoading,
  onUpdateConfig,
}: EvaluationConfigPanelProps) {
  const [isOpen, setIsOpen] = useState(config?.is_open ?? false);
  const [expiresAt, setExpiresAt] = useState(config?.expires_at ?? "");
  const [isSaving, setIsSaving] = useState(false);

  // Sync prop changes to local state (for page refresh and parent updates)
  useEffect(() => {
    if (config) {
      setIsOpen(config.is_open);
      setExpiresAt(config.expires_at ?? "");
    }
  }, [config?.is_open, config?.expires_at]);

  const handleToggle = async () => {
    setIsSaving(true);
    try {
      await onUpdateConfig(!isOpen, expiresAt || undefined);
      setIsOpen(!isOpen);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSetExpiry = async () => {
    if (!expiresAt) return;
    setIsSaving(true);
    try {
      await onUpdateConfig(isOpen, expiresAt);
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

        {/* Expiry Date */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Expiry Date (optional)
          </label>
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Calendar className="absolute left-3 top-2.5 h-4 w-4 text-slate-500 pointer-events-none" />
              <input
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 pl-10 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <button
              type="button"
              onClick={handleSetExpiry}
              disabled={!expiresAt || isSaving || isLoading}
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Set"}
            </button>
          </div>
          {config?.expires_at && (
            <p className="text-xs text-slate-600 mt-2">
              Current expiry: {new Date(config.expires_at).toLocaleString()}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
