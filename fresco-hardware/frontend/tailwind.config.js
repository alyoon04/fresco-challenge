/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: {
          50: "#FDFCF8",
          100: "#FAF9F0",
          200: "#F5F3E8",
          300: "#EBE8D8",
          400: "#D5D0BC",
          500: "#B8B29E",
          600: "#918B78",
          700: "#6B6658",
          800: "#45423A",
          900: "#131314",
        },
        terra: {
          50: "#FEF5F1",
          100: "#FCEAE0",
          200: "#F9D2C1",
          300: "#F0B49A",
          400: "#E4926E",
          500: "#D97757",
          600: "#C4613F",
          700: "#A34E33",
          800: "#7D3D29",
          900: "#5A2D1E",
        },
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
