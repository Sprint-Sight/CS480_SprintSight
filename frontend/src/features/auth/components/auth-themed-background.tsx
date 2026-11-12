/**
 * Default auth background (used when the auth showcase flag is off).
 *
 * A diagonal, top-left -> bottom-right theme: a pale blue wash runs corner to corner, a brand
 * navy aura glows in from the top-left and a soft sky aura answers it in the bottom-right.
 * The auras drift like an aura (12s / 15s loops) so the page feels alive; with reduced motion
 * they stay still. The centre stays light, so the login card sits on calm, readable ground.
 */
export const THEMED_BACKGROUND =
  "linear-gradient(135deg, hsl(214 95% 93%) 0%, hsl(210 40% 98%) 50%, hsl(226 100% 96%) 100%)";

/** Navy aura, anchored top-left. */
export const NAVY_AURA =
  "radial-gradient(closest-side, hsl(var(--brand) / 0.55), hsl(var(--brand) / 0.12) 60%, transparent)";

/** Sky aura, anchored bottom-right. */
export const SKY_AURA = "radial-gradient(closest-side, hsl(199 89% 48% / 0.28), transparent)";

export function AuthThemedBackground() {
  return (
    <div
      data-testid="auth-themed-background"
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 overflow-hidden"
      style={{ backgroundImage: THEMED_BACKGROUND }}
    >
      <div
        data-testid="auth-aura"
        className="absolute -left-[25vw] -top-[30vh] h-[90vh] w-[70vw] animate-aura-drift-a blur-2xl will-change-transform motion-reduce:animate-none"
        style={{ backgroundImage: NAVY_AURA }}
      />
      <div
        data-testid="auth-aura"
        className="absolute -bottom-[30vh] -right-[20vw] h-[85vh] w-[60vw] animate-aura-drift-b blur-2xl will-change-transform motion-reduce:animate-none"
        style={{ backgroundImage: SKY_AURA }}
      />
    </div>
  );
}
