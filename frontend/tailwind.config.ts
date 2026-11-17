import type { Config } from "tailwindcss";

/*
 * Design tokens – direction: "careful, clinical, plain-spoken"; world: the printed lab result sheet
 * and pink ECG grid paper. Ink-tinted neutral ramp (Tailwind slate), navy for text and the primary
 * action, ONE teal accent, and a toned red/amber used only as lab flags (H / L, needs checking).
 * `cyan` is mapped onto the accent so no second accent can creep back in.
 */
const accent = { 50: "#eef6f5", 100: "#d5ebe8", 200: "#a9d6d0", 400: "#3f9d93", 500: "#178277", 600: "#0f766e", 700: "#0d655e", 800: "#0b524d", 900: "#09403c" };

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 950: "#0a1830", 900: "#0b2545", 800: "#13315c", 700: "#1d4174", 600: "#2a5592" },
        teal: accent,
        cyan: accent,
        flag: { high: "#b42318", low: "#b42318", warn: "#a15c07", ok: "#15803d" },
        paper: { minor: "#f6d9d9", major: "#ecb3b3" },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "Segoe UI", "system-ui", "-apple-system", "Roboto", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      transitionTimingFunction: { out: "cubic-bezier(0.22, 1, 0.36, 1)" },
    },
  },
  plugins: [],
};
export default config;
