/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        sidebar: "#0b1f33",
        accent: "#0f766e",
        ink: "#0f172a",
      },
      fontFamily: {
        display: ['"IBM Plex Serif"', "Georgia", "serif"],
        body: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
