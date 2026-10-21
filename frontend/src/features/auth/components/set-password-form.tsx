import Link from "next/link";

type SetPasswordFormProps = {
  token: string;
  purpose: string;
  password: string;
  confirmPassword: string;
  error: string;
  isLoading: boolean;
  isComplete: boolean;
  onPasswordChange: (password: string) => void;
  onConfirmPasswordChange: (password: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function SetPasswordForm({
  token,
  purpose,
  password,
  confirmPassword,
  error,
  isLoading,
  isComplete,
  onPasswordChange,
  onConfirmPasswordChange,
  onSubmit,
}: SetPasswordFormProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h1 className="mb-2 text-2xl font-semibold text-slate-900">
          {isComplete ? "Password updated" : "Choose a new password"}
        </h1>
        {isComplete ? (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              Your password has been updated. Sign in with your new password to continue.
            </p>
            <Link
              href="/login"
              className="block w-full rounded-lg bg-[#0b2046] py-2.5 text-center font-medium text-white hover:bg-[#0f2c61]"
            >
              Go to sign in
            </Link>
          </div>
        ) : (
          <form className="space-y-5" onSubmit={onSubmit}>
            <p className="text-sm text-slate-600">
              Enter and confirm the password you want to use for SprintSight.
            </p>
            <label className="block text-sm font-medium text-slate-700">
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                value={password}
                onChange={(event) => onPasswordChange(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800"
              />
            </label>
            <label className="block text-sm font-medium text-slate-700">
              Confirm new password
              <input
                type="password"
                autoComplete="new-password"
                minLength={8}
                maxLength={128}
                required
                value={confirmPassword}
                onChange={(event) => onConfirmPasswordChange(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800"
              />
            </label>
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <button
              type="submit"
              disabled={isLoading || !token || !purpose}
              className="w-full rounded-lg bg-[#0b2046] py-2.5 font-medium text-white disabled:opacity-50"
            >
              {isLoading ? "Updating password..." : "Set password"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
