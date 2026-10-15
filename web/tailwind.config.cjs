/** Tailwind theme generated from the design tokens: classes like bg-primary-600, text-ink-800, rounded-lg. */
const t = require("./src/theme/tokens.cjs");
const px = (obj) => Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, `${v}px`]));

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    screens: px(t.breakpoint),
    colors: {
      transparent: "transparent",
      current: "currentColor",
      white: "#FFFFFF",
      primary: t.color.primary,
      sky: t.color.sky,
      gold: t.color.gold,
      ink: t.color.ink,
      surface: t.color.surface,
      success: t.color.success,
      warning: t.color.warning,
      danger: t.color.danger,
      emergency: t.color.emergency,
    },
    fontFamily: {
      display: [t.font.family.display, "system-ui", "sans-serif"],
      sans: [t.font.family.body, "system-ui", "sans-serif"],
      mono: [t.font.family.mono, "ui-monospace", "monospace"],
    },
    fontSize: Object.fromEntries(
      Object.entries(t.font.size).map(([k, v]) => [k, [`${v}px`, `${t.font.lineHeight[k]}px`]]),
    ),
    spacing: px(t.space),
    borderRadius: { none: "0", ...px(t.radius), full: "9999px" },
    extend: {
      boxShadow: Object.fromEntries(
        Object.entries(t.shadow).map(([k, s]) => [k, `${s.x}px ${s.y}px ${s.blur}px ${s.color}`]),
      ),
      transitionDuration: Object.fromEntries(Object.entries(t.motion.duration).map(([k, v]) => [k, `${v}ms`])),
      minHeight: { touch: `${t.size.touchTarget}px` },
      minWidth: { touch: `${t.size.touchTarget}px` },
    },
  },
  plugins: [],
};
