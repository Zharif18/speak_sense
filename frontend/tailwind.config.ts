import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Cool paper white -- deliberately not the cream-#F4F1EA default.
        paper: "#F2F4F1",
        // Warm-tinted near-black, not pure #000.
        ink: "#1C2321",
        // Brand teal: calm, growth, trust -- the "steady voice" color.
        teal: {
          DEFAULT: "#2F6F62",
          50: "#EAF2F0",
          100: "#CFE3DE",
          400: "#4A8B7D",
          600: "#2F6F62",
          700: "#245650",
          900: "#153330",
        },
        // Amber accent, used sparingly for CTAs and highlighted moments.
        amber: {
          DEFAULT: "#E3A23B",
          100: "#FBEAD0",
          400: "#E3A23B",
          600: "#C6832256"
        },
        // Blue-grey "mist" -- reserved for wearable / physiological data only,
        // so users learn to associate this color with body-signal context.
        mist: {
          DEFAULT: "#7C93A8",
          100: "#E7ECF0",
          400: "#7C93A8",
          600: "#5A7488",
        },
        line: "#DDE3DF",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-jbmono)", "monospace"],
      },
      keyframes: {
        wave: {
          "0%, 100%": { transform: "scaleY(0.4)" },
          "50%": { transform: "scaleY(1)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        wave: "wave 1.2s ease-in-out infinite",
        "fade-up": "fade-up 0.6s ease-out forwards",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
