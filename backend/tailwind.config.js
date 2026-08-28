/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html"],
  corePlugins: {
    preflight: false,
  },
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Manrope"', "system-ui", "sans-serif"],
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
      },
      colors: {
        ink: "var(--ink)",
        brand: {
          DEFAULT: "var(--brand)",
          strong: "var(--brand-strong)",
        },
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    logs: false,
    prefix: "dui-",
    themes: [
      {
        prenium: {
          primary: "#ff8775",
          "primary-content": "#1a1815",
          secondary: "#a83bc4",
          "secondary-content": "#ffffff",
          accent: "#770176",
          neutral: "#1a1815",
          "neutral-content": "#fbf6ee",
          "base-100": "#fffdf8",
          "base-200": "#fbf6ee",
          "base-300": "#e2dccb",
          info: "#3b82f6",
          success: "#287451",
          warning: "#8b5d08",
          error: "#a33b45",
        },
      },
    ],
  },
};
