/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["IBM Plex Sans", "Manrope", "Avenir Next", "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 45px -26px rgba(15, 23, 42, 0.35)",
      },
    },
  },
  plugins: [],
};
