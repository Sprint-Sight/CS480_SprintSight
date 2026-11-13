import { AUTH_SHOWCASE_ENABLED } from "@/features/auth/auth-feature-flags";
import { AuthShowcaseShell } from "@/features/auth/components/auth-showcase-shell";
import { AuthThemedBackground } from "@/features/auth/components/auth-themed-background";

type AuthShellProps = {
  children: React.ReactNode;
  /** Defaults to the NEXT_PUBLIC_AUTH_SHOWCASE flag; passed explicitly only in tests. */
  showcase?: boolean;
};

/**
 * Layout for every auth screen. Picks between:
 * - default: the centred form card on a diagonal themed background;
 * - showcase (idle, behind NEXT_PUBLIC_AUTH_SHOWCASE): the animated product preview layout.
 */
export function AuthShell({ children, showcase = AUTH_SHOWCASE_ENABLED }: AuthShellProps) {
  if (showcase) return <AuthShowcaseShell>{children}</AuthShowcaseShell>;

  return (
    <div className="relative min-h-dvh bg-slate-50">
      <AuthThemedBackground />
      <div className="relative">{children}</div>
    </div>
  );
}
