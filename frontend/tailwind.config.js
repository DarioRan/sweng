/** Design tokens (T-209). Phone-first: large type and touch targets (Rule 6). */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["media"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "rgb(var(--bg) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        subtle: "rgb(var(--subtle) / <alpha-value>)",
        "accent-strong": "rgb(var(--accent-strong) / <alpha-value>)",
        ink: "rgb(var(--text) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        accent: "rgb(var(--accent) / <alpha-value>)",
        "accent-ink": "rgb(var(--accent-text) / <alpha-value>)",
        "accent-soft": "rgb(var(--accent-soft) / <alpha-value>)",
        "warn-bg": "rgb(var(--warn-bg) / <alpha-value>)",
        "warn-line": "rgb(var(--warn-line) / <alpha-value>)",
        "stop-bg": "rgb(var(--stop-bg) / <alpha-value>)",
        "stop-line": "rgb(var(--stop-line) / <alpha-value>)",
        ok: "rgb(var(--ok) / <alpha-value>)",
        box: "rgb(var(--box) / <alpha-value>)",
      },
      borderRadius: {
        card: "14px",
      },
      spacing: {
        touch: "48px", // Rule 6: hands stay on the hardware - large touch targets
      },
      minHeight: {
        touch: "48px",
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          '"Segoe UI"',
          "Roboto",
          '"Helvetica Neue"',
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
