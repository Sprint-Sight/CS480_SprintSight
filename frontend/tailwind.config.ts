import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        muted: "hsl(var(--muted) / <alpha-value>)",
        border: "hsl(var(--border) / <alpha-value>)",
        primary: "hsl(var(--primary) / <alpha-value>)",
        danger: "hsl(var(--danger) / <alpha-value>)",
        chart: {
          1: "hsl(var(--chart-1) / <alpha-value>)",
          2: "hsl(var(--chart-2) / <alpha-value>)",
          3: "hsl(var(--chart-3) / <alpha-value>)",
          4: "hsl(var(--chart-4) / <alpha-value>)",
          5: "hsl(var(--chart-5) / <alpha-value>)",
          bar: "hsl(var(--chart-bar) / <alpha-value>)",
        },
        brand: {
          DEFAULT: "hsl(var(--brand) / <alpha-value>)",
          hover: "hsl(var(--brand-hover) / <alpha-value>)",
        },
        score: {
          high: "hsl(var(--score-high) / <alpha-value>)",
          mid: "hsl(var(--score-mid) / <alpha-value>)",
          low: "hsl(var(--score-low) / <alpha-value>)",
        },
      },
      // Auth-screen sprint preview. Card width equals column width and the board gap is
      // 0.75rem, so each step moves a card exactly one column.
      keyframes: {
        // Auth background auras: slow, looping drift (opposite paths so they never sync).
        "aura-drift-a": {
          "0%,100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(8vw, 6vh) scale(1.12)" },
          "66%": { transform: "translate(3vw, 12vh) scale(0.95)" },
        },
        "aura-drift-b": {
          "0%,100%": { transform: "translate(0, 0) scale(1)" },
          "33%": { transform: "translate(-7vw, -8vh) scale(1.1)" },
          "66%": { transform: "translate(-12vw, -2vh) scale(0.92)" },
        },
        "card-flow": {
          "0%,20%": { transform: "translateX(0)", opacity: "1" },
          "33%,53%": { transform: "translateX(calc(100% + .75rem))" },
          "66%,90%": { transform: "translateX(calc(200% + 1.5rem))", opacity: "1" },
          "100%": { transform: "translateX(calc(200% + 1.5rem))", opacity: "0" },
        },
        // Same 12s cycle as card-flow: the AI score appears once a card reaches the last column.
        "badge-in": {
          "0%,64%": { opacity: "0", transform: "scale(0.6)" },
          "72%,90%": { opacity: "1", transform: "scale(1)" },
          "100%": { opacity: "0", transform: "scale(1)" },
        },
        draw: {
          from: { strokeDashoffset: "1" },
          to: { strokeDashoffset: "0" },
        },
        "cell-pop": {
          from: { opacity: "0", transform: "scale(0.6)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "aura-drift-a": "aura-drift-a 12s ease-in-out infinite",
        "aura-drift-b": "aura-drift-b 15s ease-in-out infinite",
        "card-flow": "card-flow 12s ease-in-out infinite",
        "badge-in": "badge-in 12s ease-out infinite",
        draw: "draw 2.5s ease-out both",
        "cell-pop": "cell-pop .4s ease-out both",
        "fade-up": "fade-up .5s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
