type Props = {
  jiraEmail: string;
  hasSavedToken: boolean;
  isLoading: boolean;
  error: string;
  onJiraEmailChange: (email: string) => void;
};

export function ApiConnectionsSettings({
  jiraEmail,
  hasSavedToken,
  isLoading,
  error,
  onJiraEmailChange,
}: Props) {
  return (
    <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xl font-semibold text-blue-950">API Connections</h2>
      <p className="mt-1 text-sm text-slate-600">These Jira account credentials are shared across your groups.</p>
      <div className="mt-4 w-full min-w-0 space-y-3">
        <label className="block text-sm font-medium text-slate-700">
          Jira Account Email
          <input
            type="email"
            autoComplete="username"
            value={jiraEmail}
            onChange={(event) => onJiraEmailChange(event.target.value)}
            disabled={isLoading}
            className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-3"
          />
        </label>
        <p role="status" className={`text-xs ${hasSavedToken ? "text-emerald-600" : "text-slate-500"}`}>
          {isLoading ? "Loading Jira credential status..." : hasSavedToken ? "Shared Jira token is configured." : "No shared Jira token is configured."}
        </p>
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      </div>
    </section>
  );
}
