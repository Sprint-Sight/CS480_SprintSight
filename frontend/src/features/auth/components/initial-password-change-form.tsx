type InitialPasswordChangeFormProps = {
  newPassword: string;
  confirmPassword: string;
  error: string;
  isLoading: boolean;
  onNewPasswordChange: (password: string) => void;
  onConfirmPasswordChange: (password: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function InitialPasswordChangeForm({
  newPassword,
  confirmPassword,
  error,
  isLoading,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onSubmit,
}: InitialPasswordChangeFormProps) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white w-full max-w-md rounded-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] p-8">
        <h2 className="text-xl font-semibold text-slate-900 mb-2">Set Your Password</h2>
        <p className="text-sm text-slate-600 mb-6">
          This account has a temporary password. Set a new password to continue.
        </p>

        <form className="space-y-6" onSubmit={onSubmit}>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              New Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={newPassword}
              onChange={(e) => onNewPasswordChange(e.target.value)}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
            <p className="text-xs text-slate-500 mt-1">Minimum 8 characters</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Confirm Password
            </label>
            <input
              type="password"
              placeholder="••••••••"
              value={confirmPassword}
              onChange={(e) => onConfirmPasswordChange(e.target.value)}
              className="w-full px-4 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 transition-all text-slate-800 disabled:bg-slate-100"
              required
              disabled={isLoading}
            />
          </div>

          {error && <p className="text-sm text-rose-600">{error}</p>}

          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-[#0b2046] hover:bg-[#0f2c61] text-white py-2.5 rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            {isLoading ? "Updating password..." : "Set Password and Continue"}
          </button>
        </form>
      </div>
    </div>
  );
}
