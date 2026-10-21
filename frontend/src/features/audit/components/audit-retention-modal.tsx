"use client";

import React, { useState, useEffect } from "react";
import { X, AlertCircle, CheckCircle2, Loader } from "lucide-react";
import type { AuditRetentionConfig, AuditRetentionConfigUpdate } from "@/features/audit/audit-api";

interface AuditRetentionModalProps {
  isOpen: boolean;
  config: AuditRetentionConfig | null;
  isLoading: boolean;
  isSaving: boolean;
  error: string | null;
  saveError: string | null;
  onClose: () => void;
  onSave: (payload: AuditRetentionConfigUpdate) => Promise<void>;
  onLoadConfig: () => Promise<void>;
}

export function AuditRetentionModal({
  isOpen,
  config,
  isLoading,
  isSaving,
  error,
  saveError,
  onClose,
  onSave,
  onLoadConfig,
}: AuditRetentionModalProps) {
  const [hotRetentionDays, setHotRetentionDays] = useState<number>(30);
  const [actionArchiveRetentionDays, setActionArchiveRetentionDays] = useState<number>(365);
  const [overrideArchiveRetentionDays, setOverrideArchiveRetentionDays] = useState<number>(365);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  // Load config when modal opens
  useEffect(() => {
    if (isOpen && !config) {
      void onLoadConfig();
    }
  }, [isOpen, config, onLoadConfig]);

  // Populate form with current config
  useEffect(() => {
    if (config) {
      setHotRetentionDays(config.hot_retention_days);
      setActionArchiveRetentionDays(config.action_archive_retention_days);
      setOverrideArchiveRetentionDays(config.override_archive_retention_days);
      setIsDirty(false);
      setSaveSuccess(false);
    }
  }, [config]);

  const handleInputChange = (setter: React.Dispatch<React.SetStateAction<number>>) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = parseInt(e.target.value, 10);
    if (!isNaN(value) && value >= 1) {
      setter(value);
      setIsDirty(true);
      setSaveSuccess(false);
    }
  };

  const handleSave = async () => {
    try {
      await onSave({
        hot_retention_days: hotRetentionDays,
        action_archive_retention_days: actionArchiveRetentionDays,
        override_archive_retention_days: overrideArchiveRetentionDays,
      });
      setSaveSuccess(true);
      setIsDirty(false);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err) {
      // Error is handled by the hook and displayed via saveError prop
    }
  };

  const handleCancel = () => {
    if (config) {
      setHotRetentionDays(config.hot_retention_days);
      setActionArchiveRetentionDays(config.action_archive_retention_days);
      setOverrideArchiveRetentionDays(config.override_archive_retention_days);
      setIsDirty(false);
      setSaveSuccess(false);
    }
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-xl">
        {/* Header */}
        <div className="border-b border-slate-200 bg-slate-50 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Audit Log Retention Settings</h2>
              <p className="mt-1 text-sm text-slate-500">Configure how long audit records are retained in the system.</p>
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="px-6 py-4">
          {/* Loading State */}
          {isLoading && !config ? (
            <div className="flex items-center justify-center py-8">
              <Loader className="h-5 w-5 animate-spin text-blue-600" />
              <span className="ml-3 text-sm text-slate-600">Loading retention settings...</span>
            </div>
          ) : error ? (
            <div className="rounded-lg bg-rose-50 p-4 border border-rose-200">
              <div className="flex gap-3">
                <AlertCircle className="h-5 w-5 text-rose-600 flex-shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-medium text-rose-900">Failed to load settings</h3>
                  <p className="mt-1 text-sm text-rose-700">{error}</p>
                </div>
              </div>
            </div>
          ) : config ? (
            <div className="space-y-5">
              {/* Success Message */}
              {saveSuccess && (
                <div className="rounded-lg bg-emerald-50 p-4 border border-emerald-200">
                  <div className="flex gap-3">
                    <CheckCircle2 className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <h3 className="text-sm font-medium text-emerald-900">Settings saved successfully</h3>
                      <p className="mt-1 text-sm text-emerald-700">Retention policy updated and audit logged.</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Save Error Message */}
              {saveError && (
                <div className="rounded-lg bg-rose-50 p-4 border border-rose-200">
                  <div className="flex gap-3">
                    <AlertCircle className="h-5 w-5 text-rose-600 flex-shrink-0 mt-0.5" />
                    <div>
                      <h3 className="text-sm font-medium text-rose-900">Failed to save settings</h3>
                      <p className="mt-1 text-sm text-rose-700">{saveError}</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Hot Retention Days */}
              <div>
                <label htmlFor="hotRetention" className="block text-sm font-medium text-slate-900 mb-1.5">
                  Hot Storage Retention (days)
                </label>
                <p className="text-xs text-slate-500 mb-2">
                  How long audit records remain in the active database before archival. Faster query access.
                </p>
                <input
                  id="hotRetention"
                  type="number"
                  min="1"
                  value={hotRetentionDays}
                  onChange={handleInputChange(setHotRetentionDays)}
                  disabled={isSaving}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              {/* Action Archive Retention */}
              <div>
                <label htmlFor="actionArchive" className="block text-sm font-medium text-slate-900 mb-1.5">
                  Action Audit Archive Retention (days)
                </label>
                <p className="text-xs text-slate-500 mb-2">
                  How long action audit records (system changes) are retained in archive storage after hot retention expires.
                </p>
                <input
                  id="actionArchive"
                  type="number"
                  min="1"
                  value={actionArchiveRetentionDays}
                  onChange={handleInputChange(setActionArchiveRetentionDays)}
                  disabled={isSaving}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              {/* Override Archive Retention */}
              <div>
                <label htmlFor="overrideArchive" className="block text-sm font-medium text-slate-900 mb-1.5">
                  Override Audit Archive Retention (days)
                </label>
                <p className="text-xs text-slate-500 mb-2">
                  How long score override audit records are retained in archive storage after hot retention expires.
                </p>
                <input
                  id="overrideArchive"
                  type="number"
                  min="1"
                  value={overrideArchiveRetentionDays}
                  onChange={handleInputChange(setOverrideArchiveRetentionDays)}
                  disabled={isSaving}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg bg-white text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-600 transition-all disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              {/* Last Updated Info */}
              <div className="rounded-lg bg-slate-50 p-3 border border-slate-200">
                <p className="text-xs text-slate-600">
                  <span className="font-medium">Last updated:</span> {new Date(config.updated_at).toLocaleString()}
                  {config.updated_by && <span className="ml-2">by {config.updated_by}</span>}
                </p>
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 bg-slate-50 px-6 py-4 flex items-center justify-end gap-3">
          <button
            onClick={handleCancel}
            disabled={isSaving}
            className="px-4 py-2 text-sm font-medium text-slate-700 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || isSaving || !config}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving && <Loader className="h-4 w-4 animate-spin" />}
            {isSaving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
