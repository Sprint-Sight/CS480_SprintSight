import Link from "next/link";

type ForgotPasswordFormProps = {
  email: string;
  error: string;
  isLoading: boolean;
  isSubmitted: boolean;
  onEmailChange: (email: string) => void;
  onSubmit: (event: React.FormEvent<HTMLFormElement>) => void;
};

export function ForgotPasswordForm({
  email,
  error,
  isLoading,
  isSubmitted,
  onEmailChange,
  onSubmit,
}: ForgotPasswordFormProps) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)]">
        <h1 className="mb-2 text-2xl font-semibold text-slate-900">Reset your password</h1>
        {isSubmitted ? (
          <div className="space-y-5">
            <p className="text-sm text-slate-600">
              If an active account matches that email, password reset instructions have been sent.
              Check your inbox.
            </p>
            <Link href="/login" className="text-sm text-blue-700 hover:underline">
              Return to sign in
            </Link>
          </div>
        ) : (
          <form className="space-y-5" onSubmit={onSubmit}>
            <p className="text-sm text-slate-600">
              Enter your account email and we’ll send a link to choose a new password.
            </p>
            <label className="block text-sm font-medium text-slate-700">
              Email address
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => onEmailChange(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-200 px-4 py-2 text-slate-800"
              />
            </label>
            {error && <p className="text-sm text-rose-600">{error}</p>}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-lg bg-[#0b2046] py-2.5 font-medium text-white disabled:opacity-50"
            >
              {isLoading ? "Sending..." : "Email me a reset link"}
            </button>
            <div className="text-center">
              <Link href="/login" className="text-sm text-blue-700 hover:underline">
                Return to sign in
              </Link>
            </div>
          </form>
        )}
      </section>
    </main>
  );
}
