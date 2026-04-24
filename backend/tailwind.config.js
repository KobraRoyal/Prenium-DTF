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
        ink: "#201d18",
        brand: {
          DEFAULT: "#8f3d1f",
          strong: "#6f2f17",
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
          primary: "#8f3d1f",
          "primary-content": "#fffdf8",
          secondary: "#584a3d",
          "secondary-content": "#f9f2e7",
          accent: "#ffbda8",
          neutral: "#1f1a14",
          "neutral-content": "#f9f2e7",
          "base-100": "#fffdf8",
          "base-200": "#f6f4ee",
          "base-300": "#ddd2c1",
          info: "#3b82f6",
          success: "#1f7a40",
          warning: "#8a5a08",
          error: "#a11a1a",
        },
      },
    ],
  },
};
