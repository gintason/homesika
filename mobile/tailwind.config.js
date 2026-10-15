/** NativeWind theme generated from the design tokens (same class names as the web dashboard). */
const t = require("./src/theme/tokens.js");

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    colors: {
      transparent: "transparent",
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
      display: ["Montserrat_700Bold"],
      "display-semibold": ["Montserrat_600SemiBold"],
      sans: ["Inter_400Regular"],
      medium: ["Inter_500Medium"],
      semibold: ["Inter_600SemiBold"],
    },
    fontSize: Object.fromEntries(
      Object.entries(t.font.size).map(([k, v]) => [k, [`${v}px`, `${t.font.lineHeight[k]}px`]]),
    ),
    spacing: Object.fromEntries(Object.entries(t.space).map(([k, v]) => [k, `${v}px`])),
    borderRadius: { none: "0", ...Object.fromEntries(Object.entries(t.radius).map(([k, v]) => [k, `${v}px`])), full: "9999px" },
  },
  plugins: [],
};
